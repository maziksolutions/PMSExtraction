from __future__ import annotations

import uuid
from typing import Annotated, Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user
from app.models.job import Job
from app.models.missing_manual import MissingManualGap
from app.models.standard_jobs import (
    ClassSociety,
    MatchStatus,
    StandardJob,
    StandardJobMatch,
    VesselTypeTemplate,
)
from app.models.user import User
from app.models.vessel import VesselProject

router = APIRouter()


async def _get_vessel_or_404(vessel_id: uuid.UUID, db: AsyncSession) -> VesselProject:
    result = await db.execute(
        select(VesselProject).where(
            VesselProject.id == vessel_id, VesselProject.is_deleted == False
        )
    )
    vessel = result.scalar_one_or_none()
    if vessel is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Vessel not found")
    return vessel


@router.get("/standard-jobs", summary="List standard jobs library")
async def list_standard_jobs(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    class_society: Optional[str] = Query(None),
    machinery_type: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
) -> dict[str, Any]:
    query = select(StandardJob).where(StandardJob.is_deleted == False)
    if class_society:
        try:
            query = query.where(StandardJob.class_society == ClassSociety(class_society))
        except ValueError:
            pass
    if machinery_type:
        query = query.where(StandardJob.machinery_type == machinery_type)
    query = query.offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(query)
    jobs = result.scalars().all()
    return {
        "items": [
            {
                "id": str(j.id),
                "class_society": j.class_society.value,
                "machinery_type": j.machinery_type,
                "job_name": j.job_name,
                "job_description": j.job_description,
                "frequency": j.frequency,
                "frequency_type": j.frequency_type.value if j.frequency_type else None,
                "is_critical": j.is_critical,
                "library_reference": j.library_reference,
            }
            for j in jobs
        ],
        "page": page,
    }


@router.get("/standard-jobs/vessel-types", summary="List vessel type templates")
async def list_vessel_types(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, Any]:
    result = await db.execute(
        select(VesselTypeTemplate).where(VesselTypeTemplate.is_deleted == False)
    )
    templates = result.scalars().all()
    return {
        "items": [
            {
                "id": str(t.id),
                "vessel_type": t.vessel_type,
                "machinery_group": t.machinery_group,
                "machinery_name": t.machinery_name,
                "is_mandatory": t.is_mandatory,
                "extraction_types": t.extraction_types,
            }
            for t in templates
        ]
    }


@router.post("/vessels/{vessel_id}/standard-jobs/run-comparison", summary="Run standard job matching")
async def run_comparison(
    vessel_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, Any]:
    vessel = await _get_vessel_or_404(vessel_id, db)

    # Get all standard jobs
    std_jobs_result = await db.execute(
        select(StandardJob).where(StandardJob.is_deleted == False)
    )
    std_jobs = std_jobs_result.scalars().all()

    # Get vessel jobs
    vessel_jobs_result = await db.execute(
        select(Job).where(
            Job.vessel_id == vessel_id,
            Job.is_deleted == False,
        )
    )
    vessel_jobs = vessel_jobs_result.scalars().all()
    vessel_job_names = {j.job_name.lower() for j in vessel_jobs}
    vessel_jobs_dict = {j.job_name.lower(): j for j in vessel_jobs}

    matches_created = 0
    for std_job in std_jobs:
        std_name_lower = std_job.job_name.lower()

        # Check for existing match
        existing = await db.execute(
            select(StandardJobMatch).where(
                StandardJobMatch.vessel_id == vessel_id,
                StandardJobMatch.standard_job_id == std_job.id,
                StandardJobMatch.is_deleted == False,
            )
        )
        if existing.scalar_one_or_none():
            continue

        # Simple name matching
        if std_name_lower in vessel_job_names:
            matched_job = vessel_jobs_dict[std_name_lower]
            match_status = MatchStatus.matched
            match_score = 100
            matched_job_id = matched_job.id
        else:
            # Check partial match (contains)
            partial = None
            for vj_name, vj in vessel_jobs_dict.items():
                if std_name_lower in vj_name or vj_name in std_name_lower:
                    partial = vj
                    break
            if partial:
                match_status = MatchStatus.partial
                match_score = 60
                matched_job_id = partial.id
            else:
                match_status = MatchStatus.not_found
                match_score = 0
                matched_job_id = None

        match = StandardJobMatch(
            tenant_id=current_user.tenant_id,
            vessel_id=vessel_id,
            standard_job_id=std_job.id,
            matched_job_id=matched_job_id,
            match_status=match_status,
            match_score=match_score,
        )
        db.add(match)
        matches_created += 1

    await db.commit()
    return {"status": "completed", "matches_created": matches_created}


