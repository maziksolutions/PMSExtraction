from __future__ import annotations

import json
import uuid

from typing import Any, Iterable, Optional

from sqlalchemy import bindparam, select, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.activity import ActivityEntry
from app.models.component import Component, QCStatus
from app.models.job import Job
from app.models.spare import Spare
from app.services.deduplication import (
    is_duplicate_component,
    is_duplicate_job,
    is_duplicate_spare,
)
from app.websocket import manager

_GLOBAL_TABLE_MAP = {
    "component": "global_component_library",
    "job": "global_job_library",
    "spare": "global_spare_library",
}


def _jsonb_typed_text(sql: str):
    return text(sql).bindparams(
        bindparam("cd", type_=JSONB),
        bindparam("sv", type_=JSONB),
    )


def _as_uuid_str(value: uuid.UUID | str) -> str:
    return str(value)


def _normalized_signature_payload(record: dict[str, Any]) -> dict[str, Any]:
    normalized: dict[str, Any] = {}
    for key, value in record.items():
        if key == "id":
            continue
        if isinstance(value, str):
            normalized[key] = " ".join(value.strip().lower().split())
        elif value is None:
            normalized[key] = None
        else:
            normalized[key] = value
    return normalized


def _canonical_library_record(record: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in record.items() if key != "id"}


def _library_signature(record: dict[str, Any]) -> str:
    return json.dumps(_normalized_signature_payload(record), sort_keys=True, default=str)


def _activity_event_payload(entry: ActivityEntry) -> dict[str, Any]:
    cached = getattr(entry, "_event_payload", None)
    if cached:
        return cached
    payload = {
        "id": str(entry.id),
        "action_type": entry.action_type,
        "entity_type": entry.entity_type,
        "entity_id": str(entry.entity_id),
        "description": entry.description,
        "created_at": entry.created_at.isoformat() if entry.created_at else "",
        "user_id": str(entry.user_id),
        "vessel_id": str(entry.vessel_id),
    }
    setattr(entry, "_event_payload", payload)
    return payload


async def ensure_maker_models_table(db: AsyncSession) -> None:
    result = await db.execute(
        text(
            "SELECT 1 FROM information_schema.tables "
            "WHERE table_schema = 'public' AND table_name = 'maker_models'"
        )
    )
    if result.scalar_one_or_none() is None:
        await db.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS maker_models (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    tenant_id UUID NOT NULL,
                    maker VARCHAR(255) NOT NULL,
                    model VARCHAR(255),
                    component_category VARCHAR(100),
                    is_system_generated BOOLEAN NOT NULL DEFAULT false,
                    is_deleted BOOLEAN NOT NULL DEFAULT false,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """
            )
        )
    await db.execute(
        text(
            """
            ALTER TABLE maker_models
            ADD COLUMN IF NOT EXISTS is_system_generated BOOLEAN NOT NULL DEFAULT false
            """
        )
    )
    await db.execute(
        text(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS uq_maker_models_tenant_maker_model
            ON maker_models (tenant_id, maker, COALESCE(model, ''))
            WHERE is_deleted = false
            """
        )
    )


async def ensure_global_library_tables(db: AsyncSession) -> None:
    for table_name in _GLOBAL_TABLE_MAP.values():
        await db.execute(
            text(
                f"""
                CREATE TABLE IF NOT EXISTS {table_name} (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    tenant_id UUID NOT NULL,
                    canonical_data JSONB NOT NULL,
                    source_vessels JSONB NOT NULL DEFAULT '[]'::jsonb,
                    occurrence_count INTEGER NOT NULL DEFAULT 1,
                    first_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    last_confirmed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    is_deleted BOOLEAN NOT NULL DEFAULT false
                )
                """
            )
        )
        await db.execute(
            text(
                f"""
                CREATE INDEX IF NOT EXISTS ix_{table_name}_tenant_id
                ON {table_name} (tenant_id)
                """
            )
        )


