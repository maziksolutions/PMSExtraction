from __future__ import annotations

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user
from app.models.user import User
from app.services.locking import lock_service

router = APIRouter()


@router.post("/{vessel_id}/locks/acquire", summary="Acquire a record lock")
async def acquire_lock(
    vessel_id: uuid.UUID,
    body: dict[str, str],
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, Any]:
    record_type = body.get("record_type", "")
    record_id = body.get("record_id", "")
    acquired = await lock_service.acquire_lock(
        record_type,
        record_id,
        str(current_user.id),
        current_user.full_name or current_user.email,
    )
    if not acquired:
        info = await lock_service.get_lock_info(record_type, record_id)
        return {
            "acquired": False,
            "locked_by": info.get("user_name") if info else "another user",
        }
    return {"acquired": True}


@router.delete(
    "/{vessel_id}/locks/{record_type}/{record_id}",
    summary="Release a record lock",
)
async def release_lock(
    vessel_id: uuid.UUID,
    record_type: str,
    record_id: str,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, Any]:
    released = await lock_service.release_lock(
        record_type, record_id, str(current_user.id)
    )
    return {"released": released}


@router.post(
    "/{vessel_id}/locks/{record_type}/{record_id}/heartbeat",
    summary="Extend a record lock TTL",
)
async def heartbeat_lock(
    vessel_id: uuid.UUID,
    record_type: str,
    record_id: str,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, Any]:
    extended = await lock_service.extend_lock(
        record_type, record_id, str(current_user.id)
    )
    return {"extended": extended}


@router.get("/{vessel_id}/locks", summary="Get all locks for a vessel")
async def get_vessel_locks(
    vessel_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, Any]:
    locks = await lock_service.get_vessel_locks(str(vessel_id))
    return {"locks": locks}
