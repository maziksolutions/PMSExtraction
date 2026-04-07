from __future__ import annotations

import csv
import io
import re
import uuid
from difflib import SequenceMatcher
from typing import Annotated, Any, Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from sqlalchemy import String, asc, desc, func, or_, select
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


def _enum_value(value: Any) -> str | None:
    if value is None:
        return None
    return value.value if hasattr(value, "value") else str(value)


def _class_society_value(value: Any) -> str:
    raw = (_enum_value(value) or "General").strip()
    if not raw:
        return "General"
    normalized = _norm_text(raw)
    for member in ClassSociety:
        member_tokens = {
            _norm_text(member.value),
            _norm_text(member.name),
            _norm_text(f"{member.__class__.__name__}.{member.name}"),
        }
        if normalized in member_tokens:
            return member.value
    return raw


def _frequency_type_value(value: Any) -> str | None:
    raw = _enum_value(value)
    if not isinstance(raw, str) or not raw.strip():
        return None
    cleaned = raw.strip()
    normalized = _norm_text(cleaned).replace(" ", "_")
    mapped = FREQ_ALIASES.get(normalized.replace("_", " ")) or FREQ_ALIASES.get(normalized.replace("_", ""))
    if mapped:
        return mapped
    for member in FREQ_MAP.values():
        member_tokens = {
            _norm_text(member.value).replace(" ", "_"),
            _norm_text(member.name).replace(" ", "_"),
            _norm_text(f"{member.__class__.__name__}.{member.name}").replace(" ", "_"),
        }
        if normalized in member_tokens:
            return member.value
    return cleaned


def _job_type_for_standard_job(job: StandardJob) -> str:
    if bool(job.is_critical):
        return "critical"
    normalized_society = _norm_text(_class_society_value(job.class_society))
    return "class" if normalized_society in CLASS_LIBRARY_VALUES else "standard"


def _serialize_standard_job(job: StandardJob) -> dict[str, Any]:
    class_society = _class_society_value(job.class_society)
    frequency_type = _frequency_type_value(job.frequency_type)
    if job.is_critical:
        job_type = "critical"
    else:
        job_type = "class" if _norm_text(class_society) in CLASS_LIBRARY_VALUES else "standard"
    return {
        "id": str(job.id),
        "class_society": class_society,
        "job_type": job_type,
        "machinery_type": job.machinery_type,
        "job_name": job.job_name,
        "job_description": job.job_description,
        "frequency": job.frequency,
        "frequency_type": frequency_type,
        "is_critical": job.is_critical,
        "library_reference": job.library_reference,
    }


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
CLASS_LIBRARY_VALUES = {
    _norm_text(member.value)
    for member in ClassSociety
    if member != ClassSociety.general
}
CLASS_LIBRARY_VALUES.update(
    {
        _norm_text(f"{member.__class__.__name__}.{member.name}")
        for member in ClassSociety
        if member != ClassSociety.general
    }
)
WORKBOOK_SHEETS = {"annex1pmsjobs", "auditstandardjobs", "annexjobtitle", "criticaljobs"}
IMPORTABLE_JOB_HEADERS = {"jobname", "jobtitle", "jobdescription", "frequencytype", "frequency", "iscritical"}


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


def _sheet_looks_like_job_library(sheet_key: str, headers: list[str]) -> bool:
    if sheet_key in WORKBOOK_SHEETS:
        return True
    header_set = {header for header in headers if header}
    return len(header_set.intersection(IMPORTABLE_JOB_HEADERS)) >= 3 and (
        "jobname" in header_set or "jobtitle" in header_set
    )


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
    if job_type not in {"standard", "critical"}:
        return []

    rows: list[dict[str, Any]] = []
    for sheet_name in wb.sheetnames:
        ws = wb[sheet_name]
        sheet_key = _header_key(sheet_name)
        headers = [_header_key(cell.value) for cell in next(ws.iter_rows(min_row=1, max_row=1))]
        if not _sheet_looks_like_job_library(sheet_key, headers):
            continue
        for row in ws.iter_rows(min_row=2, values_only=True):
            mapped = {headers[i]: (row[i] if i < len(row) else None) for i in range(len(headers))}
            canonical = _canonical_standard_row(sheet_name, mapped, default_cs=ClassSociety.general)
            if canonical is not None:
                is_critical = bool(canonical.get("is_critical"))
                if job_type == "critical":
                    if not is_critical:
                        continue
                    canonical["is_critical"] = True
                elif is_critical:
                    continue
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


