from __future__ import annotations

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import require_role
from app.models.audit import AuditLog
from app.models.user import User, UserRole

router = APIRouter()


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
