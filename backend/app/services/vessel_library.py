from __future__ import annotations

import uuid
from typing import Any, Optional

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.component import Component


async def resolve_vessel_type_id(
    *,
    db: AsyncSession,
    tenant_id: uuid.UUID,
    vessel_type_name: Optional[str],
) -> Optional[str]:
    vessel_type_name = (vessel_type_name or "").strip()
    if not vessel_type_name:
        return None

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
    return str(row[0]) if row else None


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
        select(
            Component.group1,
            Component.group2,
            Component.main_machinery,
            Component.component_name,
        ).where(
            Component.vessel_id == vessel_id,
            Component.tenant_id == tenant_id,
            Component.is_deleted == False,
        )
    )
    existing_keys = {
        (
            (group1 or "").lower().strip(),
            (group2 or "").lower().strip(),
            (main_machinery or "").lower().strip(),
            (component_name or "").lower().strip(),
        )
        for group1, group2, main_machinery, component_name in existing_result.all()
    }

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
        if key in existing_keys:
            skipped += 1
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
        existing_keys.add(key)
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