async def upsert_maker_model_library_entry(
    db: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    maker: Optional[str],
    model: Optional[str],
    component_category: Optional[str] = None,
    is_system_generated: bool = True,
) -> None:
    maker_value = (maker or "").strip()
    model_value = (model or "").strip() or None
    category_value = (component_category or "").strip() or None
    if not maker_value:
        return

    await ensure_maker_models_table(db)

    deleted_match = await db.execute(
        text(
            """
            SELECT id FROM maker_models
            WHERE tenant_id = :tid
              AND maker = :maker
              AND COALESCE(model, '') = COALESCE(:model, '')
              AND is_deleted = true
            LIMIT 1
            """
        ),
        {
            "tid": _as_uuid_str(tenant_id),
            "maker": maker_value,
            "model": model_value,
        },
    )
    if deleted_match.scalar_one_or_none() is not None:
        return
    active_match = await db.execute(
        text(
            """
            SELECT id, component_category, is_system_generated
            FROM maker_models
            WHERE tenant_id = :tid
              AND maker = :maker
              AND COALESCE(model, '') = COALESCE(:model, '')
              AND is_deleted = false
            LIMIT 1
            """
        ),
        {
            "tid": _as_uuid_str(tenant_id),
            "maker": maker_value,
            "model": model_value,
        },
    )
    active_row = active_match.mappings().first()
    if active_row is not None:
        should_update = bool(active_row["is_system_generated"]) and (
            active_row["component_category"] != category_value
            or bool(active_row["is_system_generated"]) != is_system_generated
        )
        if should_update:
            await db.execute(
                text(
                    """
                    UPDATE maker_models
                    SET component_category = :category,
                        is_system_generated = :is_system_generated,
                        updated_at = NOW()
                    WHERE id = :id
                    """
                ),
                {
                    "id": str(active_row["id"]),
                    "category": category_value,
                    "is_system_generated": is_system_generated,
                },
            )
        return
    await db.execute(
        text(
            """
            INSERT INTO maker_models (id, tenant_id, maker, model, component_category, is_system_generated)
            VALUES (gen_random_uuid(), :tid, :maker, :model, :category, :is_system_generated)
            ON CONFLICT DO NOTHING
            """
        ),
        {
            "tid": _as_uuid_str(tenant_id),
            "maker": maker_value,
            "model": model_value,
            "category": category_value,
            "is_system_generated": is_system_generated,
        },
    )


def _maker_model_signature(maker: Optional[str], model: Optional[str]) -> str:
    return json.dumps(
        {
            "maker": " ".join((maker or "").strip().lower().split()),
            "model": " ".join((model or "").strip().lower().split()),
        },
        sort_keys=True,
    )


async def _reconcile_maker_model_library(
    db: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    desired_entries: list[dict[str, Optional[str]]],
) -> None:
    await ensure_maker_models_table(db)
    active_result = await db.execute(
        text(
            """
            SELECT id, maker, model, component_category
            FROM maker_models
            WHERE tenant_id = :tid
              AND is_deleted = false
              AND is_system_generated = true
            """
        ),
        {"tid": _as_uuid_str(tenant_id)},
    )
    active_rows = {
        _maker_model_signature(row["maker"], row["model"]): row
        for row in active_result.mappings().all()
    }
    deleted_result = await db.execute(
        text(
            """
            SELECT maker, model
            FROM maker_models
            WHERE tenant_id = :tid
              AND is_deleted = true
            """
        ),
        {"tid": _as_uuid_str(tenant_id)},
    )
    deleted_signatures = {
        _maker_model_signature(row["maker"], row["model"])
        for row in deleted_result.mappings().all()
    }

    desired_map: dict[str, dict[str, Optional[str]]] = {}
    for entry in desired_entries:
        maker = (entry.get("maker") or "").strip()
        model = (entry.get("model") or "").strip() or None
        if not maker:
            continue
        signature = _maker_model_signature(maker, model)
        if signature in deleted_signatures:
            continue
        desired_map[signature] = {
            "maker": maker,
            "model": model,
            "component_category": (entry.get("component_category") or "").strip() or None,
        }

    for signature, desired in desired_map.items():
        active = active_rows.pop(signature, None)
        if active is None:
            await db.execute(
                text(
                    """
                    INSERT INTO maker_models (id, tenant_id, maker, model, component_category, is_system_generated)
                    VALUES (gen_random_uuid(), :tid, :maker, :model, :category, true)
                    ON CONFLICT DO NOTHING
                    """
                ),
                {
                    "tid": _as_uuid_str(tenant_id),
                    "maker": desired["maker"],
                    "model": desired["model"],
                    "category": desired["component_category"],
                },
            )
            continue

        if active["component_category"] != desired["component_category"]:
            await db.execute(
                text(
                    """
                    UPDATE maker_models
                    SET component_category = :category,
                        updated_at = NOW()
                    WHERE id = :id
                    """
                ),
                {
                    "id": str(active["id"]),
                    "category": desired["component_category"],
                },
            )

    for stale in active_rows.values():
        await db.execute(
            text(
                """
                UPDATE maker_models
                SET is_deleted = true,
                    updated_at = NOW()
                WHERE id = :id
                """
            ),
            {"id": str(stale["id"])},
        )


