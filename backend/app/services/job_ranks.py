from __future__ import annotations

import uuid
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.job import Job
from app.models.job_rank import JobRank
from app.models.standard_jobs import StandardJob


def normalize_rank_name(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    cleaned = " ".join(str(value).split()).strip()
    return cleaned or None


def _rank_key(value: Optional[str]) -> Optional[str]:
    cleaned = normalize_rank_name(value)
    return cleaned.lower() if cleaned else None


async def ensure_job_rank(db: AsyncSession, *, tenant_id: uuid.UUID, rank_name: Optional[str]) -> None:
    cleaned = normalize_rank_name(rank_name)
    if not cleaned:
        return
    key = _rank_key(cleaned)
    if not key:
        return
    result = await db.execute(
        select(JobRank).where(
            JobRank.tenant_id == tenant_id,
            JobRank.normalized_name == key,
            JobRank.is_deleted == False,
        )
    )
    existing = result.scalar_one_or_none()
    if existing:
        if existing.rank_name != cleaned:
            existing.rank_name = cleaned
            db.add(existing)
        return
    db.add(
        JobRank(
            tenant_id=tenant_id,
            rank_name=cleaned,
            normalized_name=key,
        )
    )


async def infer_rank_from_component(
    db: AsyncSession,
    *,
    vessel_id: uuid.UUID,
    component_id: Optional[uuid.UUID],
) -> Optional[str]:
    if not component_id:
        return None
    result = await db.execute(
        select(
            Job.performing_rank,
            func.count(Job.id).label("rank_count"),
        )
        .where(
            Job.vessel_id == vessel_id,
            Job.component_id == component_id,
            Job.is_deleted == False,
            Job.performing_rank.is_not(None),
        )
        .group_by(Job.performing_rank)
        .order_by(func.count(Job.id).desc())
        .limit(1)
    )
    row = result.first()
    return row[0] if row else None


async def backfill_job_ranks_from_existing_data(
    db: AsyncSession,
    *,
    tenant_id: uuid.UUID,
) -> None:
    rank_queries = [
        select(Job.performing_rank).where(
            Job.tenant_id == tenant_id,
            Job.is_deleted == False,
            Job.performing_rank.is_not(None),
        ),
        select(Job.verifying_rank).where(
            Job.tenant_id == tenant_id,
            Job.is_deleted == False,
            Job.verifying_rank.is_not(None),
        ),
        select(StandardJob.performing_rank).where(
            StandardJob.tenant_id == tenant_id,
            StandardJob.is_deleted == False,
            StandardJob.performing_rank.is_not(None),
        ),
        select(StandardJob.verifying_rank).where(
            StandardJob.tenant_id == tenant_id,
            StandardJob.is_deleted == False,
            StandardJob.verifying_rank.is_not(None),
        ),
    ]

    for query in rank_queries:
        result = await db.execute(query.distinct())
        for (rank_name,) in result.all():
            await ensure_job_rank(db, tenant_id=tenant_id, rank_name=rank_name)
