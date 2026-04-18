from __future__ import annotations

import uuid

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User, UserRole
from app.models.vessel import VesselProject, VesselProjectUser


async def get_accessible_vessel_or_404(
    *,
    vessel_id: uuid.UUID,
    current_user: User,
    db: AsyncSession,
) -> VesselProject:
    result = await db.execute(
        select(VesselProject).where(
            VesselProject.id == vessel_id,
            VesselProject.is_deleted == False,
        )
    )
    vessel = result.scalar_one_or_none()
    if vessel is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Vessel not found")

    if vessel.tenant_id != current_user.tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Vessel not found")

    if current_user.role == UserRole.super_admin:
        return vessel

    assignment_result = await db.execute(
        select(VesselProjectUser.id).where(
            VesselProjectUser.vessel_id == vessel_id,
            VesselProjectUser.user_id == current_user.id,
            VesselProjectUser.is_deleted == False,
        )
    )
    assignment = assignment_result.scalar_one_or_none()
    if assignment is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied for this vessel")

    return vessel