async def log_activity(
    db: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    vessel_id: uuid.UUID,
    user_id: uuid.UUID,
    action_type: str,
    entity_type: str,
    entity_id: uuid.UUID,
    description: str,
    metadata: Optional[dict[str, Any]] = None,
) -> ActivityEntry:
    entry = ActivityEntry(
        tenant_id=tenant_id,
        vessel_id=vessel_id,
        user_id=user_id,
        action_type=action_type,
        entity_type=entity_type,
        entity_id=entity_id,
        description=description[:500],
        metadata_json=metadata,
    )
    db.add(entry)
    await db.flush()
    _activity_event_payload(entry)
    return entry


async def broadcast_activity(entry: ActivityEntry | dict[str, Any]) -> None:
    payload = entry if isinstance(entry, dict) else _activity_event_payload(entry)
    await manager.broadcast_to_vessel(
        str(payload["vessel_id"]),
        {
            "type": "activity",
            "event": {
                "id": str(payload["id"]),
                "action_type": payload["action_type"],
                "entity_type": payload["entity_type"],
                "entity_id": str(payload["entity_id"]),
                "description": payload["description"],
                "created_at": payload["created_at"],
                "user_id": str(payload["user_id"]),
            },
        },
    )


def _component_record(component: Component) -> dict[str, Any]:
    return {
        "id": str(component.id),
        "group1": component.group1,
        "group2": component.group2,
        "main_machinery": component.main_machinery,
        "component_name": component.component_name,
        "maker": component.maker or "",
        "model": component.model or "",
        "location": component.location or "",
        "machinery_particulars": component.machinery_particulars or "",
        "specification": component.specification or "",
    }


def _job_record(job: Job) -> dict[str, Any]:
    return {
        "id": str(job.id),
        "job_name": job.job_name,
        "job_code": job.job_code or "",
        "job_description": job.job_description or "",
        "frequency": job.frequency,
        "frequency_type": job.frequency_type.value if job.frequency_type else None,
        "cms_id": job.cms_id or "",
    }


def _spare_record(spare: Spare) -> dict[str, Any]:
    return {
        "id": str(spare.id),
        "part_name": spare.part_name,
        "part_number": spare.part_number or "",
        "drawing_number": spare.drawing_number or "",
        "drawing_position": spare.drawing_position or "",
        "specification": spare.specification or "",
        "spare_assembly": spare.spare_assembly or spare.spare_model or "",
        "assembly_description": spare.assembly_description or spare.spare_assembly or spare.spare_model or "",
        "spare_maker": spare.spare_maker or "",
        "spare_model": spare.spare_model or "",
    }


def _component_is_manual_derived(component: Component) -> bool:
    return bool(
        component.source_manual_id
        or component.pdf_reference
        or component.page_reference is not None
        or component.job_pages
        or component.spare_pages
    )


async def _load_existing_global_entries(
    db: AsyncSession,
    *,
    table: str,
    tenant_id: uuid.UUID,
) -> list[dict[str, Any]]:
    await ensure_global_library_tables(db)
    existing_result = await db.execute(
        text(
            f"SELECT id, canonical_data, source_vessels, occurrence_count "
            f"FROM {table} WHERE tenant_id = :tid AND is_deleted = false"
        ),
        {"tid": _as_uuid_str(tenant_id)},
    )
    rows = existing_result.mappings().all()
    items: list[dict[str, Any]] = []
    for row in rows:
        raw_data = row["canonical_data"]
        if isinstance(raw_data, str):
            try:
                raw_data = json.loads(raw_data)
            except Exception:
                raw_data = {}
        items.append(
            {
                "id": str(row["id"]),
                "data": raw_data or {},
                "source_vessels": list(row["source_vessels"] or []),
                "occurrence_count": int(row["occurrence_count"] or 1),
            }
    )
    return items


