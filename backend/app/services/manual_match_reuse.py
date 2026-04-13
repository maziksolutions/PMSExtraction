from __future__ import annotations

import uuid
from typing import Any, Optional

from sqlalchemy import select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.component import Component, QCStatus
from app.models.ingestion import Manual
from app.models.job import Job
from app.models.spare import Spare


def _is_exact_manual_match(match_confidence: Optional[str], match_score: Any) -> bool:
    confidence = (match_confidence or "").strip().lower()
    if confidence == "exact":
        return True
    try:
        numeric_score = float(match_score or 0)
        if numeric_score > 1:
            return numeric_score >= 99.9
        return numeric_score >= 0.999
    except (TypeError, ValueError):
        return False


def _review_note(matched_manual_name: str) -> str:
    return (
        f"Copied from matched manual '{matched_manual_name}'. "
        "Review page references against the current manual before acceptance."
    )


def _append_note(value: Optional[str], note: str) -> str:
    base = (value or "").strip()
    if not base:
        return note
    if note in base:
        return base
    return f"{base}\n\n{note}"


def _manual_source_reference(manual_name: str, page_reference: int | None, exact_match: bool) -> str:
    if exact_match and page_reference:
        return f"{manual_name} (p.{page_reference})"
    return manual_name


async def find_best_manual_match_for_source(
    db: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    source_manual_id: uuid.UUID,
) -> Optional[dict[str, Any]]:
    result = await db.execute(
        text(
            "SELECT mm.id, mm.source_manual_id, mm.matched_manual_id, mm.match_score, mm.match_confidence "
            "FROM manual_matches mm "
            "WHERE mm.tenant_id = :tid "
            "  AND mm.source_manual_id = :smid "
            "  AND mm.is_deleted = false "
            "ORDER BY "
            "  CASE mm.match_confidence "
            "    WHEN 'exact' THEN 4 "
            "    WHEN 'high' THEN 3 "
            "    WHEN 'medium' THEN 2 "
            "    WHEN 'low' THEN 1 "
            "    ELSE 0 "
            "  END DESC, "
            "  mm.match_score DESC, "
            "  mm.created_at DESC "
            "LIMIT 1"
        ),
        {"tid": str(tenant_id), "smid": str(source_manual_id)},
    )
    row = result.mappings().one_or_none()
    return dict(row) if row else None


