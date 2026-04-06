from __future__ import annotations

import csv
import io
import re
import uuid
from difflib import SequenceMatcher
from typing import Annotated, Any, Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user
from app.models.component import Component, QCStatus
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


def _norm_text(value: Any) -> str:
    return " ".join(str(value or "").strip().lower().split())


def _header_key(value: Any) -> str:
    return "".join(ch for ch in str(value or "").strip().lower() if ch.isalnum())


def _clean_text(value: Any) -> Optional[str]:
    text = str(value or "").strip()
    return text or None


def _coerce_bool(value: Any) -> bool:
    return _norm_text(value) in {"yes", "true", "1", "y"}


def _coerce_int(value: Any) -> Optional[int]:
    if value is None:
        return None
    text = str(value).strip()
    if not text or _norm_text(text) in {"na", "n/a", "maker instruction", "makers instruction"}:
        return None
    try:
        return int(float(text))
    except (TypeError, ValueError):
        return None


FREQ_MAP = {member.value: member for member in __import__("app.models.job", fromlist=["FrequencyType"]).FrequencyType}
FREQ_ALIASES = {
    "daily": "daily",
    "weekly": "weekly",
    "fortnightly": "biweekly",
    "biweekly": "biweekly",
    "monthly": "monthly",
    "quarterly": "quarterly",
    "half yearly": "half_yearly",
    "halfyearly": "half_yearly",
    "half_yearly": "half_yearly",
    "sixmonthly": "half_yearly",
    "6monthly": "half_yearly",
    "yearly": "yearly",
    "annual": "yearly",
    "biannual": "biannual",
    "biennial": "biannual",
    "runhours": "running_hours",
    "runninghours": "running_hours",
    "running_hours": "running_hours",
    "hourly": "running_hours",
    "hours": "running_hours",
}
CS_MAP = {member.value.lower(): member for member in ClassSociety}
WORKBOOK_SHEETS = {"annex1pmsjobs", "auditstandardjobs", "annexjobtitle", "criticaljobs"}


def _map_frequency_type(value: Any) -> Optional[Any]:
    normalized = _norm_text(value).replace("-", " ")
    compact = normalized.replace(" ", "")
    if not normalized or normalized in {"na", "n/a", "maker instruction", "makers instruction"}:
        return None
    mapped = FREQ_ALIASES.get(normalized) or FREQ_ALIASES.get(compact)
    return FREQ_MAP.get(mapped) if mapped else None


def _choose_frequency(row: dict[str, Any]) -> tuple[Optional[int], Optional[Any]]:
    primary_type = _map_frequency_type(row.get("frequencytype"))
    primary_freq = _coerce_int(row.get("frequency"))
    alt_type = _map_frequency_type(row.get("alternatefrequencytype"))
    alt_freq = _coerce_int(row.get("alternatefrequency"))
    if primary_type is not None:
        return primary_freq, primary_type
    if alt_type is not None:
        return alt_freq, alt_type
    return primary_freq, None


def _derive_machinery_type(raw_name: Optional[str], fallback_name: Optional[str], group: Optional[str]) -> str:
    source = raw_name or fallback_name or group or "General"
    source = re.sub(r"\s+", " ", source).strip()
    parts = [part.strip() for part in re.split(r"\s*-\s*", source) if part.strip()]
    if len(parts) >= 2:
        return " - ".join(parts[:2])
    return parts[0] if parts else source


def _build_library_reference(sheet_name: str, row: dict[str, Any]) -> Optional[str]:
    for key in ("procedurereferencecode", "operationalprocedurecode", "safetyprocedurecode", "documentreferencecode"):
        value = _clean_text(row.get(key))
        if value:
            return value
    remarks = _clean_text(row.get("remarks")) or _clean_text(row.get(""))
    if remarks:
        return f"{sheet_name}: {remarks}"[:200]
    return sheet_name[:200]