async def _load_deleted_global_signatures(
    db: AsyncSession,
    *,
    table: str,
    tenant_id: uuid.UUID,
) -> set[str]:
    await ensure_global_library_tables(db)
    deleted_result = await db.execute(
        text(
            f"SELECT canonical_data "
            f"FROM {table} WHERE tenant_id = :tid AND is_deleted = true"
        ),
        {"tid": _as_uuid_str(tenant_id)},
    )
    signatures: set[str] = set()
    for (raw_data,) in deleted_result.all():
        if isinstance(raw_data, str):
            try:
                raw_data = json.loads(raw_data)
            except Exception:
                raw_data = {}
        signatures.add(_library_signature(raw_data or {}))
    return signatures


async def _upsert_global_library_record(
    db: AsyncSession,
    *,
    table: str,
    tenant_id: uuid.UUID,
    vessel_id: uuid.UUID,
    record: dict[str, Any],
    existing_rows: list[dict[str, Any]],
    entity_type: str,
    deleted_signatures: set[str] | None = None,
) -> tuple[bool, bool]:
    duplicate_match: Optional[dict[str, Any]] = None
    for existing in existing_rows:
        if entity_type == "component" and is_duplicate_component(record, existing["data"]):
            duplicate_match = existing
            break
        if entity_type == "job" and is_duplicate_job(record, existing["data"]):
            duplicate_match = existing
            break
        if entity_type == "spare" and is_duplicate_spare(record, existing["data"]):
            duplicate_match = existing
            break

    vessel_id_str = _as_uuid_str(vessel_id)
    deleted_signatures = deleted_signatures or set()
    if duplicate_match is None and _library_signature(record) in deleted_signatures:
        return False, False

    if duplicate_match is not None:
        source_vessels = list(duplicate_match["source_vessels"])
        if vessel_id_str not in source_vessels:
            source_vessels.append(vessel_id_str)
        occurrence_count = max(int(duplicate_match["occurrence_count"]), len(source_vessels))
        await db.execute(
            _jsonb_typed_text(
                f"UPDATE {table} "
                "SET canonical_data = :cd, "
                "    source_vessels = :sv, "
                "    occurrence_count = :count, "
                "    last_confirmed_at = NOW(), "
                "    updated_at = NOW() "
                "WHERE id = :id"
            ),
            {
                "cd": record,
                "sv": source_vessels,
                "count": occurrence_count,
                "id": duplicate_match["id"],
            },
        )
        duplicate_match["data"] = record
        duplicate_match["source_vessels"] = source_vessels
        duplicate_match["occurrence_count"] = occurrence_count
        return False, True

    new_id = str(uuid.uuid4())
    await db.execute(
        _jsonb_typed_text(
            f"INSERT INTO {table} "
            "(id, tenant_id, canonical_data, occurrence_count, source_vessels, first_seen_at, "
            " last_confirmed_at, created_at, updated_at, is_deleted) "
            "VALUES (:id, :tid, :cd, 1, :sv, NOW(), NOW(), NOW(), NOW(), false)"
        ),
        {
            "id": new_id,
            "tid": _as_uuid_str(tenant_id),
            "cd": record,
            "sv": [vessel_id_str],
        },
    )
    existing_rows.append(
        {
            "id": new_id,
            "data": record,
            "source_vessels": [vessel_id_str],
            "occurrence_count": 1,
        }
    )
    return True, False


def _records_match(entity_type: str, left: dict[str, Any], right: dict[str, Any]) -> bool:
    if entity_type == "component":
        return is_duplicate_component(left, right)
    if entity_type == "job":
        return is_duplicate_job(left, right)
    if entity_type == "spare":
        return is_duplicate_spare(left, right)
    return False


