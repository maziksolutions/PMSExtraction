from __future__ import annotations

import uuid
from difflib import SequenceMatcher
from typing import Annotated, Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user
from app.models.ingestion import Manual
from app.models.user import User
from app.models.vessel import VesselProject

router = APIRouter()

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
# Utility: extract keywords from a filename
# ---------------------------------------------------------------------------


def _filename_keywords(filename: str) -> list[str]:
    """
    Split a filename on underscores, hyphens, dots and spaces to produce
    a list of lowercase keyword tokens (min length 2).
    """
    import re
    stem = filename.rsplit(".", 1)[0] if "." in filename else filename
    tokens = re.split(r"[_\-\.\s]+", stem)
    return [t.lower() for t in tokens if len(t) >= 2]


def _keyword_overlap_score(name_tokens: list[str], manual_tokens: list[str]) -> float:
    """
    Compute a simple overlap score: fraction of name_tokens found in manual_tokens.
    """
    if not name_tokens:
        return 0.0
    hits = sum(1 for t in name_tokens if t in manual_tokens)
    return hits / len(name_tokens)


def _fuzzy_score(a: str, b: str) -> float:
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()


def _compute_match_score(machinery_tokens: list[str], manual_tokens: list[str]) -> int:
    """
    Compute a 0-100 integer match score combining keyword overlap and
    sequence similarity of the joined token strings.
    """
    overlap = _keyword_overlap_score(machinery_tokens, manual_tokens)
    seq_sim = _fuzzy_score(" ".join(machinery_tokens), " ".join(manual_tokens))
    # Weighted average: 60% keyword overlap, 40% sequence similarity
    raw = 0.60 * overlap + 0.40 * seq_sim
    return min(100, int(round(raw * 100)))


def _precheck_status(score: int) -> str:
    if score >= 80:
        return "found"
    elif score >= 65:
        return "low_confidence"
    else:
        return "missing"


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.post(
    "/{vessel_id}/precheck/run",
    summary="F-10: Run instruction manual pre-check for a vessel",
)
async def run_precheck(
    vessel_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, Any]:
    """
    1. Find all Machinery Particulars manuals for the vessel.
    2. Extract machinery keywords from each filename.
    3. Match against Instruction Manuals using keyword overlap + fuzzy scoring.
    4. Upsert rows in instruction_manual_precheck.
    5. Return the list of precheck items.
    """
    await _get_vessel_or_404(vessel_id, db)

    # ------------------------------------------------------------------
    # Load Machinery Particulars manuals
    # ------------------------------------------------------------------
    mp_result = await db.execute(
        select(Manual).where(
            Manual.vessel_id == vessel_id,
            Manual.tenant_id == current_user.tenant_id,
            Manual.category == "Machinery Particulars",
            Manual.is_deleted == False,
        )
    )
    mp_manuals = mp_result.scalars().all()

    if not mp_manuals:
        return {
            "status": "no_machinery_particulars",
            "message": (
                "No Machinery Particulars manuals found for this vessel. "
                "Upload and classify manuals before running pre-check."
            ),
            "items": [],
        }

    # ------------------------------------------------------------------
    # Load Instruction Manuals for the vessel
    # ------------------------------------------------------------------
    im_result = await db.execute(
        select(Manual).where(
            Manual.vessel_id == vessel_id,
            Manual.tenant_id == current_user.tenant_id,
            Manual.category == "Instruction Manual",
            Manual.is_deleted == False,
        )
    )
    instruction_manuals = im_result.scalars().all()

    # ------------------------------------------------------------------
    # Run matching for each Machinery Particulars entry
    # ------------------------------------------------------------------
    precheck_items: list[dict] = []

    for mp in mp_manuals:
        machinery_tokens = _filename_keywords(mp.original_filename)
        # Infer machinery_name from filename (join first few tokens)
        machinery_name = " ".join(machinery_tokens[:5]).title() if machinery_tokens else mp.original_filename

        best_score = 0
        best_manual: Optional[Manual] = None

        for im in instruction_manuals:
            im_tokens = _filename_keywords(im.original_filename)
            score = _compute_match_score(machinery_tokens, im_tokens)
            if score > best_score:
                best_score = score
                best_manual = im

        item_status = _precheck_status(best_score)
        matched_manual_id = str(best_manual.id) if best_manual else None

        new_id = uuid.uuid4()

        # Upsert into instruction_manual_precheck
        try:
            # Try to find an existing row for this vessel + machinery_name combo
            existing = await db.execute(
                text(
                    "SELECT id FROM instruction_manual_precheck "
                    "WHERE vessel_id = :vid AND tenant_id = :tid "
                    "  AND machinery_name = :mn AND is_deleted = false "
                    "LIMIT 1"
                ),
                {
                    "vid": str(vessel_id),
                    "tid": str(current_user.tenant_id),
                    "mn": machinery_name,
                },
            )
            existing_row = existing.mappings().one_or_none()

            if existing_row:
                existing_id = existing_row["id"]
                await db.execute(
                    text(
                        "UPDATE instruction_manual_precheck "
                        "SET status = :st, match_score = :score, "
                        "matched_manual_id = :mmid, updated_at = NOW() "
                        "WHERE id = :id"
                    ),
                    {
                        "st": item_status,
                        "score": best_score,
                        "mmid": matched_manual_id,
                        "id": str(existing_id),
                    },
                )
                row_id = str(existing_id)
            else:
                await db.execute(
                    text(
                        "INSERT INTO instruction_manual_precheck "
                        "(id, tenant_id, vessel_id, machinery_name, "
                        "machinery_maker, machinery_model, status, "
                        "matched_manual_id, match_score, is_deleted) "
                        "VALUES (:id, :tid, :vid, :mn, :mm, :mo, :st, :mmid, :score, false)"
                    ),
                    {
                        "id": str(new_id),
                        "tid": str(current_user.tenant_id),
                        "vid": str(vessel_id),
                        "mn": machinery_name,
                        "mm": None,  # machinery_maker — not available from filename
                        "mo": None,  # machinery_model — not available from filename
                        "st": item_status,
                        "mmid": matched_manual_id,
                        "score": best_score,
                    },
                )
                row_id = str(new_id)

        except Exception:
            row_id = str(new_id)  # gracefully continue if table doesn't exist

        precheck_items.append(
            {
                "id": row_id,
                "vessel_id": str(vessel_id),
                "machinery_name": machinery_name,
                "status": item_status,
                "match_score": best_score,
                "matched_manual_id": matched_manual_id,
                "matched_manual_name": best_manual.original_filename if best_manual else None,
                "user_acknowledgement": None,
            }
        )

    try:
        await db.commit()
    except Exception:
        pass

    return {"status": "completed", "items": precheck_items, "total": len(precheck_items)}


