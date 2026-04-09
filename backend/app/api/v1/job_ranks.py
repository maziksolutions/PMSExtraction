from __future__ import annotations

from typing import Annotated, Optional

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user
from app.models.user import User
from app.services.job_ranks import (
    ensure_job_rank,
    list_rank_names_from_seed_and_existing_data,
    normalize_rank_name,
)

router = APIRouter()


@router.get("/job-ranks", summary="List job ranks")
async def list_job_ranks(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    search: Optional[str] = Query(None),
    sort_by: str = Query("rank_name"),
    sort_order: str = Query("asc", pattern="^(asc|desc)$"),
    page: int = Query(1, ge=1),
    page_size: int = Query(200, ge=1, le=1000),
) -> dict[str, object]:
    rank_names = await list_rank_names_from_seed_and_existing_data(
        db,
        tenant_id=current_user.tenant_id,
    )

    if search:
        needle = search.strip().lower()
        rank_names = [rank_name for rank_name in rank_names if needle in rank_name.lower()]

    reverse = sort_order == "desc"
    rank_names = sorted(rank_names, key=lambda value: value.lower(), reverse=reverse)
    total = len(rank_names)
    start = (page - 1) * page_size
    end = start + page_size
    items = [
        {"id": normalize_rank_name(rank_name) or rank_name, "rank_name": rank_name}
        for rank_name in rank_names[start:end]
    ]
    return {"items": items, "page": page, "page_size": page_size, "total": total}


@router.post("/job-ranks", summary="Add a new job rank", status_code=status.HTTP_201_CREATED)
async def create_job_rank(
    body: dict[str, str],
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, str]:
    rank_name = normalize_rank_name(body.get("rank_name"))
    await ensure_job_rank(db, tenant_id=current_user.tenant_id, rank_name=rank_name)
    await db.commit()
    return {"rank_name": rank_name or ""}
