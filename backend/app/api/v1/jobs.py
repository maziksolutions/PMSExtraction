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
from app.services.review_workflow import (
    broadcast_activity,
    log_activity,
    sync_jobs_to_global_library,
)

router = APIRouter()


def _merge_text_values(*values: Optional[str]) -> Optional[str]:
    seen: set[str] = set()
    merged: list[str] = []
    for value in values:
        for part in (value or "").split("\n\n"):
            cleaned = part.strip()
            if not cleaned:
                continue
            key = " ".join(cleaned.lower().split())
            if key in seen:
                continue
            seen.add(key)
            merged.append(cleaned)
    return "\n\n".join(merged) if merged else None


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
    await db.flush()
    activity = await log_activity(
        db,
        tenant_id=current_user.tenant_id,
        vessel_id=vessel_id,
        user_id=current_user.id,
        action_type="job.created",
        entity_type="job",
        entity_id=job.id,
        description=f"Created job '{job.job_name}'.",
        metadata={"component_id": str(job.component_id) if job.component_id else None},
    )
    if job.qc_status == QCStatus.accepted:
        await sync_jobs_to_global_library(
            db,
            tenant_id=current_user.tenant_id,
            vessel_id=vessel_id,
            jobs=[job],
        )
    await db.commit()
    await db.refresh(job)
    await broadcast_activity(activity)
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
    original_qc_status = job.qc_status
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

    activity = None
    if update_data:
        activity = await log_activity(
            db,
            tenant_id=current_user.tenant_id,
            vessel_id=vessel_id,
            user_id=current_user.id,
            action_type="job.corrected" if job.source_manual_id else "job.modified",
            entity_type="job",
            entity_id=job.id,
            description=f"Updated job '{job.job_name}'.",
            metadata={"fields": sorted(update_data.keys())},
        )
    if job.qc_status == QCStatus.accepted and (
        original_qc_status != QCStatus.accepted or update_data
    ):
        await sync_jobs_to_global_library(
            db,
            tenant_id=current_user.tenant_id,
            vessel_id=vessel_id,
            jobs=[job],
        )
    await db.commit()
    await db.refresh(job)
    if activity:
        await broadcast_activity(activity)
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
    activities = []
    for job in jobs:
        job.qc_status = QCStatus.accepted
        db.add(job)
        activities.append(
            await log_activity(
                db,
                tenant_id=current_user.tenant_id,
                vessel_id=vessel_id,
                user_id=current_user.id,
                action_type="job.accepted",
                entity_type="job",
                entity_id=job.id,
                description=f"Accepted job '{job.job_name}'.",
            )
        )
    if jobs:
        await sync_jobs_to_global_library(
            db,
            tenant_id=current_user.tenant_id,
            vessel_id=vessel_id,
            jobs=jobs,
        )
    await db.commit()
    for activity in activities:
        await broadcast_activity(activity)
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
    activities = []
    for job in jobs:
        job.qc_status = QCStatus.rejected
        db.add(job)
        activities.append(
            await log_activity(
                db,
                tenant_id=current_user.tenant_id,
                vessel_id=vessel_id,
                user_id=current_user.id,
                action_type="job.rejected",
                entity_type="job",
                entity_id=job.id,
                description=f"Rejected job '{job.job_name}'.",
            )
        )
    await db.commit()
    for activity in activities:
        await broadcast_activity(activity)
    return {"rejected": len(jobs)}


