from __future__ import annotations

import logging
import uuid
from typing import Annotated, Any, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status

logger = logging.getLogger(__name__)
from sqlalchemy import select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user
from app.models.base import TenantBase
from app.models.component import Component
from app.models.ingestion import Manual, ManualStatus
from app.models.user import User
from app.models.vessel import VesselProject
from app.services.deduplication import is_duplicate_component
from app.services.extractor import auto_extract_from_manual

router = APIRouter()

# ---------------------------------------------------------------------------
# In-memory extraction progress tracker
# Structure: { vessel_id_str: { "total": int, "done": int, "status": str } }
# ---------------------------------------------------------------------------

_extract_state: dict[str, dict] = {}

# ---------------------------------------------------------------------------
# Inline SQLAlchemy model for extraction_prompts
# (Defined here to avoid creating a separate models file)
# ---------------------------------------------------------------------------

from sqlalchemy import Boolean, Enum as SAEnum, Float, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column


class ExtractionPrompt(TenantBase):
    __tablename__ = "extraction_prompts"

    prompt_key: Mapped[str] = mapped_column(String(200), nullable=False)
    extraction_type: Mapped[str] = mapped_column(String(50), nullable=False)
    system_prompt: Mapped[str] = mapped_column(Text, nullable=False)
    few_shot_example: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    model_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    max_tokens: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    temperature: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


async def _get_vessel_or_404(vessel_id: uuid.UUID, db: AsyncSession) -> VesselProject:
    result = await db.execute(
        select(VesselProject).where(
            VesselProject.id == vessel_id,
            VesselProject.is_deleted == False,
        )
    )
    vessel = result.scalar_one_or_none()
    if vessel is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Vessel not found")
    return vessel


# ---------------------------------------------------------------------------
# Background runner for all manuals
# ---------------------------------------------------------------------------


async def _run_extract_all(
    vessel_id_str: str,
    tenant_id_str: str,
    manual_ids: list[str],
) -> None:
    """Run auto_extract_from_manual for each manual sequentially."""
    _extract_state[vessel_id_str]["total"] = len(manual_ids)
    _extract_state[vessel_id_str]["done"] = 0
    _extract_state[vessel_id_str]["status"] = "running"

    for mid in manual_ids:
        try:
            await auto_extract_from_manual(mid)
        except Exception as exc:
            logger.error("_run_extract_all: extraction failed for manual %s: %s", mid, exc)
        _extract_state[vessel_id_str]["done"] += 1

    _extract_state[vessel_id_str]["status"] = "completed"


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.post(
    "/{vessel_id}/extract-all",
    summary="F-02: Trigger auto-extraction for all classified manuals",
)
async def extract_all(
    vessel_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, Any]:
    """
    Enqueues auto_extract_from_manual as a background task for every
    classified manual with a non-null category in this vessel.
    """
    await _get_vessel_or_404(vessel_id, db)

    result = await db.execute(
        select(Manual).where(
            Manual.vessel_id == vessel_id,
            Manual.tenant_id == current_user.tenant_id,
            Manual.is_deleted == False,
            Manual.category != None,
        )
    )
    manuals = result.scalars().all()
    total = len(manuals)

    if total == 0:
        return {"started": False, "total": 0, "message": "No classified manuals found."}

    vessel_id_str = str(vessel_id)
    tenant_id_str = str(current_user.tenant_id)
    manual_ids = [str(m.id) for m in manuals]

    _extract_state[vessel_id_str] = {"total": total, "done": 0, "status": "running"}

    background_tasks.add_task(
        _run_extract_all,
        vessel_id_str,
        tenant_id_str,
        manual_ids,
    )

    return {"started": True, "total": total}


@router.get(
    "/{vessel_id}/extraction-status",
    summary="Get extraction progress for a vessel",
)
async def extraction_status(
    vessel_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, Any]:
    """Returns the current in-memory extraction progress for the vessel."""
    await _get_vessel_or_404(vessel_id, db)
    state = _extract_state.get(
        str(vessel_id),
        {"total": 0, "done": 0, "status": "idle"},
    )
    return state


@router.get(
    "/extraction-prompts",
    summary="F-02: List extraction prompts for the tenant",
)
async def list_extraction_prompts(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    extraction_type: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
) -> dict[str, Any]:
    """List all extraction_prompts rows for the authenticated tenant."""
    result = await db.execute(
        text(
            "SELECT id, tenant_id, prompt_key, extraction_type, system_prompt, "
            "few_shot_example, model_id, max_tokens, temperature, version, "
            "is_active, created_at, updated_at, is_deleted "
            "FROM extraction_prompts "
            "WHERE tenant_id = :tid AND is_deleted = false "
            + ("AND extraction_type = :etype " if extraction_type else "")
            + "ORDER BY prompt_key, version DESC "
            f"LIMIT {page_size} OFFSET {(page - 1) * page_size}"
        ),
        {"tid": str(current_user.tenant_id), "etype": extraction_type},
    )
    rows = result.mappings().all()
    return {
        "items": [dict(r) for r in rows],
        "page": page,
        "page_size": page_size,
    }


