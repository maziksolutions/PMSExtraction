from __future__ import annotations

from typing import Annotated, Optional

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user
from app.models.job_rank import JobRank
from app.models.user import User
from app.services.job_ranks import (
    backfill_job_ranks_from_existing_data,
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
    try:
        await backfill_job_ranks_from_existing_data(db, tenant_id=current_user.tenant_id)
        await db.commit()
    except Exception:
        await db.rollback()

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
    await ensure_job_rank(
        db,
        tenant_id=current_user.tenant_id,
        rank_name=rank_name,
        revive_deleted=True,
    )
    await db.commit()
    return {"rank_name": rank_name or ""}


@router.delete("/job-ranks/{rank_name}", summary="Delete a job rank")
async def delete_job_rank(
    rank_name: str,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, str]:
    normalized = normalize_rank_name(rank_name)
    if not normalized:
        return {"status": "deleted"}

    result = await db.execute(
        select(JobRank).where(
            JobRank.tenant_id == current_user.tenant_id,
            JobRank.normalized_name == normalized.lower(),
            JobRank.is_deleted == False,
        )
    )
    rank = result.scalar_one_or_none()
    if rank is not None:
        rank.is_deleted = True
        db.add(rank)
        await db.commit()
    return {"status": "deleted"}