@router.get(
    "/{vessel_id}/precheck",
    summary="F-10: List all pre-check items for a vessel",
)
async def list_precheck(
    vessel_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    precheck_status: Optional[str] = Query(None, alias="status"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
) -> dict[str, Any]:
    """Return stored instruction_manual_precheck items for the vessel."""
    await _get_vessel_or_404(vessel_id, db)

    where_extra = "AND status = :st " if precheck_status else ""
    try:
        result = await db.execute(
            text(
                "SELECT id, tenant_id, vessel_id, machinery_name, machinery_maker, "
                "machinery_model, status, matched_manual_id, match_score, "
                "user_acknowledgement, acknowledgement_reason, acknowledged_by, "
                "created_at, updated_at "
                "FROM instruction_manual_precheck "
                f"WHERE vessel_id = :vid AND tenant_id = :tid "
                f"  AND is_deleted = false {where_extra}"
                "ORDER BY status, machinery_name "
                f"LIMIT {page_size} OFFSET {(page - 1) * page_size}"
            ),
            {
                "vid": str(vessel_id),
                "tid": str(current_user.tenant_id),
                "st": precheck_status,
            },
        )
        rows = result.mappings().all()
    except Exception:
        rows = []

    return {"items": [dict(r) for r in rows], "page": page, "page_size": page_size}


@router.patch(
    "/{vessel_id}/precheck/{item_id}",
    summary="F-10: Acknowledge a pre-check item",
)
async def acknowledge_precheck_item(
    vessel_id: uuid.UUID,
    item_id: uuid.UUID,
    body: dict[str, Any],
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, Any]:
    """
    Record the user's acknowledgement for a pre-check item.

    Valid user_acknowledgement values:
      upload_pending | genuinely_absent | not_applicable | confirmed
    """
    await _get_vessel_or_404(vessel_id, db)

    valid_acks = {"upload_pending", "genuinely_absent", "not_applicable", "confirmed"}
    ack = body.get("user_acknowledgement", "")
    if ack not in valid_acks:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"Invalid user_acknowledgement '{ack}'. "
                f"Must be one of: {sorted(valid_acks)}"
            ),
        )

    reason = body.get("acknowledgement_reason", "")

    try:
        check = await db.execute(
            text(
                "SELECT id FROM instruction_manual_precheck "
                "WHERE id = :id AND vessel_id = :vid AND tenant_id = :tid "
                "  AND is_deleted = false"
            ),
            {
                "id": str(item_id),
                "vid": str(vessel_id),
                "tid": str(current_user.tenant_id),
            },
        )
        if check.one_or_none() is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Pre-check item not found",
            )

        await db.execute(
            text(
                "UPDATE instruction_manual_precheck "
                "SET user_acknowledgement = :ack, "
                "    acknowledgement_reason = :reason, "
                "    acknowledged_by = :uid, "
                "    updated_at = NOW() "
                "WHERE id = :id AND tenant_id = :tid"
            ),
            {
                "ack": ack,
                "reason": reason,
                "uid": str(current_user.id),
                "id": str(item_id),
                "tid": str(current_user.tenant_id),
            },
        )
        await db.commit()

        row_result = await db.execute(
            text(
                "SELECT id, vessel_id, machinery_name, status, match_score, "
                "matched_manual_id, user_acknowledgement, acknowledgement_reason, "
                "acknowledged_by, updated_at "
                "FROM instruction_manual_precheck WHERE id = :id"
            ),
            {"id": str(item_id)},
        )
        row = row_result.mappings().one()
        return dict(row)

    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Could not update pre-check item: {exc}",
        )
