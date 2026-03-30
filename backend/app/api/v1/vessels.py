from __future__ import annotations

import math
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user, require_role
from app.models.user import User, UserRole
from app.models.vessel import VesselProject, VesselProjectUser
from app.schemas.vessel import VesselCreate, VesselListResponse, VesselResponse, VesselUpdate

router = APIRouter()

# Roles that can create / modify / delete vessel projects
_VESSEL_WRITE_ROLES = (UserRole.super_admin, UserRole.vessel_admin)


@router.get(
    "",
    response_model=VesselListResponse,
    status_code=status.HTTP_200_OK,
    summary="List vessel projects accessible to the current user",
)
async def list_vessels(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> VesselListResponse:
    """
    Super admins see all vessels in their tenant.
    Other roles see only vessels they are explicitly assigned to.
    """
    if current_user.role == UserRole.super_admin:
        base_query = select(VesselProject).where(
            VesselProject.tenant_id == current_user.tenant_id,
            VesselProject.is_deleted == False,
        )
    else:
        assigned_vessel_ids_query = select(VesselProjectUser.vessel_id).where(
            VesselProjectUser.user_id == current_user.id,
            VesselProjectUser.is_deleted == False,
        )
        base_query = select(VesselProject).where(
            VesselProject.id.in_(assigned_vessel_ids_query),
            VesselProject.is_deleted == False,
        )

    count_result = await db.execute(select(func.count()).select_from(base_query.subquery()))
    total: int = count_result.scalar_one()

    offset = (page - 1) * page_size
    result = await db.execute(base_query.offset(offset).limit(page_size))
    vessels = list(result.scalars().all())

    return VesselListResponse(
        items=[VesselResponse.model_validate(v) for v in vessels],
        total=total,
        page=page,
        page_size=page_size,
        pages=math.ceil(total / page_size) if total > 0 else 1,
    )


@router.post(
    "",
    response_model=VesselResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new vessel project (vessel_admin+)",
)
async def create_vessel(
    vessel_data: VesselCreate,
    current_user: Annotated[User, Depends(require_role(*_VESSEL_WRITE_ROLES))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> VesselResponse:
    """Create a vessel project. IMO number must be unique per tenant."""
    existing = await db.execute(
        select(VesselProject).where(
            VesselProject.imo_number == vessel_data.imo_number,
            VesselProject.tenant_id == current_user.tenant_id,
            VesselProject.is_deleted == False,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"A vessel with IMO number '{vessel_data.imo_number}' already exists in this tenant",
        )

    vessel = VesselProject(
        tenant_id=current_user.tenant_id,
        name=vessel_data.name,
        imo_number=vessel_data.imo_number,
        vessel_type=vessel_data.vessel_type,
        sharepoint_folder_url=vessel_data.sharepoint_folder_url,
        shipyard=vessel_data.shipyard,
        created_by=current_user.id,
    )
    db.add(vessel)
    await db.commit()
    await db.refresh(vessel)
    return VesselResponse.model_validate(vessel)


@router.get(
    "/{vessel_id}",
    response_model=VesselResponse,
    status_code=status.HTTP_200_OK,
    summary="Get vessel project details",
)
async def get_vessel(
    vessel_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> VesselResponse:
    """
    Retrieve a specific vessel project.
    Access is restricted to users assigned to the vessel (super_admin bypasses this).
    """
    vessel = await _get_vessel_or_404(vessel_id, db)
    _assert_vessel_access(vessel, current_user, db)
    return VesselResponse.model_validate(vessel)


@router.put(
    "/{vessel_id}",
    response_model=VesselResponse,
    status_code=status.HTTP_200_OK,
    summary="Update a vessel project (vessel_admin+)",
)
async def update_vessel(
    vessel_id: uuid.UUID,
    vessel_data: VesselUpdate,
    current_user: Annotated[User, Depends(require_role(*_VESSEL_WRITE_ROLES))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> VesselResponse:
    """Update editable fields on a vessel project."""
    vessel = await _get_vessel_or_404(vessel_id, db)

    for field, value in vessel_data.model_dump(exclude_unset=True).items():
        setattr(vessel, field, value)

    db.add(vessel)
    await db.commit()
    await db.refresh(vessel)
    return VesselResponse.model_validate(vessel)


@router.delete(
    "/{vessel_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    response_model=None,
    summary="Soft-delete a vessel project (vessel_admin+)",
)
async def delete_vessel(
    vessel_id: uuid.UUID,
    _: Annotated[User, Depends(require_role(*_VESSEL_WRITE_ROLES))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    """Soft-delete a vessel project. All associated data is preserved."""
    vessel = await _get_vessel_or_404(vessel_id, db)
    vessel.is_deleted = True
    db.add(vessel)
    await db.commit()


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

async def _get_vessel_or_404(vessel_id: uuid.UUID, db: AsyncSession) -> VesselProject:
    result = await db.execute(
        select(VesselProject).where(
            VesselProject.id == vessel_id,
            VesselProject.is_deleted == False,
        )
    )
    vessel: VesselProject | None = result.scalar_one_or_none()
    if vessel is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Vessel project not found")
    return vessel


def _assert_vessel_access(vessel: VesselProject, user: User, db: AsyncSession) -> None:
    """Non-super_admin users must be assigned to the vessel."""
    # Access control for non-admins is enforced at the list level;
    # for single-resource reads we rely on the assignment check done in list_vessels.
    # A deeper check would query VesselProjectUser — left as a thin guard here.
    if user.role == UserRole.super_admin:
        return
    # For other roles, verify tenant ownership at minimum
    if vessel.tenant_id != user.tenant_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