async def _resolve_component_mapping(
    *,
    vessel_id: uuid.UUID,
    component_id: Optional[str],
    db: AsyncSession,
) -> Optional[uuid.UUID]:
    if not component_id:
        return None
    try:
        component_uuid = uuid.UUID(component_id)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail="Invalid component mapping selected") from exc

    result = await db.execute(
        select(Component).where(
            Component.id == component_uuid,
            Component.vessel_id == vessel_id,
            Component.is_deleted == False,
        )
    )
    component = result.scalar_one_or_none()
    if component is None:
        raise HTTPException(status_code=404, detail="Mapped component not found on this vessel")
    return component_uuid


async def _upsert_standard_job_match(
    *,
    vessel_id: uuid.UUID,
    standard_job_id: uuid.UUID,
    matched_job_id: Optional[uuid.UUID],
    current_user: User,
    db: AsyncSession,
    match_status: MatchStatus = MatchStatus.matched,
    match_score: int = 100,
) -> None:
    result = await db.execute(
        select(StandardJobMatch).where(
            StandardJobMatch.vessel_id == vessel_id,
            StandardJobMatch.standard_job_id == standard_job_id,
            StandardJobMatch.is_deleted == False,
        )
    )
    match = result.scalar_one_or_none()
    if match is None:
        match = StandardJobMatch(
            tenant_id=current_user.tenant_id,
            vessel_id=vessel_id,
            standard_job_id=standard_job_id,
        )
    match.matched_job_id = matched_job_id
    match.match_status = match_status
    match.match_score = match_score if matched_job_id else 0
    db.add(match)