def _canonical_standard_row(sheet_name: str, row: dict[str, Any], *, default_cs: ClassSociety) -> Optional[dict[str, Any]]:
    if _coerce_bool(row.get("isinactive")):
        return None

    job_name = (
        _clean_text(row.get("jobtitle"))
        or _clean_text(row.get("job title"))
        or _clean_text(row.get("jobname"))
    )
    raw_name = _clean_text(row.get("jobname")) or job_name
    if not job_name:
        return None

    frequency, frequency_type = _choose_frequency(row)
    is_critical = _coerce_bool(row.get("iscritical")) or _coerce_bool(row.get("is_critical"))
    class_society = default_cs
    if row.get("classsociety"):
        class_society = CS_MAP.get(_norm_text(row.get("classsociety")), default_cs)

    return {
        "class_society": class_society,
        "machinery_type": _derive_machinery_type(raw_name, job_name, _clean_text(row.get("jobgroup"))),
        "job_name": job_name,
        "job_description": _clean_text(row.get("jobdescription")),
        "frequency": frequency,
        "frequency_type": frequency_type,
        "is_critical": is_critical,
        "library_reference": _build_library_reference(sheet_name, row),
        "is_system": False,
    }


def _standard_job_key(
    *,
    class_society: ClassSociety,
    machinery_type: str,
    job_name: str,
    is_critical: bool,
) -> tuple[str, str, str, bool]:
    return (
        class_society.value.lower(),
        _norm_text(machinery_type),
        _norm_text(job_name),
        is_critical,
    )


def _extract_structured_workbook_rows(wb: Any, *, job_type: str) -> list[dict[str, Any]]:
    if job_type != "standard":
        return []

    rows: list[dict[str, Any]] = []
    for sheet_name in wb.sheetnames:
        ws = wb[sheet_name]
        if _header_key(sheet_name) not in WORKBOOK_SHEETS:
            continue
        headers = [_header_key(cell.value) for cell in next(ws.iter_rows(min_row=1, max_row=1))]
        for row in ws.iter_rows(min_row=2, values_only=True):
            mapped = {headers[i]: (row[i] if i < len(row) else None) for i in range(len(headers))}
            canonical = _canonical_standard_row(sheet_name, mapped, default_cs=ClassSociety.general)
            if canonical is not None:
                rows.append(canonical)
    return rows


