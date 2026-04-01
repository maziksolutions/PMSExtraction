from __future__ import annotations

import io
import uuid
from typing import Annotated, Any, List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, Query, Response, UploadFile, status
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


async def _rerun_manual_extraction(manual_ids: list[str]) -> None:
    from app.services.extractor import auto_extract_from_manual

    for manual_id in manual_ids:
        try:
            await auto_extract_from_manual(manual_id)
        except Exception:
            continue


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
    search: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(100, ge=1, le=1000),
) -> dict[str, Any]:
    from sqlalchemy import func as _func, or_
    from app.models.component import Component
    from app.models.ingestion import Manual
    await _get_vessel_or_404(vessel_id, db)
    base_where = [
        Job.vessel_id == vessel_id,
        Job.tenant_id == current_user.tenant_id,
        Job.is_deleted == False,
    ]
    if component_id:
        base_where.append(Job.component_id == component_id)
    if qc_status:
        try:
            base_where.append(Job.qc_status == QCStatus(qc_status))
        except ValueError:
            pass
    if is_critical is not None:
        base_where.append(Job.is_critical == is_critical)
    if is_unmapped is not None:
        base_where.append(Job.is_unmapped == is_unmapped)
    if frequency_type:
        try:
            base_where.append(Job.frequency_type == FrequencyType(frequency_type))
        except ValueError:
            pass
    if search:
        base_where.append(
            or_(
                Job.job_name.ilike(f"%{search}%"),
                Job.job_code.ilike(f"%{search}%"),
            )
        )

    total_result = await db.execute(select(_func.count()).select_from(Job).where(*base_where))
    total: int = total_result.scalar_one()

    query = select(Job).where(*base_where).order_by(Job.job_name).offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(query)
    jobs = result.scalars().all()

    component_ids = {job.component_id for job in jobs if job.component_id}
    manual_ids = {job.source_manual_id for job in jobs if job.source_manual_id}

    component_lookup: dict[uuid.UUID, Component] = {}
    manual_lookup: dict[uuid.UUID, Manual] = {}

    if component_ids:
        component_result = await db.execute(select(Component).where(Component.id.in_(component_ids)))
        component_lookup = {component.id: component for component in component_result.scalars().all()}
    if manual_ids:
        manual_result = await db.execute(select(Manual).where(Manual.id.in_(manual_ids)))
        manual_lookup = {manual.id: manual for manual in manual_result.scalars().all()}

    items = []
    for job in jobs:
        payload = JobOut.model_validate(job).model_dump()
        component = component_lookup.get(job.component_id) if job.component_id else None
        manual = manual_lookup.get(job.source_manual_id) if job.source_manual_id else None
        payload.update(
            {
                "component_name": component.component_name if component else None,
                "component_maker": component.maker if component else None,
                "component_model": component.model if component else None,
                "source_manual_name": manual.original_filename if manual else None,
            }
        )
        items.append(payload)

    return {"items": items, "page": page, "page_size": page_size, "total": total}


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
    background_tasks: BackgroundTasks,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, Any]:
    await _get_vessel_or_404(vessel_id, db)
    from app.models.ingestion import Manual

    result = await db.execute(
        select(Manual).where(
            Manual.vessel_id == vessel_id,
            Manual.tenant_id == current_user.tenant_id,
            Manual.is_deleted == False,
            Manual.pages_with_jobs.isnot(None),
            Manual.pages_with_jobs != "",
        )
    )
    manuals = result.scalars().all()
    manual_ids = [str(manual.id) for manual in manuals]
    if not manual_ids:
        return {"started": False, "total": 0, "message": "No manuals with job page references found."}

    background_tasks.add_task(_rerun_manual_extraction, manual_ids)
    return {"started": True, "total": len(manual_ids), "message": "Job extraction started."}


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