async def _import_standard_job_to_vessel(
    *,
    vessel_id: uuid.UUID,
    std_job: StandardJob,
    component_id: Optional[uuid.UUID],
    current_user: User,
    db: AsyncSession,
) -> tuple[str, Job]:
    existing_match_result = await db.execute(
        select(StandardJobMatch).where(
            StandardJobMatch.vessel_id == vessel_id,
            StandardJobMatch.standard_job_id == std_job.id,
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
            if component_id is not None:
                matched_job.component_id = component_id
                matched_job.is_unmapped = False
            if not matched_job.job_description and std_job.job_description:
                matched_job.job_description = std_job.job_description
            db.add(matched_job)
            await _upsert_standard_job_match(
                vessel_id=vessel_id,
                standard_job_id=std_job.id,
                matched_job_id=matched_job.id,
                current_user=current_user,
                db=db,
            )
            return "merged", matched_job

    existing_job_result = await db.execute(
        select(Job).where(
            Job.vessel_id == vessel_id,
            Job.job_name == std_job.job_name,
            Job.is_deleted == False,
        )
    )
    existing_job = existing_job_result.scalar_one_or_none()
    if existing_job is not None:
        existing_job.is_critical = bool(existing_job.is_critical or std_job.is_critical)
        existing_job.source_reference = _merge_source_reference(
            existing_job.source_reference,
            std_job.library_reference,
        )
        if component_id is not None:
            existing_job.component_id = component_id
            existing_job.is_unmapped = False
        if not existing_job.job_description and std_job.job_description:
            existing_job.job_description = std_job.job_description
        db.add(existing_job)
        await _upsert_standard_job_match(
            vessel_id=vessel_id,
            standard_job_id=std_job.id,
            matched_job_id=existing_job.id,
            current_user=current_user,
            db=db,
        )
        return "merged", existing_job

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
        component_id=component_id,
        is_unmapped=component_id is None,
    )
    db.add(new_job)
    await db.flush()
    await _upsert_standard_job_match(
        vessel_id=vessel_id,
        standard_job_id=std_job.id,
        matched_job_id=new_job.id,
        current_user=current_user,
        db=db,
    )
    return "imported", new_job


def _job_looks_library_imported(job: Job, std_job: StandardJob) -> bool:
    source_ref = _norm_text(job.source_reference)
    std_ref = _norm_text(std_job.library_reference)
    if job.source_manual_id is None and _norm_text(job.job_name) == _norm_text(std_job.job_name):
        return True
    if source_ref and std_ref and std_ref in source_ref:
        return True
    return False


@router.get("/standard-jobs", summary="List standard jobs library")
async def list_standard_jobs(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    class_society: Optional[str] = Query(None),
    machinery_type: Optional[str] = Query(None),
    is_critical: Optional[bool] = Query(None),
    job_type: Optional[str] = Query(None, description="'standard', 'class', or 'critical'"),
    search: Optional[str] = Query(None),
    sort_by: str = Query("job_name"),
    sort_order: str = Query("asc", pattern="^(asc|desc)$"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
) -> dict[str, Any]:
    class_society_expr = func.lower(func.trim(StandardJob.class_society.cast(String)))
    frequency_type_expr = func.lower(StandardJob.frequency_type.cast(String))
    query = select(StandardJob).where(
        StandardJob.tenant_id == current_user.tenant_id,
        StandardJob.is_deleted == False,
    )

    if job_type == "critical":
        query = query.where(StandardJob.is_critical.is_(True))
    elif job_type == "standard":
        query = query.where(
            StandardJob.is_critical.is_(False),
            or_(
                StandardJob.class_society.is_(None),
                ~class_society_expr.in_(sorted(CLASS_LIBRARY_VALUES)),
            ),
        )
    elif job_type == "class":
        query = query.where(
            StandardJob.is_critical.is_(False),
            class_society_expr.in_(sorted(CLASS_LIBRARY_VALUES)),
        )

    if class_society:
        normalized_society = _norm_text(class_society)
        mapped_society = CS_MAP.get(normalized_society)
        if mapped_society is not None:
            allowed_values = {
                mapped_society.value.lower(),
                f"{mapped_society.__class__.__name__}.{mapped_society.name}".lower(),
            }
            query = query.where(class_society_expr.in_(sorted(allowed_values)))
        else:
            query = query.where(class_society_expr == normalized_society)

    if machinery_type:
        query = query.where(StandardJob.machinery_type.ilike(f"%{machinery_type.strip()}%"))

    if is_critical is not None:
        query = query.where(StandardJob.is_critical.is_(is_critical))

    if search:
        term = f"%{search.strip()}%"
        query = query.where(
            or_(
                StandardJob.job_name.ilike(term),
                StandardJob.machinery_type.ilike(term),
                StandardJob.job_description.ilike(term),
                StandardJob.library_reference.ilike(term),
                StandardJob.class_society.cast(String).ilike(term),
                StandardJob.frequency.cast(String).ilike(term),
                StandardJob.frequency_type.cast(String).ilike(term),
            )
        )

    sort_columns = {
        "job_name": StandardJob.job_name,
        "machinery_type": StandardJob.machinery_type,
        "class_society": StandardJob.class_society.cast(String),
        "frequency": StandardJob.frequency,
        "frequency_type": StandardJob.frequency_type.cast(String),
        "critical": StandardJob.is_critical,
        "reference": StandardJob.library_reference,
        "job_type": class_society_expr,
    }
    order_col = sort_columns.get(sort_by, StandardJob.job_name)
    order_expr = desc(order_col) if sort_order == "desc" else asc(order_col)

    total = (
        await db.execute(select(func.count()).select_from(query.order_by(None).subquery()))
    ).scalar_one()
    total_pages = max(1, (total + page_size - 1) // page_size)
    jobs_result = await db.execute(
        query.order_by(order_expr).offset((page - 1) * page_size).limit(page_size)
    )
    jobs = [_serialize_standard_job(job) for job in jobs_result.scalars().all()]
    return {
        "items": jobs,
        "page": page,
        "page_size": page_size,
        "total": total,
        "total_pages": total_pages,
    }


@router.post("/standard-jobs/bulk-import", summary="Bulk import standard or class jobs from Excel/CSV")
async def bulk_import_standard_jobs(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    file: UploadFile = File(...),
    job_type: str = Query("standard", description="'standard' or 'class'"),
) -> dict[str, Any]:
    """Import Standard Jobs or Class Society Jobs from Excel/CSV."""
    content = await file.read()
    filename = (file.filename or "").lower()
    if job_type not in {"standard", "class", "critical"}:
        raise HTTPException(status_code=400, detail="job_type must be 'standard', 'class', or 'critical'")
    rows = _extract_rows_from_upload(content, filename, job_type=job_type)
    parsed_rows = len(rows)
    default_cs = ClassSociety.general if job_type == "standard" else None
    if job_type == "critical":
        default_cs = ClassSociety.general

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

    if not rows:
        raise HTTPException(
            status_code=400,
            detail="No importable rows found. Use Audit standard jobs / Annex Job Title for Standard Jobs or Critical Jobs for the Critical Jobs tab.",
        )

    imported = 0
    updated = 0
    unchanged = 0
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
        else:
            unchanged += 1

    await db.commit()
    if imported == 0 and updated == 0 and unchanged == 0 and skipped == parsed_rows:
        raise HTTPException(
            status_code=400,
            detail="No valid rows were imported. Please check that the selected tab matches the workbook content and required job columns are present.",
        )
    return {
        "parsed_rows": parsed_rows,
        "imported": imported,
        "updated": updated,
        "unchanged": unchanged,
        "skipped": skipped,
        "job_type": job_type,
    }


@router.post("/standard-jobs", summary="Create a standard or class job")
async def create_standard_job(
    body: dict[str, Any],
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, Any]:
    job_name = _clean_text(body.get("job_name"))
    machinery_type = _clean_text(body.get("machinery_type"))
    if not job_name or not machinery_type:
        raise HTTPException(status_code=400, detail="job_name and machinery_type are required")

    class_society_raw = _clean_text(body.get("class_society")) or "General"
    class_society = CS_MAP.get(_norm_text(class_society_raw))
    if class_society is None:
        raise HTTPException(status_code=400, detail="Invalid class_society")

    std_job = StandardJob(
        tenant_id=current_user.tenant_id,
        class_society=class_society,
        machinery_type=machinery_type,
        job_name=job_name,
        job_description=_clean_text(body.get("job_description")),
        frequency=_coerce_int(body.get("frequency")),
        frequency_type=_map_frequency_type(body.get("frequency_type")),
        is_critical=_coerce_bool(body.get("is_critical")),
        library_reference=_clean_text(body.get("library_reference")),
        is_system=False,
    )
    db.add(std_job)
    await db.commit()
    await db.refresh(std_job)
    return _serialize_standard_job(std_job)


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
            StandardJob.tenant_id == current_user.tenant_id,
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
            Job.source_manual_id.is_not(None),
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
    standard_job_ids: Optional[str] = Query(None, description="Comma separated standard job ids"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
) -> dict[str, Any]:
    await _get_vessel_or_404(vessel_id, db)
    conditions = [
        StandardJobMatch.vessel_id == vessel_id,
        StandardJobMatch.is_deleted == False,
    ]
    if standard_job_ids:
        ids: list[uuid.UUID] = []
        for raw in standard_job_ids.split(","):
            value = raw.strip()
            if not value:
                continue
            try:
                ids.append(uuid.UUID(value))
            except ValueError:
                continue
        if ids:
            conditions.append(StandardJobMatch.standard_job_id.in_(ids))
    if match_status:
        try:
            conditions.append(StandardJobMatch.match_status == MatchStatus(match_status))
        except ValueError:
            pass
    total = await db.scalar(select(func.count()).select_from(StandardJobMatch).where(*conditions)) or 0
    total_pages = max(1, (total + page_size - 1) // page_size)
    query = (
        select(StandardJobMatch)
        .where(*conditions)
        .order_by(StandardJobMatch.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
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
                "matched_job_description": job_lookup[m.matched_job_id].job_description if m.matched_job_id in job_lookup else None,
                "matched_job_qc_status": job_lookup[m.matched_job_id].qc_status.value if m.matched_job_id in job_lookup and job_lookup[m.matched_job_id].qc_status else None,
            }
            for m in matches
        ],
        "page": page,
        "page_size": page_size,
        "total": total,
        "total_pages": total_pages,
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
    component_id: Optional[str] = Query(None),
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

    mapped_component_id = await _resolve_component_mapping(
        vessel_id=vessel_id,
        component_id=component_id,
        db=db,
    )

    import_status, job = await _import_standard_job_to_vessel(
        vessel_id=vessel_id,
        std_job=std_job,
        component_id=mapped_component_id,
        current_user=current_user,
        db=db,
    )
    await db.commit()
    return {"status": import_status, "job_id": str(job.id)}


@router.post("/vessels/{vessel_id}/standard-jobs/import-batch", summary="Import selected or filtered standard jobs")
async def import_standard_jobs_batch(
    vessel_id: uuid.UUID,
    body: dict[str, Any],
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, Any]:
    await _get_vessel_or_404(vessel_id, db)

    selected_ids = [uuid.UUID(v) for v in body.get("standard_job_ids", []) if v]
    component_map_raw = body.get("component_map") or {}
    component_map: dict[str, uuid.UUID | None] = {}
    if isinstance(component_map_raw, dict):
        for standard_job_id, component_id in component_map_raw.items():
            if not isinstance(standard_job_id, str):
                continue
            component_map[standard_job_id] = await _resolve_component_mapping(
                vessel_id=vessel_id,
                component_id=component_id,
                db=db,
            ) if component_id else None
    query = select(StandardJob).where(
        StandardJob.tenant_id == current_user.tenant_id,
        StandardJob.is_deleted == False,
    )
    if selected_ids:
        query = query.where(StandardJob.id.in_(selected_ids))
    else:
        if body.get("job_type") == "standard":
            query = query.where(StandardJob.class_society == ClassSociety.general)
        elif body.get("job_type") == "class":
            query = query.where(StandardJob.class_society != ClassSociety.general)
        if body.get("class_society"):
            cs = CS_MAP.get(_norm_text(body["class_society"]))
            if cs:
                query = query.where(StandardJob.class_society == cs)
        if body.get("machinery_type"):
            query = query.where(StandardJob.machinery_type == body["machinery_type"])
        if body.get("include_critical") is False:
            query = query.where(StandardJob.is_critical == False)
    result = await db.execute(query)
    std_jobs = result.scalars().all()
    if not std_jobs:
        raise HTTPException(status_code=404, detail="No standard jobs found for import")

    imported = 0
    merged = 0
    for std_job in std_jobs:
        mapped_component_id = component_map.get(str(std_job.id))
        status_value, _ = await _import_standard_job_to_vessel(
            vessel_id=vessel_id,
            std_job=std_job,
            component_id=mapped_component_id,
            current_user=current_user,
            db=db,
        )
        if status_value == "imported":
            imported += 1
        else:
            merged += 1
    await db.commit()
    return {"imported": imported, "merged": merged, "total": len(std_jobs)}


@router.post("/vessels/{vessel_id}/standard-jobs/remove-batch", summary="Remove selected or filtered imported standard jobs from vessel")
async def remove_standard_jobs_batch(
    vessel_id: uuid.UUID,
    body: dict[str, Any],
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, Any]:
    await _get_vessel_or_404(vessel_id, db)

    selected_ids = [uuid.UUID(v) for v in body.get("standard_job_ids", []) if v]
    query = select(StandardJob).where(
        StandardJob.tenant_id == current_user.tenant_id,
        StandardJob.is_deleted == False,
    )
    if selected_ids:
        query = query.where(StandardJob.id.in_(selected_ids))
    else:
        if body.get("job_type") == "standard":
            query = query.where(StandardJob.class_society == ClassSociety.general)
        elif body.get("job_type") == "class":
            query = query.where(StandardJob.class_society != ClassSociety.general)
        if body.get("class_society"):
            cs = CS_MAP.get(_norm_text(body["class_society"]))
            if cs:
                query = query.where(StandardJob.class_society == cs)
        if body.get("machinery_type"):
            query = query.where(StandardJob.machinery_type == body["machinery_type"])
        if body.get("include_critical") is False:
            query = query.where(StandardJob.is_critical == False)
    result = await db.execute(query)
    std_jobs = result.scalars().all()
    if not std_jobs:
        raise HTTPException(status_code=404, detail="No standard jobs found for removal")

    removed = 0
    skipped = 0
    for std_job in std_jobs:
        match_result = await db.execute(
            select(StandardJobMatch).where(
                StandardJobMatch.vessel_id == vessel_id,
                StandardJobMatch.standard_job_id == std_job.id,
                StandardJobMatch.is_deleted == False,
            )
        )
        match = match_result.scalar_one_or_none()
        if match is None or match.matched_job_id is None:
            skipped += 1
            continue
        job_result = await db.execute(
            select(Job).where(
                Job.id == match.matched_job_id,
                Job.vessel_id == vessel_id,
                Job.is_deleted == False,
            )
        )
        job = job_result.scalar_one_or_none()
        if job is None or not _job_looks_library_imported(job, std_job):
            skipped += 1
            continue
        job.is_deleted = True
        match.matched_job_id = None
        match.match_status = MatchStatus.not_found
        match.match_score = 0
        db.add(job)
        db.add(match)
        removed += 1

    await db.commit()
    return {"removed": removed, "skipped": skipped, "total": len(std_jobs)}


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