async def reuse_records_from_matched_manual(
    db: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    vessel_id: uuid.UUID,
    source_manual: Manual,
    matched_manual: Manual,
    match_confidence: Optional[str],
    match_score: Any = None,
    auto_merge_components: bool = False,
) -> dict[str, Any]:
    exact_match = _is_exact_manual_match(match_confidence, match_score)
    note = _review_note(matched_manual.original_filename)

    await db.execute(
        update(Component)
        .where(
            Component.vessel_id == vessel_id,
            Component.tenant_id == tenant_id,
            Component.source_manual_id == source_manual.id,
            Component.qc_status == QCStatus.pending,
            Component.is_deleted == False,
        )
        .values(is_deleted=True)
    )
    await db.execute(
        update(Job)
        .where(
            Job.vessel_id == vessel_id,
            Job.tenant_id == tenant_id,
            Job.source_manual_id == source_manual.id,
            Job.qc_status == QCStatus.pending,
            Job.is_deleted == False,
        )
        .values(is_deleted=True)
    )
    await db.execute(
        update(Spare)
        .where(
            Spare.vessel_id == vessel_id,
            Spare.tenant_id == tenant_id,
            Spare.source_manual_id == source_manual.id,
            Spare.qc_status == QCStatus.pending,
            Spare.is_deleted == False,
        )
        .values(is_deleted=True)
    )

    comp_result = await db.execute(
        select(Component).where(
            Component.vessel_id == matched_manual.vessel_id,
            Component.tenant_id == tenant_id,
            Component.source_manual_id == matched_manual.id,
            Component.qc_status == QCStatus.accepted,
            Component.is_deleted == False,
        )
    )
    source_components = list(comp_result.scalars().all())

    component_id_map: dict[uuid.UUID, uuid.UUID] = {}
    copied_components = 0
    for component in source_components:
        copied = Component(
            tenant_id=tenant_id,
            vessel_id=vessel_id,
            group1=component.group1,
            group2=component.group2,
            main_machinery=component.main_machinery,
            component_name=component.component_name,
            maker=component.maker,
            model=component.model,
            serial_number=component.serial_number,
            specification=component.specification,
            location=component.location,
            machinery_particulars=component.machinery_particulars,
            source_manual_id=source_manual.id,
            page_reference=component.page_reference if exact_match else None,
            confidence_score=component.confidence_score,
            is_critical=component.is_critical,
            criticality=component.criticality,
            qc_status=QCStatus.pending,
            is_unmapped=True,
            extraction_notes=component.extraction_notes if exact_match else _append_note(component.extraction_notes, note),
            job_pages=component.job_pages if exact_match else None,
            spare_pages=component.spare_pages if exact_match else None,
            pdf_reference=source_manual.original_filename,
        )
        db.add(copied)
        await db.flush()
        component_id_map[component.id] = copied.id
        copied_components += 1

    job_result = await db.execute(
        select(Job).where(
            Job.vessel_id == matched_manual.vessel_id,
            Job.tenant_id == tenant_id,
            Job.source_manual_id == matched_manual.id,
            Job.qc_status == QCStatus.accepted,
            Job.is_deleted == False,
        )
    )
    source_jobs = list(job_result.scalars().all())

    copied_jobs = 0
    for job in source_jobs:
        copied_job = Job(
            tenant_id=tenant_id,
            vessel_id=vessel_id,
            component_id=component_id_map.get(job.component_id) if job.component_id else None,
            job_name=job.job_name,
            job_code=job.job_code,
            job_description=job.job_description if exact_match else _append_note(job.job_description, note),
            safety_precaution=job.safety_precaution,
            tools_required=job.tools_required,
            performing_rank=job.performing_rank,
            verifying_rank=job.verifying_rank,
            frequency=job.frequency,
            frequency_type=job.frequency_type,
            initial_due=job.initial_due,
            initial_frequency_type=job.initial_frequency_type,
            cms_id=job.cms_id,
            page_reference=job.page_reference if exact_match else None,
            pdf_reference=source_manual.original_filename,
            source_reference=_manual_source_reference(
                source_manual.original_filename,
                job.page_reference if exact_match else None,
                exact_match,
            ),
            is_critical=job.is_critical,
            qc_status=QCStatus.pending,
            is_unmapped=job.component_id is None,
            source_manual_id=source_manual.id,
            confidence_score=job.confidence_score,
        )
        db.add(copied_job)
        copied_jobs += 1

    spare_result = await db.execute(
        select(Spare).where(
            Spare.vessel_id == matched_manual.vessel_id,
            Spare.tenant_id == tenant_id,
            Spare.source_manual_id == matched_manual.id,
            Spare.qc_status == QCStatus.accepted,
            Spare.is_deleted == False,
        )
    )
    source_spares = list(spare_result.scalars().all())

    copied_spares = 0
    for spare in source_spares:
        copied_spare = Spare(
            tenant_id=tenant_id,
            vessel_id=vessel_id,
            component_id=component_id_map.get(spare.component_id) if spare.component_id else None,
            part_name=spare.part_name,
            part_number=spare.part_number,
            drawing_number=spare.drawing_number,
            drawing_position=spare.drawing_position,
            specification=spare.specification,
            spare_assembly=spare.spare_assembly,
            assembly_description=spare.assembly_description,
            spare_maker=spare.spare_maker,
            spare_model=spare.spare_model,
            machinery_maker=spare.machinery_maker,
            machinery_model=spare.machinery_model,
            source_manual_id=source_manual.id,
            page_reference=spare.page_reference if exact_match else None,
            extraction_method=spare.extraction_method,
            is_critical=spare.is_critical,
            qc_status=QCStatus.pending,
            confidence_score=spare.confidence_score,
            is_duplicate=spare.is_duplicate,
        )
        db.add(copied_spare)
        copied_spares += 1

    if auto_merge_components and copied_components:
        from app.services.component_matcher import auto_merge_extracted_components

        await db.flush()
        await auto_merge_extracted_components(
            db=db,
            vessel_id=vessel_id,
            tenant_id=tenant_id,
        )

    return {
        "copied_components": copied_components,
        "copied_jobs": copied_jobs,
        "copied_spares": copied_spares,
        "total": copied_components + copied_jobs + copied_spares,
        "exact_match": exact_match,
    }