async def _reconcile_global_library_records(
    db: AsyncSession,
    *,
    table: str,
    tenant_id: uuid.UUID,
    entity_type: str,
    desired_records: list[dict[str, Any]],
) -> dict[str, int]:
    existing_rows = await _load_existing_global_entries(db, table=table, tenant_id=tenant_id)
    deleted_signatures = await _load_deleted_global_signatures(db, table=table, tenant_id=tenant_id)
    unmatched_existing = existing_rows.copy()

    added = 0
    updated = 0
    removed = 0
    skipped_deleted = 0

    for desired in desired_records:
        if _library_signature(desired["data"]) in deleted_signatures:
            skipped_deleted += 1
            continue

        match_index = next(
            (
                index
                for index, existing in enumerate(unmatched_existing)
                if _records_match(entity_type, desired["data"], existing["data"])
            ),
            None,
        )

        if match_index is None:
            new_id = str(uuid.uuid4())
            await db.execute(
                _jsonb_typed_text(
                    f"INSERT INTO {table} "
                    "(id, tenant_id, canonical_data, occurrence_count, source_vessels, first_seen_at, "
                    " last_confirmed_at, created_at, updated_at, is_deleted) "
                    "VALUES (:id, :tid, :cd, :count, :sv, NOW(), NOW(), NOW(), NOW(), false)"
                ),
                {
                    "id": new_id,
                    "tid": _as_uuid_str(tenant_id),
                    "cd": desired["data"],
                    "count": desired["occurrence_count"],
                    "sv": desired["source_vessels"],
                },
            )
            added += 1
            continue

        existing = unmatched_existing.pop(match_index)
        source_vessels = list(desired["source_vessels"])
        should_update = (
            existing["data"] != desired["data"]
            or list(existing["source_vessels"]) != source_vessels
            or int(existing["occurrence_count"]) != int(desired["occurrence_count"])
        )
        if should_update:
            await db.execute(
                _jsonb_typed_text(
                    f"UPDATE {table} "
                    "SET canonical_data = :cd, "
                    "    source_vessels = :sv, "
                    "    occurrence_count = :count, "
                    "    last_confirmed_at = NOW(), "
                    "    updated_at = NOW() "
                    "WHERE id = :id"
                ),
                {
                    "id": existing["id"],
                    "cd": desired["data"],
                    "sv": source_vessels,
                    "count": desired["occurrence_count"],
                },
            )
            updated += 1

    for stale in unmatched_existing:
        await db.execute(
            text(
                f"UPDATE {table} "
                "SET is_deleted = true, updated_at = NOW() "
                "WHERE id = :id"
            ),
            {"id": stale["id"]},
        )
        removed += 1

    return {
        "added": added,
        "updated": updated,
        "removed": removed,
        "skipped_deleted": skipped_deleted,
    }


def _collapse_records_for_library(
    *,
    entity_type: str,
    records: list[dict[str, Any]],
) -> dict[str, Any]:
    desired_groups: list[dict[str, Any]] = []
    duplicates = 0

    for item in records:
        candidate = _canonical_library_record(item["data"])
        vessel_id_str = item["vessel_id"]
        match = next(
            (group for group in desired_groups if _records_match(entity_type, candidate, group["data"])),
            None,
        )
        if match is None:
            desired_groups.append(
                {
                    "data": candidate,
                    "source_vessels": [vessel_id_str],
                    "occurrence_count": 1,
                }
            )
            continue

        duplicates += 1
        if vessel_id_str not in match["source_vessels"]:
            match["source_vessels"].append(vessel_id_str)
        match["occurrence_count"] += 1

    for group in desired_groups:
        group["source_vessels"] = sorted(group["source_vessels"])

    return {"desired_groups": desired_groups, "duplicates": duplicates}


async def sync_components_to_global_library(
    db: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    vessel_id: uuid.UUID,
    components: Iterable[Component],
) -> dict[str, int]:
    for component in components:
        await upsert_maker_model_library_entry(
            db,
            tenant_id=tenant_id,
            maker=component.maker,
            model=component.model,
            component_category=component.group1,
        )
    await backfill_maker_models_from_accepted_records(db, tenant_id=tenant_id)
    return await backfill_global_library_from_accepted_records(
        db,
        tenant_id=tenant_id,
        entity_type="component",
    )


async def sync_jobs_to_global_library(
    db: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    vessel_id: uuid.UUID,
    jobs: Iterable[Job],
) -> dict[str, int]:
    return await backfill_global_library_from_accepted_records(
        db,
        tenant_id=tenant_id,
        entity_type="job",
    )


