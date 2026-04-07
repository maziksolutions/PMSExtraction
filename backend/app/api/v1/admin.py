from __future__ import annotations

import json
import logging
import re
import uuid
from typing import Annotated, Any

from fastapi import APIRouter, BackgroundTasks, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import require_role
from app.models.audit import AuditLog
from app.models.user import User, UserRole

logger = logging.getLogger(__name__)
router = APIRouter()


def _has_non_ascii(value: str | None) -> bool:
    return bool(value and not value.isascii())


async def _translate_spare_batch(
    spares: list,
    db: AsyncSession,
) -> int:
    """Translate non-English fields on a list of Spare ORM objects using Gemini."""
    from app.core.config import settings

    if not settings.GEMINI_API_KEY:
        logger.warning("translate_spare_batch: GEMINI_API_KEY not set, skipping")
        return 0

    import httpx

    records = []
    for spare in spares:
        records.append(
            {
                "id": str(spare.id),
                "part_name": spare.part_name,
                "spare_model": spare.spare_model,
                "spare_maker": spare.spare_maker,
                "specification": spare.specification,
            }
        )

    prompt = (
        "You are a maritime technical translator. Translate any non-English text (Japanese, Chinese, Korean, etc.) "
        "in the following spare parts records to English. Keep fields that are already in English unchanged. "
        "Return ONLY a valid JSON array with the same records, preserving the 'id' field exactly. "
        "Each record must have: id, part_name, spare_model, spare_maker, specification.\n\n"
        f"Records:\n{json.dumps(records, ensure_ascii=False)}"
    )

    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"gemini-2.0-flash-lite:generateContent?key={settings.GEMINI_API_KEY}"
    )
    payload = {"contents": [{"parts": [{"text": prompt}]}]}

    try:
        async with httpx.AsyncClient(timeout=120) as client:
            response = await client.post(url, json=payload)
            response.raise_for_status()
        data = response.json()
        raw = data["candidates"][0]["content"]["parts"][0]["text"].strip()
        # Strip markdown fences if present
        if raw.startswith("```"):
            lines = raw.splitlines()
            lines = lines[1:] if lines[0].startswith("```") else lines
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            raw = "\n".join(lines).strip()
        translated = json.loads(raw)
    except Exception as exc:
        logger.warning("translate_spare_batch: Gemini call failed: %s", exc)
        return 0

    spare_map = {str(s.id): s for s in spares}
    updated = 0
    for rec in translated:
        spare_id = rec.get("id")
        spare = spare_map.get(spare_id)
        if not spare:
            continue
        changed = False
        for field in ("part_name", "spare_model", "spare_maker", "specification"):
            new_val = rec.get(field)
            if new_val and new_val != getattr(spare, field):
                setattr(spare, field, new_val)
                changed = True
        if changed:
            db.add(spare)
            updated += 1

    await db.commit()
    return updated


@router.get("/admin/audit-logs", summary="Paginated audit logs (Super Admin only)")
async def list_audit_logs(
    current_user: Annotated[User, Depends(require_role(UserRole.super_admin))],
    db: Annotated[AsyncSession, Depends(get_db)],
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
) -> dict[str, Any]:
    result = await db.execute(
        select(AuditLog)
        .where(
            AuditLog.tenant_id == current_user.tenant_id,
            AuditLog.is_deleted == False,
        )
        .order_by(AuditLog.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    logs = result.scalars().all()
    return {
        "items": [
            {
                "id": str(log.id),
                "user_id": str(log.user_id) if log.user_id else None,
                "ip_address": log.ip_address,
                "method": log.method,
                "path": log.path,
                "status_code": log.status_code,
                "duration_ms": log.duration_ms,
                "created_at": log.created_at.isoformat(),
            }
            for log in logs
        ],
        "page": page,
    }


@router.get("/admin/system-health", summary="System health check (Super Admin only)")
async def system_health(
    current_user: Annotated[User, Depends(require_role(UserRole.super_admin))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, Any]:
    try:
        from app.core.health import deep_health_check

        return await deep_health_check()
    except Exception as exc:
        return {"status": "error", "error": str(exc)}


@router.post(
    "/admin/data-deletion/{vessel_id}",
    summary="Trigger auto-deletion policy (Super Admin only)",
)
async def trigger_data_deletion(
    vessel_id: uuid.UUID,
    current_user: Annotated[User, Depends(require_role(UserRole.super_admin))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, Any]:
    """
    Mark vessel data for deletion per the 90-day retention policy
    (90 days after the final export).
    """
    from app.models.vessel import VesselProject
    from sqlalchemy import select

    result = await db.execute(
        select(VesselProject).where(
            VesselProject.id == vessel_id,
            VesselProject.tenant_id == current_user.tenant_id,
        )
    )
    vessel = result.scalar_one_or_none()
    if vessel is None:
        return {"status": "not_found"}

    vessel.status = "pending_deletion"
    db.add(vessel)
    await db.commit()
    return {
        "status": "scheduled",
        "vessel_id": str(vessel_id),
        "message": "Vessel data scheduled for deletion after 90-day retention period.",
    }


@router.post(
    "/admin/vessels/{vessel_id}/translate-spare-names",
    summary="Translate non-English spare part names to English (Super Admin only)",
)
async def translate_spare_names(
    vessel_id: uuid.UUID,
    current_user: Annotated[User, Depends(require_role(UserRole.super_admin))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, Any]:
    """
    Find all spare parts for this vessel that contain non-English (non-ASCII)
    text in part_name, spare_model, spare_maker, or specification, then
    translate them to English using the Gemini LLM.
    """
    from app.models.spare import Spare

    result = await db.execute(
        select(Spare).where(
            Spare.vessel_id == vessel_id,
            Spare.tenant_id == current_user.tenant_id,
            Spare.is_deleted == False,
        )
    )
    all_spares = result.scalars().all()

    # Filter spares that have at least one non-ASCII field
    non_english = [
        s for s in all_spares
        if any(
            _has_non_ascii(v)
            for v in [s.part_name, s.spare_model, s.spare_maker, s.specification]
        )
    ]

    if not non_english:
        return {"status": "ok", "found": 0, "updated": 0, "message": "No non-English spare names found."}

    # Process in batches of 30 to stay within LLM token limits
    BATCH = 30
    total_updated = 0
    for i in range(0, len(non_english), BATCH):
        batch = non_english[i : i + BATCH]
        total_updated += await _translate_spare_batch(batch, db)

    return {
        "status": "ok",
        "found": len(non_english),
        "updated": total_updated,
        "message": f"Translated {total_updated} of {len(non_english)} spare records.",
    }