@router.post(
    "/extraction-prompts",
    status_code=status.HTTP_201_CREATED,
    summary="F-02: Create a new extraction prompt",
)
async def create_extraction_prompt(
    body: dict[str, Any],
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, Any]:
    """Create a new extraction_prompts row."""
    required = {"prompt_key", "extraction_type", "system_prompt"}
    missing = required - body.keys()
    if missing:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Missing required fields: {sorted(missing)}",
        )

    new_id = uuid.uuid4()
    await db.execute(
        text(
            "INSERT INTO extraction_prompts "
            "(id, tenant_id, prompt_key, extraction_type, system_prompt, "
            "few_shot_example, model_id, max_tokens, temperature, version, "
            "is_active, is_deleted) "
            "VALUES (:id, :tid, :pk, :etype, :sp, :fse, :mid, :mt, :temp, 1, true, false)"
        ),
        {
            "id": str(new_id),
            "tid": str(current_user.tenant_id),
            "pk": body["prompt_key"],
            "etype": body["extraction_type"],
            "sp": body["system_prompt"],
            "fse": body.get("few_shot_example"),
            "mid": body.get("model_id"),
            "mt": body.get("max_tokens"),
            "temp": body.get("temperature"),
        },
    )
    await db.commit()

    row = await db.execute(
        text(
            "SELECT id, tenant_id, prompt_key, extraction_type, system_prompt, "
            "few_shot_example, model_id, max_tokens, temperature, version, "
            "is_active, created_at, updated_at "
            "FROM extraction_prompts WHERE id = :id"
        ),
        {"id": str(new_id)},
    )
    record = row.mappings().one()
    return dict(record)


@router.patch(
    "/extraction-prompts/{prompt_id}",
    summary="F-02: Update an extraction prompt",
)
async def update_extraction_prompt(
    prompt_id: uuid.UUID,
    body: dict[str, Any],
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, Any]:
    """Update allowed fields on an extraction_prompts row."""
    # Verify existence and ownership
    check = await db.execute(
        text(
            "SELECT id FROM extraction_prompts "
            "WHERE id = :id AND tenant_id = :tid AND is_deleted = false"
        ),
        {"id": str(prompt_id), "tid": str(current_user.tenant_id)},
    )
    if check.one_or_none() is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Prompt not found")

    allowed_fields = {
        "prompt_key", "extraction_type", "system_prompt",
        "few_shot_example", "model_id", "max_tokens", "temperature",
        "version", "is_active",
    }
    updates = {k: v for k, v in body.items() if k in allowed_fields}
    if not updates:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="No valid fields to update.",
        )

    set_clause = ", ".join(f"{k} = :{k}" for k in updates)
    updates["id"] = str(prompt_id)
    updates["tid"] = str(current_user.tenant_id)

    await db.execute(
        text(
            f"UPDATE extraction_prompts SET {set_clause}, updated_at = NOW() "
            "WHERE id = :id AND tenant_id = :tid"
        ),
        updates,
    )
    await db.commit()

    row = await db.execute(
        text(
            "SELECT id, tenant_id, prompt_key, extraction_type, system_prompt, "
            "few_shot_example, model_id, max_tokens, temperature, version, "
            "is_active, created_at, updated_at "
            "FROM extraction_prompts WHERE id = :id"
        ),
        {"id": str(prompt_id)},
    )
    record = row.mappings().one()
    return dict(record)


@router.post(
    "/{vessel_id}/components/check-duplicates",
    summary="F-05: Run fuzzy deduplication check on vessel components",
)
async def check_component_duplicates(
    vessel_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, Any]:
    """
    Runs pairwise fuzzy deduplication across all components for the vessel.
    Returns a list of {component_id, duplicate_of_id, similarity} for any
    component that is flagged as a duplicate of an earlier component.
    """
    await _get_vessel_or_404(vessel_id, db)

    result = await db.execute(
        select(Component).where(
            Component.vessel_id == vessel_id,
            Component.tenant_id == current_user.tenant_id,
            Component.is_deleted == False,
        ).order_by(Component.created_at)
    )
    components = result.scalars().all()

    def _as_dict(c: Component) -> dict:
        return {
            "component_name": c.component_name or "",
            "maker": c.maker or "",
            "model": c.model or "",
        }

    duplicates: list[dict[str, Any]] = []
    seen: list[Component] = []

    for comp in components:
        comp_dict = _as_dict(comp)
        for earlier in seen:
            if is_duplicate_component(comp_dict, _as_dict(earlier)):
                from difflib import SequenceMatcher as SM
                from app.services.deduplication import normalise, fuzzy_similarity
                sim = fuzzy_similarity(
                    normalise(comp.component_name or ""),
                    normalise(earlier.component_name or ""),
                )
                duplicates.append(
                    {
                        "component_id": str(comp.id),
                        "duplicate_of_id": str(earlier.id),
                        "similarity": round(sim, 4),
                    }
                )
                break  # only report first match per component
        seen.append(comp)

    return {"duplicates": duplicates, "total": len(duplicates)}