def _extract_rows_from_upload(content: bytes, filename: str, *, job_type: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if filename.endswith(".csv"):
        text = content.decode("utf-8-sig", errors="replace")
        reader = csv.DictReader(io.StringIO(text))
        rows = [{_header_key(k): v for k, v in dict(r).items()} for r in reader]
    else:
        import openpyxl

        wb = openpyxl.load_workbook(io.BytesIO(content), data_only=True)
        structured_rows = _extract_structured_workbook_rows(wb, job_type=job_type)
        if structured_rows:
            return structured_rows
        ws = wb.active
        headers = [_header_key(c.value) for c in next(ws.iter_rows(min_row=1, max_row=1))]
        for row in ws.iter_rows(min_row=2, values_only=True):
            rows.append({headers[i]: (row[i] if i < len(row) else None) for i in range(len(headers))})
    return rows


def _score_standard_job(std_job: StandardJob, vessel_job: Job, component_lookup: dict[uuid.UUID, Component]) -> int:
    std_name = _norm_text(std_job.job_name)
    vessel_name = _norm_text(vessel_job.job_name)
    if not std_name or not vessel_name:
        return 0

    ratio = SequenceMatcher(None, std_name, vessel_name).ratio()
    score = int(ratio * 100)
    if std_name == vessel_name:
        score = max(score, 100)
    if std_job.frequency and vessel_job.frequency and std_job.frequency == vessel_job.frequency:
        score += 5
    if std_job.frequency_type and vessel_job.frequency_type and std_job.frequency_type == vessel_job.frequency_type:
        score += 5

    linked_component = component_lookup.get(vessel_job.component_id) if vessel_job.component_id else None
    machinery_context = _norm_text(linked_component.main_machinery if linked_component else "")
    std_machinery = _norm_text(std_job.machinery_type)
    if std_machinery and machinery_context and (
        std_machinery in machinery_context or machinery_context in std_machinery
    ):
        score += 10
    return min(score, 100)


def _merge_source_reference(existing: Optional[str], new_value: Optional[str]) -> Optional[str]:
    merged: list[str] = []
    seen: set[str] = set()
    for raw in (existing, new_value):
        for part in (raw or "").split(" | "):
            cleaned = part.strip()
            if not cleaned:
                continue
            key = cleaned.lower()
            if key in seen:
                continue
            seen.add(key)
            merged.append(cleaned)
    return " | ".join(merged) if merged else None


@router.get("/standard-jobs", summary="List standard jobs library")
async def list_standard_jobs(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    class_society: Optional[str] = Query(None),
    machinery_type: Optional[str] = Query(None),
    is_critical: Optional[bool] = Query(None),
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
    if is_critical is not None:
        query = query.where(StandardJob.is_critical == is_critical)
    query = query.offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(query)
    jobs = result.scalars().all()
    return {
        "items": [
            {
                "id": str(j.id),
                "class_society": j.class_society.value,
                "job_type": "standard" if j.class_society == ClassSociety.general else "class",
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


@router.post("/standard-jobs/bulk-import", summary="Bulk import standard or class jobs from Excel/CSV")
async def bulk_import_standard_jobs(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    file: UploadFile = File(...),
    job_type: str = Query("standard", description="'standard' or 'class'"),
) -> dict[str, Any]:
    """
    Import Standard Jobs or Class Society Jobs from an Excel (.xlsx) or CSV file.

    Expected columns (Excel header row):
      job_name, machinery_type, job_description (opt), class_society (opt),
      frequency (opt), frequency_type (opt), is_critical (opt), library_reference (opt)

    For job_type='standard', class_society defaults to 'General'.
    For job_type='class', class_society column is required.
    """
    content = await file.read()
    filename = (file.filename or "").lower()
    rows = _extract_rows_from_upload(content, filename, job_type=job_type)
    default_cs = ClassSociety.general if job_type == "standard" else None

    existing_result = await db.execute(
        select(StandardJob).where(
            StandardJob.tenant_id == current_user.tenant_id,
            StandardJob.is_deleted == False,
        )
    )
    existing_jobs = {
        _standard_job_key(
            class_society=job.class_society,
            machinery_type=job.machinery_type,
            job_name=job.job_name,
            is_critical=job.is_critical,
        ): job
        for job in existing_result.scalars().all()
    }

    imported = 0
    updated = 0
    skipped = 0
    seen_upload_keys: set[tuple[str, str, str, bool]] = set()
    for row in rows:
        if "class_society" in row:
            canonical = row
        else:
            job_name = _clean_text(row.get("jobname") or row.get("job_name"))
            machinery_type = _clean_text(row.get("machinerytype") or row.get("machinery_type"))
            if not job_name or not machinery_type:
                skipped += 1
                continue
            cs_raw = _norm_text(row.get("classsociety") or row.get("class_society"))
            class_society = CS_MAP.get(cs_raw, default_cs)
            if class_society is None:
                skipped += 1
                continue
            canonical = {
                "class_society": class_society,
                "machinery_type": machinery_type,
                "job_name": job_name,
                "job_description": _clean_text(row.get("jobdescription") or row.get("job_description")),
                "frequency": _coerce_int(row.get("frequency")),
                "frequency_type": _map_frequency_type(row.get("frequencytype") or row.get("frequency_type")),
                "is_critical": _coerce_bool(row.get("iscritical") or row.get("is_critical")),
                "library_reference": _clean_text(row.get("libraryreference") or row.get("library_reference")),
                "is_system": False,
            }

        key = _standard_job_key(
            class_society=canonical["class_society"],
            machinery_type=canonical["machinery_type"],
            job_name=canonical["job_name"],
            is_critical=canonical["is_critical"],
        )
        if key in seen_upload_keys:
            skipped += 1
            continue
        seen_upload_keys.add(key)

        existing = existing_jobs.get(key)
        if existing is None and canonical["is_critical"]:
            existing = existing_jobs.get(
                _standard_job_key(
                    class_society=canonical["class_society"],
                    machinery_type=canonical["machinery_type"],
                    job_name=canonical["job_name"],
                    is_critical=False,
                )
            )
        if existing is None:
            db.add(
                StandardJob(
                    tenant_id=current_user.tenant_id,
                    class_society=canonical["class_society"],
                    machinery_type=canonical["machinery_type"],
                    job_name=canonical["job_name"],
                    job_description=canonical["job_description"],
                    frequency=canonical["frequency"],
                    frequency_type=canonical["frequency_type"],
                    is_critical=canonical["is_critical"],
                    library_reference=canonical["library_reference"],
                    is_system=False,
                )
            )
            imported += 1
            continue

        changed = False
        if canonical["job_description"] and canonical["job_description"] != existing.job_description:
            existing.job_description = canonical["job_description"]
            changed = True
        if canonical["frequency"] is not None and canonical["frequency"] != existing.frequency:
            existing.frequency = canonical["frequency"]
            changed = True
        if canonical["frequency_type"] is not None and canonical["frequency_type"] != existing.frequency_type:
            existing.frequency_type = canonical["frequency_type"]
            changed = True
        if canonical["library_reference"] and canonical["library_reference"] != existing.library_reference:
            existing.library_reference = canonical["library_reference"]
            changed = True
        if canonical["is_critical"] and not existing.is_critical:
            existing.is_critical = True
            changed = True
            existing_jobs[key] = existing
        if changed:
            db.add(existing)
            updated += 1

    await db.commit()
    return {
        "imported": imported,
        "updated": updated,
        "skipped": skipped,
        "job_type": job_type,
    }


@router.delete("/standard-jobs/{standard_job_id}", summary="Delete a standard job")
async def delete_standard_job(
    standard_job_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, Any]:
    result = await db.execute(
        select(StandardJob).where(StandardJob.id == standard_job_id, StandardJob.is_deleted == False)
    )
    job = result.scalar_one_or_none()
    if job is None:
        raise HTTPException(status_code=404, detail="Standard job not found")
    job.is_deleted = True
    db.add(job)
    await db.commit()
    return {"deleted": True}


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
        select(StandardJob).where(
            StandardJob.is_deleted == False,
            StandardJob.is_critical == False,
        )
    )
    std_jobs = std_jobs_result.scalars().all()

    # Get vessel jobs
    vessel_jobs_result = await db.execute(
        select(Job).where(
            Job.vessel_id == vessel_id,
            Job.qc_status != QCStatus.rejected,
            Job.is_deleted == False,
        )
    )
    vessel_jobs = vessel_jobs_result.scalars().all()
    component_ids = {job.component_id for job in vessel_jobs if job.component_id}
    component_lookup: dict[uuid.UUID, Component] = {}
    if component_ids:
        component_result = await db.execute(select(Component).where(Component.id.in_(component_ids)))
        component_lookup = {component.id: component for component in component_result.scalars().all()}

    existing_result = await db.execute(
        select(StandardJobMatch).where(
            StandardJobMatch.vessel_id == vessel_id,
            StandardJobMatch.is_deleted == False,
        )
    )
    existing_matches = {match.standard_job_id: match for match in existing_result.scalars().all()}

    matches_created = 0
    for std_job in std_jobs:
        best_match: Job | None = None
        best_score = 0
        for vessel_job in vessel_jobs:
            score = _score_standard_job(std_job, vessel_job, component_lookup)
            if score > best_score:
                best_score = score
                best_match = vessel_job

        if best_score >= 92 and best_match is not None:
            match_status = MatchStatus.matched
            matched_job_id = best_match.id
        elif best_score >= 70 and best_match is not None:
            match_status = MatchStatus.partial
            matched_job_id = best_match.id
        else:
            match_status = MatchStatus.not_found
            matched_job_id = None
            best_score = 0

        match = existing_matches.get(std_job.id)
        if match is None:
            match = StandardJobMatch(
                tenant_id=current_user.tenant_id,
                vessel_id=vessel_id,
                standard_job_id=std_job.id,
            )
            matches_created += 1

        match.matched_job_id = matched_job_id
        match.match_status = match_status
        match.match_score = best_score
        db.add(match)

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
    matched_job_ids = [match.matched_job_id for match in matches if match.matched_job_id]
    job_lookup: dict[uuid.UUID, Job] = {}
    if matched_job_ids:
        jobs_result = await db.execute(select(Job).where(Job.id.in_(matched_job_ids)))
        job_lookup = {job.id: job for job in jobs_result.scalars().all()}
    return {
        "items": [
            {
                "id": str(m.id),
                "standard_job_id": str(m.standard_job_id),
                "matched_job_id": str(m.matched_job_id) if m.matched_job_id else None,
                "match_status": m.match_status.value,
                "match_score": m.match_score,
                "not_applicable_reason": m.not_applicable_reason,
                "matched_job_name": job_lookup[m.matched_job_id].job_name if m.matched_job_id in job_lookup else None,
                "matched_job_code": job_lookup[m.matched_job_id].job_code if m.matched_job_id in job_lookup else None,
                "matched_job_qc_status": job_lookup[m.matched_job_id].qc_status.value if m.matched_job_id in job_lookup and job_lookup[m.matched_job_id].qc_status else None,
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

    existing_match_result = await db.execute(
        select(StandardJobMatch).where(
            StandardJobMatch.vessel_id == vessel_id,
            StandardJobMatch.standard_job_id == standard_job_id,
            StandardJobMatch.is_deleted == False,
        )
    )
    existing_match = existing_match_result.scalar_one_or_none()
    if existing_match and existing_match.matched_job_id:
        matched_job_result = await db.execute(
            select(Job).where(
                Job.id == existing_match.matched_job_id,
                Job.vessel_id == vessel_id,
                Job.is_deleted == False,
            )
        )
        matched_job = matched_job_result.scalar_one_or_none()
        if matched_job is not None:
            matched_job.is_critical = bool(matched_job.is_critical or std_job.is_critical)
            matched_job.source_reference = _merge_source_reference(
                matched_job.source_reference,
                std_job.library_reference,
            )
            db.add(matched_job)
            await db.commit()
            return {"status": "merged", "job_id": str(matched_job.id)}

    existing_job = await db.execute(
        select(Job).where(
            Job.vessel_id == vessel_id,
            Job.job_name == std_job.job_name,
            Job.is_deleted == False,
        )
    )
    if existing_job.scalar_one_or_none() is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="A similar vessel job already exists")

    new_job = Job(
        tenant_id=current_user.tenant_id,
        vessel_id=vessel_id,
        job_name=std_job.job_name,
        job_description=std_job.job_description,
        frequency=std_job.frequency,
        frequency_type=std_job.frequency_type,
        is_critical=std_job.is_critical,
        source_reference=std_job.library_reference,
        qc_status=QCStatus.pending,
        is_unmapped=True,
    )
    db.add(new_job)
    await db.commit()
    await db.refresh(new_job)
    return {"status": "imported", "job_id": str(new_job.id)}


@router.post("/vessels/{vessel_id}/standard-jobs/add-critical-jobs", summary="Add missing critical standard jobs")
async def add_critical_jobs(
    vessel_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, Any]:
    await _get_vessel_or_404(vessel_id, db)

    critical_result = await db.execute(
        select(StandardJob).where(
            StandardJob.tenant_id == current_user.tenant_id,
            StandardJob.is_deleted == False,
            StandardJob.is_critical == True,
        )
    )
    critical_jobs = critical_result.scalars().all()

    vessel_jobs_result = await db.execute(
        select(Job).where(
            Job.vessel_id == vessel_id,
            Job.tenant_id == current_user.tenant_id,
            Job.is_deleted == False,
            Job.qc_status != QCStatus.rejected,
        )
    )
    vessel_jobs = vessel_jobs_result.scalars().all()
    component_ids = {job.component_id for job in vessel_jobs if job.component_id}
    component_lookup: dict[uuid.UUID, Component] = {}
    if component_ids:
        component_result = await db.execute(select(Component).where(Component.id.in_(component_ids)))
        component_lookup = {component.id: component for component in component_result.scalars().all()}

    added = 0
    updated = 0
    skipped = 0
    for std_job in critical_jobs:
        best_match: Job | None = None
        best_score = 0
        for vessel_job in vessel_jobs:
            score = _score_standard_job(std_job, vessel_job, component_lookup)
            if score > best_score:
                best_score = score
                best_match = vessel_job

        if best_match is not None and best_score >= 92:
            changed = False
            if not best_match.is_critical:
                best_match.is_critical = True
                changed = True
            merged_reference = _merge_source_reference(best_match.source_reference, std_job.library_reference)
            if merged_reference != best_match.source_reference:
                best_match.source_reference = merged_reference
                changed = True
            if changed:
                db.add(best_match)
                updated += 1
            else:
                skipped += 1
            continue

        existing_same_name = await db.execute(
            select(Job).where(
                Job.vessel_id == vessel_id,
                Job.job_name == std_job.job_name,
                Job.is_deleted == False,
            )
        )
        if existing_same_name.scalar_one_or_none() is not None:
            skipped += 1
            continue

        db.add(
            Job(
                tenant_id=current_user.tenant_id,
                vessel_id=vessel_id,
                job_name=std_job.job_name,
                job_description=std_job.job_description,
                frequency=std_job.frequency,
                frequency_type=std_job.frequency_type,
                is_critical=True,
                source_reference=std_job.library_reference,
                qc_status=QCStatus.accepted,
                is_unmapped=True,
            )
        )
        added += 1

    await db.commit()
    return {"added": added, "updated": updated, "skipped": skipped}


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