async def sync_spares_to_global_library(
    db: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    vessel_id: uuid.UUID,
    spares: Iterable[Spare],
) -> dict[str, int]:
    for spare in spares:
        await upsert_maker_model_library_entry(
            db,
            tenant_id=tenant_id,
            maker=spare.spare_maker,
            model=spare.spare_model,
            component_category="spare",
        )
    await backfill_maker_models_from_accepted_records(db, tenant_id=tenant_id)
    return await backfill_global_library_from_accepted_records(
        db,
        tenant_id=tenant_id,
        entity_type="spare",
    )


async def backfill_maker_models_from_accepted_records(
    db: AsyncSession,
    *,
    tenant_id: uuid.UUID,
) -> None:
    desired_entries: list[dict[str, Optional[str]]] = []
    component_result = await db.execute(
        select(Component).where(
            Component.tenant_id == tenant_id,
            Component.qc_status == QCStatus.accepted,
            Component.is_deleted == False,
        )
    )
    for component in component_result.scalars().all():
        if not _component_is_manual_derived(component):
            continue
        desired_entries.append(
            {
                "maker": component.maker,
                "model": component.model,
                "component_category": component.group1,
            }
        )

    spare_result = await db.execute(
        select(Spare).where(
            Spare.tenant_id == tenant_id,
            Spare.qc_status == QCStatus.accepted,
            Spare.source_manual_id.is_not(None),
            Spare.is_deleted == False,
        )
    )
    for spare in spare_result.scalars().all():
        desired_entries.append(
            {
                "maker": spare.spare_maker,
                "model": spare.spare_model,
                "component_category": "spare",
            }
        )

    await _reconcile_maker_model_library(
        db,
        tenant_id=tenant_id,
        desired_entries=desired_entries,
    )


async def backfill_global_library_from_accepted_records(
    db: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    entity_type: str,
) -> dict[str, int]:
    await ensure_global_library_tables(db)
    if entity_type == "component":
        result = await db.execute(
            select(Component).where(
                Component.tenant_id == tenant_id,
                Component.qc_status == QCStatus.accepted,
                Component.is_deleted == False,
            )
        )
        components = [
            component
            for component in result.scalars().all()
            if _component_is_manual_derived(component)
        ]
        collapsed = _collapse_records_for_library(
            entity_type="component",
            records=[
                {"vessel_id": _as_uuid_str(component.vessel_id), "data": _component_record(component)}
                for component in components
            ],
        )
        totals = await _reconcile_global_library_records(
            db,
            table=_GLOBAL_TABLE_MAP["component"],
            tenant_id=tenant_id,
            entity_type="component",
            desired_records=collapsed["desired_groups"],
        )
        totals["duplicates"] = collapsed["duplicates"]
        return totals

    if entity_type == "job":
        result = await db.execute(
            select(Job).where(
                Job.tenant_id == tenant_id,
                Job.qc_status == QCStatus.accepted,
                Job.source_manual_id.is_not(None),
                Job.is_deleted == False,
            )
        )
        collapsed = _collapse_records_for_library(
            entity_type="job",
            records=[
                {"vessel_id": _as_uuid_str(job.vessel_id), "data": _job_record(job)}
                for job in result.scalars().all()
            ],
        )
        totals = await _reconcile_global_library_records(
            db,
            table=_GLOBAL_TABLE_MAP["job"],
            tenant_id=tenant_id,
            entity_type="job",
            desired_records=collapsed["desired_groups"],
        )
        totals["duplicates"] = collapsed["duplicates"]
        return totals

    if entity_type == "spare":
        result = await db.execute(
            select(Spare).where(
                Spare.tenant_id == tenant_id,
                Spare.qc_status == QCStatus.accepted,
                Spare.source_manual_id.is_not(None),
                Spare.is_deleted == False,
            )
        )
        collapsed = _collapse_records_for_library(
            entity_type="spare",
            records=[
                {"vessel_id": _as_uuid_str(spare.vessel_id), "data": _spare_record(spare)}
                for spare in result.scalars().all()
            ],
        )
        totals = await _reconcile_global_library_records(
            db,
            table=_GLOBAL_TABLE_MAP["spare"],
            tenant_id=tenant_id,
            entity_type="spare",
            desired_records=collapsed["desired_groups"],
        )
        totals["duplicates"] = collapsed["duplicates"]
        return totals

    return {"added": 0, "updated": 0, "removed": 0, "duplicates": 0, "skipped_deleted": 0}
