from __future__ import annotations

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user
from app.models.activity import ActivityEntry
from app.models.user import User

router = APIRouter()


@router.get("/{vessel_id}/activity", summary="Get paginated activity feed for a vessel")
async def get_activity(
    vessel_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    limit: int = Query(50, ge=1, le=200),
) -> dict[str, Any]:
    result = await db.execute(
        select(ActivityEntry)
        .where(
            ActivityEntry.vessel_id == vessel_id,
            ActivityEntry.tenant_id == current_user.tenant_id,
            ActivityEntry.is_deleted == False,
        )
        .order_by(ActivityEntry.created_at.desc())
        .limit(limit)
    )
    entries = result.scalars().all()
    return {
        "items": [
            {
                "id": str(e.id),
                "action_type": e.action_type,
                "entity_type": e.entity_type,
                "entity_id": str(e.entity_id),
                "description": e.description,
                "metadata": e.metadata_json,
                "created_at": e.created_at.isoformat(),
                "user_id": str(e.user_id),
            }
            for e in entries
        ]
    }