@router.post("/{vessel_id}/jobs/bulk-update")
async def bulk_update_jobs(
    vessel_id: uuid.UUID,
    body: dict[str, Any],
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, Any]:
    ids = [uuid.UUID(value) for value in body.get("ids", []) if value]
    updates = body.get("updates", {}) or {}
    if not ids or not updates:
        return {"updated": 0}

    update_payload = JobUpdate.model_validate(updates).model_dump(exclude_unset=True)
    if not update_payload:
        return {"updated": 0}

    result = await db.execute(
        select(Job).where(Job.id.in_(ids), Job.vessel_id == vessel_id, Job.is_deleted == False)
    )
    jobs = result.scalars().all()
    activities = []
    for job in jobs:
        for field, value in update_payload.items():
            setattr(job, field, value)
        db.add(job)
        activities.append(
            await log_activity(
                db,
                tenant_id=current_user.tenant_id,
                vessel_id=vessel_id,
                user_id=current_user.id,
                action_type="job.bulk_updated",
                entity_type="job",
                entity_id=job.id,
                description=f"Bulk updated job '{job.job_name}'.",
                metadata={"fields": sorted(update_payload.keys())},
            )
        )

    accepted_jobs = [job for job in jobs if job.qc_status == QCStatus.accepted]
    if accepted_jobs:
        await sync_jobs_to_global_library(
            db,
            tenant_id=current_user.tenant_id,
            vessel_id=vessel_id,
            jobs=accepted_jobs,
        )
    await db.commit()
    for activity in activities:
        await broadcast_activity(activity)
    return {"updated": len(jobs)}


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
    activity = await log_activity(
        db,
        tenant_id=current_user.tenant_id,
        vessel_id=vessel_id,
        user_id=current_user.id,
        action_type="job.mapped",
        entity_type="job",
        entity_id=job.id,
        description=f"Linked job '{job.job_name}' to a vessel component.",
        metadata={"component_id": body["component_id"]},
    )
    await db.commit()
    await db.refresh(job)
    await broadcast_activity(activity)
    return JobOut.model_validate(job)


@router.post("/{vessel_id}/jobs/merge")
async def merge_jobs(
    vessel_id: uuid.UUID,
    body: dict[str, Any],
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> JobOut:
    ids = [uuid.UUID(value) for value in body.get("ids", []) if value]
    if len(ids) < 2:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Select at least two jobs to merge.")

    target_id_raw = body.get("target_id")
    target_id = uuid.UUID(target_id_raw) if target_id_raw else ids[0]

    result = await db.execute(
        select(Job).where(
            Job.vessel_id == vessel_id,
            Job.id.in_(ids),
            Job.is_deleted == False,
        )
    )
    jobs = list(result.scalars().all())
    if len(jobs) < 2:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Jobs not found.")

    target = next((job for job in jobs if job.id == target_id), None)
    if target is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Target job must be one of the selected jobs.")

    merged_ids: list[str] = []
    for job in jobs:
        if job.id == target.id:
            continue
        target.job_description = _merge_text_values(target.job_description, job.job_description)
        target.safety_precaution = _merge_text_values(target.safety_precaution, job.safety_precaution)
        target.tools_required = _merge_text_values(target.tools_required, job.tools_required)
        if not target.job_code and job.job_code:
            target.job_code = job.job_code
        if not target.component_id and job.component_id:
            target.component_id = job.component_id
            target.is_unmapped = False
        if not target.performing_rank and job.performing_rank:
            target.performing_rank = job.performing_rank
        if not target.verifying_rank and job.verifying_rank:
            target.verifying_rank = job.verifying_rank
        if not target.cms_id and job.cms_id:
            target.cms_id = job.cms_id
        if target.frequency is None and job.frequency is not None:
            target.frequency = job.frequency
        if target.frequency_type is None and job.frequency_type is not None:
            target.frequency_type = job.frequency_type
        target.is_critical = bool(target.is_critical or job.is_critical)
        if (job.confidence_score or 0) > (target.confidence_score or 0):
            target.confidence_score = job.confidence_score
        if not target.pdf_reference and job.pdf_reference:
            target.pdf_reference = job.pdf_reference
        if not target.source_reference and job.source_reference:
            target.source_reference = job.source_reference
        job.is_deleted = True
        db.add(job)
        merged_ids.append(str(job.id))

    target.qc_status = QCStatus.modified if target.qc_status == QCStatus.accepted else target.qc_status
    db.add(target)
    activity = await log_activity(
        db,
        tenant_id=current_user.tenant_id,
        vessel_id=vessel_id,
        user_id=current_user.id,
        action_type="job.merged",
        entity_type="job",
        entity_id=target.id,
        description=f"Merged {len(merged_ids)} jobs into '{target.job_name}'.",
        metadata={"merged_job_ids": merged_ids},
    )
    await db.commit()
    await db.refresh(target)
    await broadcast_activity(activity)
    return JobOut.model_validate(target)


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