@router.get("/vessels/{vessel_id}/standard-jobs/matches", summary="Get match results")
async def get_matches(
    vessel_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    match_status: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
) -> dict[str, Any]:
    await _get_vessel_or_404(vessel_id, db)
    query = select(StandardJobMatch).where(
        StandardJobMatch.vessel_id == vessel_id,
        StandardJobMatch.is_deleted == False,
    )
    if match_status:
        try:
            query = query.where(StandardJobMatch.match_status == MatchStatus(match_status))
        except ValueError:
            pass
    query = query.offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(query)
    matches = result.scalars().all()
    return {
        "items": [
            {
                "id": str(m.id),
                "standard_job_id": str(m.standard_job_id),
                "matched_job_id": str(m.matched_job_id) if m.matched_job_id else None,
                "match_status": m.match_status.value,
                "match_score": m.match_score,
                "not_applicable_reason": m.not_applicable_reason,
            }
            for m in matches
        ],
        "page": page,
    }


@router.patch("/vessels/{vessel_id}/standard-jobs/matches/{match_id}", summary="Update match status")
async def update_match(
    vessel_id: uuid.UUID,
    match_id: uuid.UUID,
    body: dict[str, str],
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, Any]:
    result = await db.execute(
        select(StandardJobMatch).where(
            StandardJobMatch.id == match_id,
            StandardJobMatch.vessel_id == vessel_id,
            StandardJobMatch.is_deleted == False,
        )
    )
    match = result.scalar_one_or_none()
    if match is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Match not found")

    if "match_status" in body:
        try:
            match.match_status = MatchStatus(body["match_status"])
        except ValueError:
            pass
    if "not_applicable_reason" in body:
        match.not_applicable_reason = body["not_applicable_reason"]

    db.add(match)
    await db.commit()
    return {"id": str(match.id), "match_status": match.match_status.value}


@router.post("/vessels/{vessel_id}/standard-jobs/import/{standard_job_id}", summary="Import standard job")
async def import_standard_job(
    vessel_id: uuid.UUID,
    standard_job_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, Any]:
    await _get_vessel_or_404(vessel_id, db)

    std_result = await db.execute(
        select(StandardJob).where(
            StandardJob.id == standard_job_id, StandardJob.is_deleted == False
        )
    )
    std_job = std_result.scalar_one_or_none()
    if std_job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Standard job not found")

    from app.models.component import QCStatus

    new_job = Job(
        tenant_id=current_user.tenant_id,
        vessel_id=vessel_id,
        job_name=std_job.job_name,
        job_description=std_job.job_description,
        frequency=std_job.frequency,
        frequency_type=std_job.frequency_type,
        is_critical=std_job.is_critical,
        source_reference=std_job.library_reference,
        qc_status=QCStatus.accepted,
    )
    db.add(new_job)
    await db.commit()
    await db.refresh(new_job)
    return {"status": "imported", "job_id": str(new_job.id)}


@router.get("/vessels/{vessel_id}/missing-manuals", summary="Missing manual gaps")
async def get_missing_manuals(
    vessel_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, Any]:
    await _get_vessel_or_404(vessel_id, db)
    result = await db.execute(
        select(MissingManualGap).where(
            MissingManualGap.vessel_id == vessel_id,
            MissingManualGap.is_deleted == False,
        )
    )
    gaps = result.scalars().all()
    return {
        "items": [
            {
                "id": str(g.id),
                "machinery_group": g.machinery_group,
                "machinery_name": g.machinery_name,
                "is_mandatory": g.is_mandatory,
                "gap_status": g.gap_status,
                "notes": g.notes,
            }
            for g in gaps
        ]
    }


@router.patch("/vessels/{vessel_id}/missing-manuals/{gap_id}", summary="Update missing manual gap status")
async def update_missing_manual_gap(
    vessel_id: uuid.UUID,
    gap_id: uuid.UUID,
    body: dict[str, str],
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, Any]:
    result = await db.execute(
        select(MissingManualGap).where(
            MissingManualGap.id == gap_id,
            MissingManualGap.vessel_id == vessel_id,
            MissingManualGap.is_deleted == False,
        )
    )
    gap = result.scalar_one_or_none()
    if gap is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Gap not found")

    if "gap_status" in body:
        gap.gap_status = body["gap_status"]
    if "notes" in body:
        gap.notes = body["notes"]

    db.add(gap)
    await db.commit()
    return {"id": str(gap.id), "gap_status": gap.gap_status}
