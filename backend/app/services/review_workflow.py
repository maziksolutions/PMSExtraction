from __future__ import annotations

import json
import uuid
from typing import Any, Iterable, Optional

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.activity import ActivityEntry
from app.models.component import Component
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


def _as_uuid_str(value: uuid.UUID | str) -> str:
    return str(value)


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
    if result.scalar_one_or_none() is not None:
        return

    await db.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS maker_models (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                tenant_id UUID NOT NULL,
                maker VARCHAR(255) NOT NULL,
                model VARCHAR(255),
                component_category VARCHAR(100),
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
) -> None:
    maker_value = (maker or "").strip()
    model_value = (model or "").strip() or None
    category_value = (component_category or "").strip() or None
    if not maker_value:
        return

    await ensure_maker_models_table(db)
    await db.execute(
        text(
            """
            INSERT INTO maker_models (id, tenant_id, maker, model, component_category)
            VALUES (gen_random_uuid(), :tid, :maker, :model, :category)
            ON CONFLICT DO NOTHING
            """
        ),
        {
            "tid": _as_uuid_str(tenant_id),
            "maker": maker_value,
            "model": model_value,
            "category": category_value,
        },
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
        "spare_maker": spare.spare_maker or "",
        "spare_model": spare.spare_model or "",
    }


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


async def _upsert_global_library_record(
    db: AsyncSession,
    *,
    table: str,
    tenant_id: uuid.UUID,
    vessel_id: uuid.UUID,
    record: dict[str, Any],
    existing_rows: list[dict[str, Any]],
    entity_type: str,
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
    if duplicate_match is not None:
        source_vessels = list(duplicate_match["source_vessels"])
        if vessel_id_str not in source_vessels:
            source_vessels.append(vessel_id_str)
        occurrence_count = max(int(duplicate_match["occurrence_count"]), len(source_vessels))
        await db.execute(
            text(
                f"UPDATE {table} "
                "SET canonical_data = :cd::jsonb, "
                "    source_vessels = :sv::jsonb, "
                "    occurrence_count = :count, "
                "    last_confirmed_at = NOW(), "
                "    updated_at = NOW() "
                "WHERE id = :id"
            ),
            {
                "cd": json.dumps(record),
                "sv": json.dumps(source_vessels),
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
        text(
            f"INSERT INTO {table} "
            "(id, tenant_id, canonical_data, occurrence_count, source_vessels, first_seen_at, "
            " last_confirmed_at, created_at, updated_at, is_deleted) "
            "VALUES (:id, :tid, :cd::jsonb, 1, :sv::jsonb, NOW(), NOW(), NOW(), NOW(), false)"
        ),
        {
            "id": new_id,
            "tid": _as_uuid_str(tenant_id),
            "cd": json.dumps(record),
            "sv": json.dumps([vessel_id_str]),
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


async def sync_components_to_global_library(
    db: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    vessel_id: uuid.UUID,
    components: Iterable[Component],
) -> dict[str, int]:
    table = _GLOBAL_TABLE_MAP["component"]
    existing_rows = await _load_existing_global_entries(db, table=table, tenant_id=tenant_id)
    added = duplicates = 0
    for component in components:
        record = _component_record(component)
        was_added, was_duplicate = await _upsert_global_library_record(
            db,
            table=table,
            tenant_id=tenant_id,
            vessel_id=vessel_id,
            record=record,
            existing_rows=existing_rows,
            entity_type="component",
        )
        added += int(was_added)
        duplicates += int(was_duplicate)
        await upsert_maker_model_library_entry(
            db,
            tenant_id=tenant_id,
            maker=component.maker,
            model=component.model,
            component_category=component.group1,
        )
    return {"added": added, "duplicates": duplicates}


async def sync_jobs_to_global_library(
    db: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    vessel_id: uuid.UUID,
    jobs: Iterable[Job],
) -> dict[str, int]:
    table = _GLOBAL_TABLE_MAP["job"]
    existing_rows = await _load_existing_global_entries(db, table=table, tenant_id=tenant_id)
    added = duplicates = 0
    for job in jobs:
        record = _job_record(job)
        was_added, was_duplicate = await _upsert_global_library_record(
            db,
            table=table,
            tenant_id=tenant_id,
            vessel_id=vessel_id,
            record=record,
            existing_rows=existing_rows,
            entity_type="job",
        )
        added += int(was_added)
        duplicates += int(was_duplicate)
    return {"added": added, "duplicates": duplicates}


async def sync_spares_to_global_library(
    db: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    vessel_id: uuid.UUID,
    spares: Iterable[Spare],
) -> dict[str, int]:
    table = _GLOBAL_TABLE_MAP["spare"]
    existing_rows = await _load_existing_global_entries(db, table=table, tenant_id=tenant_id)
    added = duplicates = 0
    for spare in spares:
        record = _spare_record(spare)
        was_added, was_duplicate = await _upsert_global_library_record(
            db,
            table=table,
            tenant_id=tenant_id,
            vessel_id=vessel_id,
            record=record,
            existing_rows=existing_rows,
            entity_type="spare",
        )
        added += int(was_added)
        duplicates += int(was_duplicate)
        await upsert_maker_model_library_entry(
            db,
            tenant_id=tenant_id,
            maker=spare.spare_maker,
            model=spare.spare_model,
            component_category="spare",
        )
    return {"added": added, "duplicates": duplicates}
