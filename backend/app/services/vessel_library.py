from __future__ import annotations

import uuid
from typing import Any, Optional

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.component import Component, QCStatus


async def _single_populated_vessel_type(
    *,
    db: AsyncSession,
    tenant_id: uuid.UUID,
) -> Optional[dict[str, str]]:
    result = await db.execute(
        text(
            "SELECT vt.id, vt.name, COUNT(csl.id) AS component_count "
            "FROM vessel_types vt "
            "LEFT JOIN component_structure_library csl "
            "  ON csl.vessel_type_id = vt.id "
            " AND csl.is_deleted = false "
            " AND csl.status = 'active' "
            "WHERE vt.tenant_id = :tid AND vt.is_deleted = false "
            "GROUP BY vt.id, vt.name "
            "HAVING COUNT(csl.id) > 0 "
            "ORDER BY COUNT(csl.id) DESC, vt.name ASC"
        ),
        {"tid": str(tenant_id)},
    )
    rows = result.mappings().all()
    if len(rows) == 1:
        row = rows[0]
        return {"id": str(row["id"]), "name": str(row["name"])}
    return None


async def resolve_vessel_type_id(
    *,
    db: AsyncSession,
    tenant_id: uuid.UUID,
    vessel_type_name: Optional[str],
) -> Optional[str]:
    vessel_type_name = (vessel_type_name or "").strip()
    if not vessel_type_name:
        fallback = await _single_populated_vessel_type(db=db, tenant_id=tenant_id)
        return fallback["id"] if fallback else None

    result = await db.execute(
        text(
            "SELECT id "
            "FROM vessel_types "
            "WHERE tenant_id = :tid AND is_deleted = false AND lower(name) = lower(:name) "
            "ORDER BY is_system DESC, sort_order ASC, created_at ASC "
            "LIMIT 1"
        ),
        {"tid": str(tenant_id), "name": vessel_type_name},
    )
    row = result.first()
    if row:
        return str(row[0])

    fallback = await _single_populated_vessel_type(db=db, tenant_id=tenant_id)
    return fallback["id"] if fallback else None


async def load_library_components_for_vessel(
    *,
    db: AsyncSession,
    tenant_id: uuid.UUID,
    vessel_id: uuid.UUID,
    vessel_type_name: Optional[str] = None,
    vessel_type_id: Optional[str] = None,
) -> dict[str, Any]:
    resolved_vessel_type_id = vessel_type_id or await resolve_vessel_type_id(
        db=db,
        tenant_id=tenant_id,
        vessel_type_name=vessel_type_name,
    )

    lib_where = "tenant_id = :tid AND status = 'active' AND is_deleted = false"
    lib_params: dict[str, Any] = {"tid": str(tenant_id)}
    if resolved_vessel_type_id:
        lib_where += " AND vessel_type_id = :vtid"
        lib_params["vtid"] = resolved_vessel_type_id

    lib_result = await db.execute(
        text(
            "SELECT group1_name, group2_name, machinery_name, component_name, criticality "
            "FROM component_structure_library "
            f"WHERE {lib_where} "
            "ORDER BY group1_name, group2_name, machinery_name, component_name"
        ),
        lib_params,
    )
    lib_nodes = lib_result.mappings().all()

    if not lib_nodes:
        return {
            "added": 0,
            "skipped": 0,
            "message": "No active library nodes found",
            "vessel_type_id": resolved_vessel_type_id,
        }

    existing_result = await db.execute(
        select(Component).where(
            Component.vessel_id == vessel_id,
            Component.tenant_id == tenant_id,
            Component.is_deleted == False,
        )
    )
    existing_components = existing_result.scalars().all()
    mapped_keys = {
        (
            (component.group1 or "").lower().strip(),
            (component.group2 or "").lower().strip(),
            (component.main_machinery or "").lower().strip(),
            (component.component_name or "").lower().strip(),
        )
        for component in existing_components
        if not component.is_unmapped
    }
    unmapped_by_key: dict[tuple[str, str, str, str], Component] = {}
    for component in existing_components:
        if not component.is_unmapped:
            continue
        key = (
            (component.group1 or "").lower().strip(),
            (component.group2 or "").lower().strip(),
            (component.main_machinery or "").lower().strip(),
            (component.component_name or "").lower().strip(),
        )
        unmapped_by_key.setdefault(key, component)

    added = 0
    skipped = 0
    for node in lib_nodes:
        g1 = (node["group1_name"] or "Uncategorised").strip()
        g2 = (node["group2_name"] or "Uncategorised").strip()
        mm = (node["machinery_name"] or "Unknown").strip()
        cn = (node["component_name"] or "").strip()
        if not cn:
            skipped += 1
            continue

        key = (g1.lower(), g2.lower(), mm.lower(), cn.lower())
        if key in mapped_keys:
            skipped += 1
            continue

        existing_unmapped = unmapped_by_key.get(key)
        if existing_unmapped:
            existing_unmapped.is_unmapped = False
            existing_unmapped.qc_status = QCStatus.accepted
            if not existing_unmapped.confidence_score:
                existing_unmapped.confidence_score = 100
            db.add(existing_unmapped)
            mapped_keys.add(key)
            added += 1
            continue

        node_criticality = str(node.get("criticality") or "non_critical")
        await db.execute(
            text(
                "INSERT INTO components "
                "(id, tenant_id, vessel_id, group1, group2, main_machinery, component_name, "
                "is_critical, criticality, qc_status, is_unmapped, confidence_score, is_deleted, "
                "created_at, updated_at) "
                "VALUES (:id, :tid, :vid, :g1, :g2, :mm, :cn, "
                "false, :crit, 'accepted', false, 100, false, NOW(), NOW())"
            ),
            {
                "id": str(uuid.uuid4()),
                "tid": str(tenant_id),
                "vid": str(vessel_id),
                "g1": g1,
                "g2": g2,
                "mm": mm,
                "cn": cn,
                "crit": node_criticality,
            },
        )
        mapped_keys.add(key)
        added += 1

    return {
        "added": added,
        "skipped": skipped,
        "message": None,
        "vessel_type_id": resolved_vessel_type_id,
    }


async def ensure_vessel_library_baseline(
    *,
    db: AsyncSession,
    tenant_id: uuid.UUID,
    vessel_id: uuid.UUID,
    vessel_type_name: Optional[str],
) -> dict[str, Any]:
    existing_count = await db.scalar(
        select(func.count())
        .select_from(Component)
        .where(
            Component.vessel_id == vessel_id,
            Component.tenant_id == tenant_id,
            Component.is_deleted == False,
            Component.is_unmapped == False,
        )
    )
    if (existing_count or 0) > 0:
        return {"added": 0, "skipped": 0, "message": "Baseline already loaded"}

    result = await load_library_components_for_vessel(
        db=db,
        tenant_id=tenant_id,
        vessel_id=vessel_id,
        vessel_type_name=vessel_type_name,
    )
    if result.get("added"):
        await db.commit()
    return result
