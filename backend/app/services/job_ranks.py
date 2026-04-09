from __future__ import annotations

import json
import re
import uuid
from functools import lru_cache
from pathlib import Path
from typing import Any, Optional

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.component import Component
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


def _seed_text_key(value: Optional[str]) -> str:
    return " ".join(
        token for token in re.split(r"[^a-z0-9]+", str(value or "").strip().lower()) if token
    )


@lru_cache(maxsize=1)
def _load_audit_rank_seed() -> dict[str, Any]:
    seed_path = Path(__file__).resolve().parents[1] / "data" / "audit_rank_seed.json"
    if not seed_path.exists():
        return {
            "known_ranks": [],
            "performing_by_reference": {},
            "performing_by_job_name": {},
        }
    try:
        return json.loads(seed_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {
            "known_ranks": [],
            "performing_by_reference": {},
            "performing_by_job_name": {},
        }


DECK_RANK_KEYS = {
    "master",
    "chief officer",
    "second officer",
    "third officer",
    "deck cadet",
    "boatswain",
    "bosun",
    "able seaman",
}

ENGINE_RANK_KEYS = {
    "chief engineer",
    "second engineer",
    "third engineer",
    "fourth engineer",
    "fifth engineer",
    "electrical officer",
    "electrical engineer",
    "eto",
    "motorman",
    "oiler",
    "fitter",
    "wiper",
}

DECK_HINTS = {
    "accommodation",
    "cargo",
    "deck",
    "eboats",
    "embarkation",
    "hatch",
    "lifeboat",
    "liferaft",
    "lighting",
    "lashing",
    "ladder",
    "mast",
    "mooring",
    "navigation",
    "paint",
    "pilot",
    "pv",
    "raft",
    "steering",
    "winch",
}

ENGINE_HINTS = {
    "air",
    "auxiliary",
    "bearing",
    "boiler",
    "compressor",
    "cooler",
    "diesel",
    "electrical",
    "engine",
    "exhaust",
    "fuel",
    "generator",
    "governor",
    "hydraulic",
    "lube",
    "main",
    "motor",
    "oil",
    "overhaul",
    "pump",
    "purifier",
    "shaft",
    "turbocharger",
    "valve",
}

ELECTRICAL_HINTS = {
    "alarm",
    "battery",
    "breaker",
    "circuit",
    "electrical",
    "generator",
    "lighting",
    "sensor",
    "starter",
    "switchboard",
    "uv",
    "wiring",
}


def _audit_seed_performing_rank(
    *,
    job_name: Optional[str] = None,
    library_reference: Optional[str] = None,
) -> Optional[str]:
    seed = _load_audit_rank_seed()
    ref_key = _seed_text_key(library_reference)
    if ref_key:
        match = seed.get("performing_by_reference", {}).get(ref_key)
        if match:
            return normalize_rank_name(match)
    name_key = _seed_text_key(job_name)
    if name_key:
        match = seed.get("performing_by_job_name", {}).get(name_key)
        if match:
            return normalize_rank_name(match)
    return None


def infer_verifying_rank(
    performing_rank: Optional[str],
    *,
    job_name: Optional[str] = None,
    machinery_type: Optional[str] = None,
) -> Optional[str]:
    performer_key = _rank_key(performing_rank)
    if performer_key in DECK_RANK_KEYS:
        return "Master"
    if performer_key in ENGINE_RANK_KEYS:
        return "Chief Engineer"

    token_set = {
        token
        for token in (
            f"{_seed_text_key(job_name)} {_seed_text_key(machinery_type)}"
        ).split()
        if token
    }
    has_deck_hints = bool(token_set.intersection(DECK_HINTS))
    has_engine_hints = bool(token_set.intersection(ENGINE_HINTS))
    if has_deck_hints and not has_engine_hints:
        return "Master"
    if has_engine_hints:
        return "Chief Engineer"
    return None


def _text_tokens(*values: Optional[str]) -> set[str]:
    token_set: set[str] = set()
    for value in values:
        token_set.update(token for token in _seed_text_key(value).split() if token)
    return token_set


def _manual_job_name_variants(
    job_name: Optional[str],
    component_name: Optional[str],
) -> list[str]:
    full_name = _seed_text_key(job_name)
    component_key = _seed_text_key(component_name)
    candidates: list[str] = []
    if full_name:
        candidates.append(full_name)
    if full_name and component_key:
        if full_name.startswith(component_key):
            stripped = full_name[len(component_key):].strip()
            if stripped:
                candidates.append(stripped)
        for separator in (" inspect ", " inspection ", " overhaul ", " routine ", " check ", " clean "):
            if separator in full_name:
                candidates.append(full_name.split(separator, 1)[0].strip())
    seen: set[str] = set()
    ordered: list[str] = []
    for candidate in candidates:
        if candidate and candidate not in seen:
            seen.add(candidate)
            ordered.append(candidate)
    return ordered


def infer_manual_performing_rank(
    *,
    job_name: Optional[str],
    component_name: Optional[str] = None,
    main_machinery: Optional[str] = None,
    group1: Optional[str] = None,
    group2: Optional[str] = None,
    inferred_component_rank: Optional[str] = None,
    matched_standard_job: Optional[StandardJob] = None,
) -> Optional[str]:
    if matched_standard_job is not None and matched_standard_job.performing_rank:
        return normalize_rank_name(matched_standard_job.performing_rank)

    from_seed = _audit_seed_performing_rank(job_name=job_name)
    if from_seed:
        return from_seed

    if inferred_component_rank:
        return normalize_rank_name(inferred_component_rank)

    tokens = _text_tokens(job_name, component_name, main_machinery, group1, group2)
    if tokens.intersection(ELECTRICAL_HINTS):
        return "Electrical Officer"
    has_deck_hints = bool(tokens.intersection(DECK_HINTS))
    has_engine_hints = bool(tokens.intersection(ENGINE_HINTS))
    if has_deck_hints and not has_engine_hints:
        return "Chief Officer"
    if has_engine_hints:
        return "Second Engineer"
    return None


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


async def seed_rank_library_from_audit_sample(
    db: AsyncSession,
    *,
    tenant_id: uuid.UUID,
) -> None:
    seed = _load_audit_rank_seed()
    known_ranks = {
        normalize_rank_name(rank_name)
        for rank_name in seed.get("known_ranks", [])
    }
    known_ranks.update({"Chief Engineer", "Master"})
    for rank_name in sorted(rank_name for rank_name in known_ranks if rank_name):
        await ensure_job_rank(db, tenant_id=tenant_id, rank_name=rank_name)


def derive_standard_job_ranks(
    *,
    job_name: Optional[str],
    machinery_type: Optional[str],
    library_reference: Optional[str],
    performing_rank: Optional[str],
    verifying_rank: Optional[str],
) -> tuple[Optional[str], Optional[str]]:
    next_performing_rank = normalize_rank_name(performing_rank) or _audit_seed_performing_rank(
        job_name=job_name,
        library_reference=library_reference,
    )
    next_verifying_rank = normalize_rank_name(verifying_rank) or infer_verifying_rank(
        next_performing_rank,
        job_name=job_name,
        machinery_type=machinery_type,
    )
    return next_performing_rank, next_verifying_rank


async def backfill_standard_job_ranks_from_audit_seed(
    db: AsyncSession,
    *,
    tenant_id: uuid.UUID,
) -> bool:
    result = await db.execute(
        select(StandardJob).where(
            StandardJob.tenant_id == tenant_id,
            StandardJob.is_deleted == False,
            or_(
                StandardJob.performing_rank.is_(None),
                StandardJob.verifying_rank.is_(None),
            ),
        )
    )
    jobs = result.scalars().all()
    if not jobs:
        return False

    changed = False
    for job in jobs:
        next_performing_rank, next_verifying_rank = derive_standard_job_ranks(
            job_name=job.job_name,
            machinery_type=job.machinery_type,
            library_reference=job.library_reference,
            performing_rank=job.performing_rank,
            verifying_rank=job.verifying_rank,
        )

        if next_performing_rank != job.performing_rank:
            job.performing_rank = next_performing_rank
            db.add(job)
            changed = True
        if next_verifying_rank != job.verifying_rank:
            job.verifying_rank = next_verifying_rank
            db.add(job)
            changed = True

    if not changed:
        return False

    for job in jobs:
        await ensure_job_rank(db, tenant_id=tenant_id, rank_name=job.performing_rank)
        await ensure_job_rank(db, tenant_id=tenant_id, rank_name=job.verifying_rank)
    await db.commit()
    return True


def _reference_match_key(
    source_reference: Optional[str],
    reference_keys: list[str],
) -> Optional[str]:
    haystack = _seed_text_key(source_reference)
    if not haystack:
        return None
    for reference_key in reference_keys:
        if reference_key and reference_key in haystack:
            return reference_key
    return None


def derive_job_ranks_from_library_context(
    *,
    job_name: Optional[str],
    source_reference: Optional[str],
    existing_performing_rank: Optional[str],
    existing_verifying_rank: Optional[str],
    matched_standard_job: Optional[StandardJob],
) -> tuple[Optional[str], Optional[str]]:
    next_performing_rank = normalize_rank_name(existing_performing_rank)
    next_verifying_rank = normalize_rank_name(existing_verifying_rank)

    if not next_performing_rank and matched_standard_job is not None:
        next_performing_rank = normalize_rank_name(matched_standard_job.performing_rank)
    if not next_performing_rank:
        next_performing_rank = _audit_seed_performing_rank(
            job_name=job_name,
            library_reference=source_reference,
        )

    if not next_verifying_rank and matched_standard_job is not None:
        next_verifying_rank = normalize_rank_name(matched_standard_job.verifying_rank)
    if not next_verifying_rank:
        next_verifying_rank = infer_verifying_rank(
            next_performing_rank,
            job_name=job_name,
            machinery_type=matched_standard_job.machinery_type if matched_standard_job is not None else None,
        )

    return next_performing_rank, next_verifying_rank


async def backfill_vessel_job_ranks_from_library_data(
    db: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    vessel_id: uuid.UUID,
) -> bool:
    jobs_result = await db.execute(
        select(Job).where(
            Job.tenant_id == tenant_id,
            Job.vessel_id == vessel_id,
            Job.is_deleted == False,
            or_(
                Job.performing_rank.is_(None),
                Job.verifying_rank.is_(None),
            ),
        )
    )
    jobs = jobs_result.scalars().all()
    if not jobs:
        return False

    standards_result = await db.execute(
        select(StandardJob).where(
            StandardJob.tenant_id == tenant_id,
            StandardJob.is_deleted == False,
        )
    )
    standard_jobs = standards_result.scalars().all()
    standards_by_name = {
        _seed_text_key(standard_job.job_name): standard_job
        for standard_job in standard_jobs
        if _seed_text_key(standard_job.job_name)
    }
    standards_by_reference = {
        _seed_text_key(standard_job.library_reference): standard_job
        for standard_job in standard_jobs
        if _seed_text_key(standard_job.library_reference)
    }
    reference_keys = sorted(standards_by_reference, key=len, reverse=True)

    changed = False
    for job in jobs:
        matched_standard = None
        matched_reference = _reference_match_key(job.source_reference, reference_keys)
        if matched_reference:
            matched_standard = standards_by_reference.get(matched_reference)
        if matched_standard is None and job.source_manual_id is None:
            matched_standard = standards_by_name.get(_seed_text_key(job.job_name))

        next_performing_rank, next_verifying_rank = derive_job_ranks_from_library_context(
            job_name=job.job_name,
            source_reference=job.source_reference,
            existing_performing_rank=job.performing_rank,
            existing_verifying_rank=job.verifying_rank,
            matched_standard_job=matched_standard,
        )

        if next_performing_rank != job.performing_rank:
            job.performing_rank = next_performing_rank
            db.add(job)
            changed = True
        if next_verifying_rank != job.verifying_rank:
            job.verifying_rank = next_verifying_rank
            db.add(job)
            changed = True

    if not changed:
        return False

    for job in jobs:
        await ensure_job_rank(db, tenant_id=tenant_id, rank_name=job.performing_rank)
        await ensure_job_rank(db, tenant_id=tenant_id, rank_name=job.verifying_rank)
    await db.commit()
    return True


def derive_manual_job_ranks(
    *,
    job: Job,
    component: Optional[Component] = None,
    matched_standard_job: Optional[StandardJob] = None,
    inferred_component_rank: Optional[str] = None,
) -> tuple[Optional[str], Optional[str]]:
    next_performing_rank = normalize_rank_name(job.performing_rank) or infer_manual_performing_rank(
        job_name=job.job_name,
        component_name=getattr(component, "component_name", None),
        main_machinery=getattr(component, "main_machinery", None),
        group1=getattr(component, "group1", None),
        group2=getattr(component, "group2", None),
        inferred_component_rank=inferred_component_rank,
        matched_standard_job=matched_standard_job,
    )
    next_verifying_rank = normalize_rank_name(job.verifying_rank)
    if not next_verifying_rank and matched_standard_job is not None:
        next_verifying_rank = normalize_rank_name(matched_standard_job.verifying_rank)
    if not next_verifying_rank:
        next_verifying_rank = infer_verifying_rank(
            next_performing_rank,
            job_name=job.job_name,
            machinery_type=" ".join(
                filter(
                    None,
                    [
                        getattr(component, "component_name", None),
                        getattr(component, "main_machinery", None),
                        getattr(component, "group1", None),
                        getattr(component, "group2", None),
                    ],
                )
            ),
        )
    return next_performing_rank, next_verifying_rank


async def backfill_manual_job_ranks(
    db: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    vessel_id: uuid.UUID,
    manual_id: Optional[uuid.UUID] = None,
) -> bool:
    where_clauses = [
        Job.tenant_id == tenant_id,
        Job.vessel_id == vessel_id,
        Job.is_deleted == False,
        Job.source_manual_id.is_not(None),
        or_(
            Job.performing_rank.is_(None),
            Job.verifying_rank.is_(None),
        ),
    ]
    if manual_id is not None:
        where_clauses.append(Job.source_manual_id == manual_id)

    jobs_result = await db.execute(select(Job).where(*where_clauses))
    jobs = jobs_result.scalars().all()
    if not jobs:
        return False

    component_ids = {job.component_id for job in jobs if job.component_id}
    components_by_id: dict[uuid.UUID, Component] = {}
    if component_ids:
        component_result = await db.execute(
            select(Component).where(
                Component.id.in_(component_ids),
                Component.is_deleted == False,
            )
        )
        components_by_id = {component.id: component for component in component_result.scalars().all()}

    standard_jobs_result = await db.execute(
        select(StandardJob).where(
            StandardJob.tenant_id == tenant_id,
            StandardJob.is_deleted == False,
            StandardJob.performing_rank.is_not(None),
        )
    )
    standard_jobs = standard_jobs_result.scalars().all()
    standard_by_name: dict[str, StandardJob] = {}
    for standard_job in standard_jobs:
        key = _seed_text_key(standard_job.job_name)
        if key and key not in standard_by_name:
            standard_by_name[key] = standard_job

    component_rank_result = await db.execute(
        select(
            Job.component_id,
            Job.performing_rank,
            func.count(Job.id),
        )
        .where(
            Job.tenant_id == tenant_id,
            Job.vessel_id == vessel_id,
            Job.is_deleted == False,
            Job.component_id.is_not(None),
            Job.performing_rank.is_not(None),
        )
        .group_by(Job.component_id, Job.performing_rank)
        .order_by(Job.component_id, func.count(Job.id).desc(), Job.performing_rank.asc())
    )
    inferred_component_ranks: dict[uuid.UUID, str] = {}
    for component_id, performing_rank, _count in component_rank_result.all():
        if component_id not in inferred_component_ranks and performing_rank:
            inferred_component_ranks[component_id] = performing_rank

    changed = False
    for job in jobs:
        component = components_by_id.get(job.component_id) if job.component_id else None
        matched_standard_job = None
        for name_variant in _manual_job_name_variants(job.job_name, getattr(component, "component_name", None)):
            matched_standard_job = standard_by_name.get(name_variant)
            if matched_standard_job is not None:
                break
        next_performing_rank, next_verifying_rank = derive_manual_job_ranks(
            job=job,
            component=component,
            matched_standard_job=matched_standard_job,
            inferred_component_rank=inferred_component_ranks.get(job.component_id) if job.component_id else None,
        )
        if next_performing_rank != job.performing_rank:
            job.performing_rank = next_performing_rank
            db.add(job)
            changed = True
        if next_verifying_rank != job.verifying_rank:
            job.verifying_rank = next_verifying_rank
            db.add(job)
            changed = True

    if not changed:
        return False

    for job in jobs:
        await ensure_job_rank(db, tenant_id=tenant_id, rank_name=job.performing_rank)
        await ensure_job_rank(db, tenant_id=tenant_id, rank_name=job.verifying_rank)
    await db.commit()
    return True


async def backfill_job_ranks_from_existing_data(
    db: AsyncSession,
    *,
    tenant_id: uuid.UUID,
) -> None:
    await seed_rank_library_from_audit_sample(db, tenant_id=tenant_id)

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


async def list_rank_names_from_seed_and_existing_data(
    db: AsyncSession,
    *,
    tenant_id: uuid.UUID,
) -> list[str]:
    rank_names: dict[str, str] = {}

    for rank_name in _load_audit_rank_seed().get("known_ranks", []):
        cleaned = normalize_rank_name(rank_name)
        key = _rank_key(cleaned)
        if cleaned and key and key not in rank_names:
            rank_names[key] = cleaned

    rank_queries = [
        select(JobRank.rank_name).where(
            JobRank.tenant_id == tenant_id,
            JobRank.is_deleted == False,
        ),
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
            cleaned = normalize_rank_name(rank_name)
            key = _rank_key(cleaned)
            if cleaned and key and key not in rank_names:
                rank_names[key] = cleaned

    for rank_name in ("Chief Engineer", "Master"):
        key = _rank_key(rank_name)
        if key and key not in rank_names:
            rank_names[key] = rank_name

    return sorted(rank_names.values(), key=lambda value: value.lower())
