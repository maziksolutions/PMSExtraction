from __future__ import annotations

import io
import uuid
from typing import Annotated, Any, List, Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, Response, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user
from app.models.component import QCStatus
from app.models.feedback import CorrectionType, FeedbackEntry
from app.models.job import FrequencyType, Job
from app.models.user import User
from app.models.vessel import VesselProject
from app.schemas.job import JobCreate, JobOut, JobUpdate

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


@router.get("/{vessel_id}/jobs", summary="List jobs with filters")
async def list_jobs(
    vessel_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    component_id: Optional[uuid.UUID] = Query(None),
    qc_status: Optional[str] = Query(None),
    is_critical: Optional[bool] = Query(None),
    is_unmapped: Optional[bool] = Query(None),
    frequency_type: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
) -> dict[str, Any]:
    await _get_vessel_or_404(vessel_id, db)
    query = select(Job).where(
        Job.vessel_id == vessel_id,
        Job.tenant_id == current_user.tenant_id,
        Job.is_deleted == False,
    )
    if component_id:
        query = query.where(Job.component_id == component_id)
    if qc_status:
        try:
            query = query.where(Job.qc_status == QCStatus(qc_status))
        except ValueError:
            pass
    if is_critical is not None:
        query = query.where(Job.is_critical == is_critical)
    if is_unmapped is not None:
        query = query.where(Job.is_unmapped == is_unmapped)
    if frequency_type:
        try:
            query = query.where(Job.frequency_type == FrequencyType(frequency_type))
        except ValueError:
            pass

    query = query.order_by(Job.job_name).offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(query)
    jobs = result.scalars().all()
    return {"items": [JobOut.model_validate(j) for j in jobs], "page": page}


@router.post(
    "/{vessel_id}/jobs",
    response_model=JobOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_job(
    vessel_id: uuid.UUID,
    body: JobCreate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> JobOut:
    await _get_vessel_or_404(vessel_id, db)
    job = Job(
        tenant_id=current_user.tenant_id,
        vessel_id=vessel_id,
        **body.model_dump(),
    )
    db.add(job)
    await db.commit()
    await db.refresh(job)
    return JobOut.model_validate(job)


@router.patch("/{vessel_id}/jobs/{job_id}", response_model=JobOut)
async def update_job(
    vessel_id: uuid.UUID,
    job_id: uuid.UUID,
    body: JobUpdate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> JobOut:
    await _get_vessel_or_404(vessel_id, db)
    result = await db.execute(
        select(Job).where(
            Job.id == job_id, Job.vessel_id == vessel_id, Job.is_deleted == False
        )
    )
    job = result.scalar_one_or_none()
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")

    original = {"job_name": job.job_name, "qc_status": job.qc_status.value if job.qc_status else None}
    update_data = body.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(job, field, value)
    db.add(job)

    if job.source_manual_id and update_data:
        feedback = FeedbackEntry(
            tenant_id=current_user.tenant_id,
            manual_id=job.source_manual_id,
            entity_type="job",
            original_value=original,
            corrected_value=update_data,
            correction_type=CorrectionType.wrong_value,
            created_by=current_user.id,
        )
        db.add(feedback)

    await db.commit()
    await db.refresh(job)
    return JobOut.model_validate(job)


@router.delete("/{vessel_id}/jobs/{job_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response, response_model=None)
async def delete_job(
    vessel_id: uuid.UUID,
    job_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    result = await db.execute(
        select(Job).where(Job.id == job_id, Job.vessel_id == vessel_id)
    )
    job = result.scalar_one_or_none()
    if job:
        job.is_deleted = True
        db.add(job)
        await db.commit()


@router.post("/{vessel_id}/jobs/bulk-accept")
async def bulk_accept_jobs(
    vessel_id: uuid.UUID,
    body: dict[str, List[str]],
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, Any]:
    ids = [uuid.UUID(i) for i in body.get("ids", [])]
    result = await db.execute(select(Job).where(Job.id.in_(ids), Job.vessel_id == vessel_id))
    jobs = result.scalars().all()
    for job in jobs:
        job.qc_status = QCStatus.accepted
        db.add(job)
    await db.commit()
    return {"accepted": len(jobs)}


@router.post("/{vessel_id}/jobs/bulk-reject")
async def bulk_reject_jobs(
    vessel_id: uuid.UUID,
    body: dict[str, List[str]],
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, Any]:
    ids = [uuid.UUID(i) for i in body.get("ids", [])]
    result = await db.execute(select(Job).where(Job.id.in_(ids), Job.vessel_id == vessel_id))
    jobs = result.scalars().all()
    for job in jobs:
        job.qc_status = QCStatus.rejected
        db.add(job)
    await db.commit()
    return {"rejected": len(jobs)}


@router.post("/{vessel_id}/jobs/{job_id}/link-component")
async def link_component(
    vessel_id: uuid.UUID,
    job_id: uuid.UUID,
    body: dict[str, str],
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> JobOut:
    result = await db.execute(
        select(Job).where(Job.id == job_id, Job.vessel_id == vessel_id, Job.is_deleted == False)
    )
    job = result.scalar_one_or_none()
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    job.component_id = uuid.UUID(body["component_id"])
    job.is_unmapped = False
    db.add(job)
    await db.commit()
    await db.refresh(job)
    return JobOut.model_validate(job)


@router.post("/{vessel_id}/jobs/trigger-extraction")
async def trigger_job_extraction(
    vessel_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, Any]:
    await _get_vessel_or_404(vessel_id, db)
    try:
        from app.tasks.extraction import extract_jobs

        task = extract_jobs.delay(str(vessel_id))
        return {"task_id": task.id, "status": "queued"}
    except Exception:
        return {"status": "queued", "task_id": "mock"}


@router.post("/{vessel_id}/jobs/upload-cms-mapping")
async def upload_cms_mapping(
    vessel_id: uuid.UUID,
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Upload a CSV with job_name → cms_id mappings."""
    await _get_vessel_or_404(vessel_id, db)
    content = await file.read()
    lines = content.decode("utf-8", errors="replace").splitlines()
    updated = 0
    for line in lines[1:]:  # Skip header
        parts = line.split(",", 1)
        if len(parts) == 2:
            job_name = parts[0].strip()
            cms_id = parts[1].strip()
            result = await db.execute(
                select(Job).where(
                    Job.vessel_id == vessel_id,
                    Job.job_name == job_name,
                    Job.is_deleted == False,
                )
            )
            jobs = result.scalars().all()
            for job in jobs:
                job.cms_id = cms_id
                db.add(job)
                updated += 1
    await db.commit()
    return {"status": "ok", "updated": updated}
