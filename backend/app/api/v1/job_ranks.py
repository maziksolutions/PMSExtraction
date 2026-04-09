from __future__ import annotations

from typing import Annotated, Optional

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user
from app.models.job_rank import JobRank
from app.models.user import User
from app.services.job_ranks import (
    backfill_standard_job_ranks_from_audit_seed,
    backfill_job_ranks_from_existing_data,
    ensure_job_rank,
    normalize_rank_name,
    seed_rank_library_from_audit_sample,
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
    await seed_rank_library_from_audit_sample(db, tenant_id=current_user.tenant_id)
    await backfill_standard_job_ranks_from_audit_seed(db, tenant_id=current_user.tenant_id)
    await backfill_job_ranks_from_existing_data(db, tenant_id=current_user.tenant_id)
    await db.commit()

    base_where = [
        JobRank.tenant_id == current_user.tenant_id,
        JobRank.is_deleted == False,
    ]
    if search:
        base_where.append(JobRank.rank_name.ilike(f"%{search}%"))

    total_result = await db.execute(select(func.count()).select_from(JobRank).where(*base_where))
    total: int = total_result.scalar_one()

    sort_columns = {
        "rank_name": JobRank.rank_name,
        "created_at": JobRank.created_at,
    }
    order_col = sort_columns.get(sort_by, JobRank.rank_name)
    order_expr = order_col.desc() if sort_order == "desc" else order_col.asc()
    query = (
        select(JobRank)
        .where(*base_where)
        .order_by(order_expr, JobRank.rank_name.asc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    result = await db.execute(query)
    ranks = result.scalars().all()
    items = [{"id": str(rank.id), "rank_name": rank.rank_name} for rank in ranks]
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
