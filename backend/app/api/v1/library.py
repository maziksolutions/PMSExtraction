from __future__ import annotations

import hashlib
import io
import uuid
from typing import Annotated, Any, Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user
from app.models.component import Component, QCStatus as CompQCStatus
from app.models.ingestion import Manual
from app.models.job import Job
from app.models.spare import Spare
from app.models.user import User
from app.models.vessel import VesselProject
from app.services.deduplication import is_duplicate_component, is_duplicate_job, is_duplicate_spare

router = APIRouter()

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _get_vessel_or_404(vessel_id: uuid.UUID, db: AsyncSession) -> VesselProject:
    result = await db.execute(
        select(VesselProject).where(
            VesselProject.id == vessel_id,
            VesselProject.is_deleted == False,
        )
    )
    vessel = result.scalar_one_or_none()
    if vessel is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Vessel not found")
    return vessel


# ===========================================================================
# F-03: Component Structure Library
# ===========================================================================


@router.post(
    "/library/component-structure/import",
    status_code=status.HTTP_201_CREATED,
    summary="F-03: Import component structure library from Excel/CSV",
)
async def import_component_structure(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    file: UploadFile = File(...),
) -> dict[str, Any]:
    """
    Parse an Excel (.xlsx) or CSV file and bulk-insert component_structure_library rows.
    Expected columns (case-insensitive): group1_code, group1_name, group2_code, group2_name,
    machinery_code, machinery_name, component_code, component_name, component_type,
    is_critical.
    """
    content = await file.read()
    filename = (file.filename or "").lower()

    rows: list[dict] = []
    try:
        if filename.endswith(".csv"):
            import csv
            reader = csv.DictReader(io.StringIO(content.decode("utf-8", errors="replace")))
            rows = [dict(r) for r in reader]
        else:
            import openpyxl
            wb = openpyxl.load_workbook(io.BytesIO(content), read_only=True, data_only=True)
            ws = wb.active
            headers = [
                str(c.value or "").strip().lower()
                for c in next(ws.iter_rows(min_row=1, max_row=1))
            ]
            for row in ws.iter_rows(min_row=2, values_only=True):
                rows.append(
                    {headers[i]: (str(v).strip() if v is not None else "") for i, v in enumerate(row)}
                )
            wb.close()
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Could not parse file: {exc}",
        )

    # Determine current max version for this tenant
    ver_result = await db.execute(
        text(
            "SELECT COALESCE(MAX(version), 0) AS max_ver "
            "FROM component_structure_library "
            "WHERE tenant_id = :tid AND is_deleted = false"
        ),
        {"tid": str(current_user.tenant_id)},
    )
    ver_row = ver_result.mappings().one()
    new_version: int = (ver_row["max_ver"] or 0) + 1

    imported = 0
    for raw in rows:
        # Normalise keys: lowercase, strip, collapse spaces to underscore
        r = {k.lower().strip().replace(" ", "_"): v for k, v in raw.items()}

        # ── Detect column format ──────────────────────────────────────────
        # Format A (user's format): ShipComponentName, HierarchyComponentCode,
        #   ShipComponentCode, ComponentType, Priority, Status, Quantity, Category
        # Format B (legacy): group1_code, group1_name, group2_code, …
        is_user_format = "shipcomponentname" in r

        if is_user_format:
            comp_name = r.get("shipcomponentname", "").strip()
            if not comp_name:
                continue

            hierarchy_code = r.get("hierarchycomponentcode", "").strip()
            ship_code = r.get("shipcomponentcode", "").strip()
            comp_type = r.get("componenttype", "").strip()
            category = r.get("category", "").strip()
            priority = r.get("priority", "").strip().lower()

            # Derive group codes by splitting the dot-notation hierarchy code
            # e.g. "1.001.001.002" → group1="1", group2="1.001", machinery="1.001.001"
            parts = hierarchy_code.split(".")
            group1_code = parts[0] if parts else ""
            group2_code = ".".join(parts[:2]) if len(parts) >= 2 else group1_code
            # If 4-level code, last level is the component; parent 3 = machinery
            if len(parts) >= 4:
                machinery_code = ".".join(parts[:3])
            else:
                machinery_code = hierarchy_code

            is_critical = priority in ("high", "critical")

            mapped = {
                "group1_code": group1_code or None,
                "group1_name": category or "Uncategorised",
                "group2_code": group2_code or None,
                "group2_name": comp_type or category or "Uncategorised",
                "machinery_code": machinery_code or None,
                "machinery_name": comp_type or None,
                "component_code": ship_code or None,
                "component_name": comp_name,
                "component_type": comp_type or None,
                "is_critical": is_critical,
            }
        else:
            comp_name = r.get("component_name", "").strip()
            if not comp_name:
                continue
            critical_raw = str(r.get("is_critical", "")).lower()
            mapped = {
                "group1_code": r.get("group1_code", "") or None,
                "group1_name": r.get("group1_name", "") or None,
                "group2_code": r.get("group2_code", "") or None,
                "group2_name": r.get("group2_name", "") or None,
                "machinery_code": r.get("machinery_code", "") or None,
                "machinery_name": r.get("machinery_name", "") or None,
                "component_code": r.get("component_code", "") or None,
                "component_name": comp_name,
                "component_type": r.get("component_type", "") or None,
                "is_critical": critical_raw in ("yes", "true", "1", "y"),
            }

        await db.execute(
            text(
                "INSERT INTO component_structure_library "
                "(id, tenant_id, group1_code, group1_name, group2_code, group2_name, "
                "machinery_code, machinery_name, component_code, component_name, "
                "component_type, is_critical, version, status, is_deleted) "
                "VALUES (:id, :tid, :g1c, :g1n, :g2c, :g2n, :mc, :mn, :cc, :cn, "
                ":ct, :ic, :ver, 'active', false)"
            ),
            {
                "id": str(uuid.uuid4()),
                "tid": str(current_user.tenant_id),
                "g1c": mapped["group1_code"],
                "g1n": mapped["group1_name"],
                "g2c": mapped["group2_code"],
                "g2n": mapped["group2_name"],
                "mc": mapped["machinery_code"],
                "mn": mapped["machinery_name"],
                "cc": mapped["component_code"],
                "cn": mapped["component_name"],
                "ct": mapped["component_type"],
                "ic": mapped["is_critical"],
                "ver": new_version,
            },
        )
        imported += 1

    await db.commit()
    return {"imported": imported, "version": new_version}


@router.get(
    "/library/component-structure",
    summary="F-03: List all component structure library nodes for tenant",
)
async def list_component_structure(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    status_filter: Optional[str] = Query(None, alias="status"),
    page: int = Query(1, ge=1),
    page_size: int = Query(100, ge=1, le=500),
) -> dict[str, Any]:
    """List component structure library nodes, optionally filtered by status."""
    where_extra = "AND status = :st " if status_filter else ""
    result = await db.execute(
        text(
            "SELECT id, group1_code, group1_name, group2_code, group2_name, "
            "machinery_code, machinery_name, component_code, component_name, "
            "component_type, is_critical, status, version, created_at "
            "FROM component_structure_library "
            f"WHERE tenant_id = :tid AND is_deleted = false {where_extra}"
            "ORDER BY group1_name, group2_name, machinery_name, component_name "
            f"LIMIT {page_size} OFFSET {(page - 1) * page_size}"
        ),
        {"tid": str(current_user.tenant_id), "st": status_filter},
    )
    rows = result.mappings().all()
    return {"items": [dict(r) for r in rows], "page": page, "page_size": page_size}


@router.post(
    "/library/component-structure/nodes",
    status_code=status.HTTP_201_CREATED,
    summary="F-03: Add a single component structure node (pending approval)",
)
async def add_component_structure_node(
    body: dict[str, Any],
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, Any]:
    """Create a single node with status=pending_approval."""
    comp_name = body.get("component_name", "").strip()
    if not comp_name:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="component_name is required",
        )

    new_id = uuid.uuid4()
    await db.execute(
        text(
            "INSERT INTO component_structure_library "
            "(id, tenant_id, group1_code, group1_name, group2_code, group2_name, "
            "machinery_code, machinery_name, component_code, component_name, "
            "component_type, is_critical, version, status, is_deleted) "
            "VALUES (:id, :tid, :g1c, :g1n, :g2c, :g2n, :mc, :mn, :cc, :cn, "
            ":ct, :ic, 1, 'pending_approval', false)"
        ),
        {
            "id": str(new_id),
            "tid": str(current_user.tenant_id),
            "g1c": body.get("group1_code") or None,
            "g1n": body.get("group1_name") or None,
            "g2c": body.get("group2_code") or None,
            "g2n": body.get("group2_name") or None,
            "mc": body.get("machinery_code") or None,
            "mn": body.get("machinery_name") or None,
            "cc": body.get("component_code") or None,
            "cn": comp_name,
            "ct": body.get("component_type") or None,
            "ic": bool(body.get("is_critical", False)),
        },
    )
    await db.commit()
    return {"id": str(new_id), "status": "pending_approval"}


@router.get(
    "/library/component-structure/approval-requests",
    summary="F-03: List pending approval requests for component structure nodes",
)
async def list_approval_requests(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, Any]:
    """List all component_structure_library nodes with status=pending_approval."""
    result = await db.execute(
        text(
            "SELECT id, group1_code, group1_name, group2_code, group2_name, "
            "machinery_code, machinery_name, component_code, component_name, "
            "component_type, is_critical, status, created_at "
            "FROM component_structure_library "
            "WHERE tenant_id = :tid AND status = 'pending_approval' AND is_deleted = false "
            "ORDER BY created_at DESC"
        ),
        {"tid": str(current_user.tenant_id)},
    )
    rows = result.mappings().all()
    return {"items": [dict(r) for r in rows]}


@router.post(
    "/library/component-structure/approval-requests/{request_id}/approve",
    summary="F-03: Approve a component structure node",
)
async def approve_node(
    request_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, Any]:
    """Set a pending node's status to active."""
    check = await db.execute(
        text(
            "SELECT id FROM component_structure_library "
            "WHERE id = :id AND tenant_id = :tid AND is_deleted = false"
        ),
        {"id": str(request_id), "tid": str(current_user.tenant_id)},
    )
    if check.one_or_none() is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Node not found")

    await db.execute(
        text(
            "UPDATE component_structure_library "
            "SET status = 'active', updated_at = NOW() "
            "WHERE id = :id AND tenant_id = :tid"
        ),
        {"id": str(request_id), "tid": str(current_user.tenant_id)},
    )
    await db.commit()
    return {"id": str(request_id), "status": "active"}


@router.post(
    "/library/component-structure/approval-requests/{request_id}/reject",
    summary="F-03: Reject a component structure node",
)
async def reject_node(
    request_id: uuid.UUID,
    body: dict[str, Any],
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, Any]:
    """Set a pending node's status to rejected and store the rejection reason."""
    check = await db.execute(
        text(
            "SELECT id FROM component_structure_library "
            "WHERE id = :id AND tenant_id = :tid AND is_deleted = false"
        ),
        {"id": str(request_id), "tid": str(current_user.tenant_id)},
    )
    if check.one_or_none() is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Node not found")

    reason = body.get("reason", "")
    await db.execute(
        text(
            "UPDATE component_structure_library "
            "SET status = 'rejected', rejection_reason = :reason, updated_at = NOW() "
            "WHERE id = :id AND tenant_id = :tid"
        ),
        {"id": str(request_id), "tid": str(current_user.tenant_id), "reason": reason},
    )
    await db.commit()
    return {"id": str(request_id), "status": "rejected", "reason": reason}


# ===========================================================================
# F-04: Global Libraries
# ===========================================================================

_GLOBAL_TABLE_MAP = {
    "component": "global_component_library",
    "job": "global_job_library",
    "spare": "global_spare_library",
}


@router.get(
    "/library/global/{entity_type}",
    summary="F-04: List global library entries (component/job/spare)",
)
async def list_global_library(
    entity_type: str,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
) -> dict[str, Any]:
    """Return paginated records from the relevant global library table."""
    table = _GLOBAL_TABLE_MAP.get(entity_type)
    if not table:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid entity_type '{entity_type}'. Must be one of: component, job, spare.",
        )

    result = await db.execute(
        text(
            f"SELECT id, tenant_id, canonical_data, occurrence_count, "
            f"source_vessels, first_seen_at, created_at "
            f"FROM {table} "
            f"WHERE tenant_id = :tid AND is_deleted = false "
            f"ORDER BY occurrence_count DESC, first_seen_at DESC "
            f"LIMIT {page_size} OFFSET {(page - 1) * page_size}"
        ),
        {"tid": str(current_user.tenant_id)},
    )
    rows = result.mappings().all()
    return {
        "entity_type": entity_type,
        "items": [dict(r) for r in rows],
        "page": page,
        "page_size": page_size,
    }


@router.post(
    "/library/global/{entity_type}/populate",
    summary="F-04: Populate global library from accepted vessel records",
)
async def populate_global_library(
    entity_type: str,
    body: dict[str, Any],
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, Any]:
    """
    Find all accepted records for the given vessel, run dedup against the
    global library, and insert non-duplicates.
    """
    table = _GLOBAL_TABLE_MAP.get(entity_type)
    if not table:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid entity_type '{entity_type}'.",
        )

    vessel_id_str = body.get("vessel_id")
    if not vessel_id_str:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="vessel_id is required in request body",
        )
    try:
        vessel_id = uuid.UUID(vessel_id_str)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Invalid vessel_id UUID",
        )

    # ------------------------------------------------------------------
    # Load accepted entity records for the vessel
    # ------------------------------------------------------------------
    accepted_records: list[dict] = []
    if entity_type == "component":
        result = await db.execute(
            select(Component).where(
                Component.vessel_id == vessel_id,
                Component.tenant_id == current_user.tenant_id,
                Component.qc_status == CompQCStatus.accepted,
                Component.is_deleted == False,
            )
        )
        for c in result.scalars().all():
            accepted_records.append(
                {
                    "id": str(c.id),
                    "component_name": c.component_name,
                    "maker": c.maker or "",
                    "model": c.model or "",
                    "group1": c.group1,
                    "group2": c.group2,
                    "main_machinery": c.main_machinery,
                }
            )
    elif entity_type == "job":
        result = await db.execute(
            select(Job).where(
                Job.vessel_id == vessel_id,
                Job.tenant_id == current_user.tenant_id,
                Job.qc_status == CompQCStatus.accepted,
                Job.is_deleted == False,
            )
        )
        for j in result.scalars().all():
            accepted_records.append(
                {
                    "id": str(j.id),
                    "job_name": j.job_name,
                    "frequency": j.frequency,
                    "frequency_type": j.frequency_type.value if j.frequency_type else None,
                }
            )
    elif entity_type == "spare":
        result = await db.execute(
            select(Spare).where(
                Spare.vessel_id == vessel_id,
                Spare.tenant_id == current_user.tenant_id,
                Spare.qc_status == CompQCStatus.accepted,
                Spare.is_deleted == False,
            )
        )
        for s in result.scalars().all():
            accepted_records.append(
                {
                    "id": str(s.id),
                    "part_name": s.part_name,
                    "part_number": s.part_number or "",
                }
            )

    if not accepted_records:
        return {"added": 0, "duplicates": 0, "message": "No accepted records found for vessel."}

    # ------------------------------------------------------------------
    # Load existing global library entries for dedup comparison
    # ------------------------------------------------------------------
    existing_result = await db.execute(
        text(
            f"SELECT id, canonical_data, source_vessels, occurrence_count "
            f"FROM {table} "
            f"WHERE tenant_id = :tid AND is_deleted = false"
        ),
        {"tid": str(current_user.tenant_id)},
    )
    existing_rows = existing_result.mappings().all()
    existing_canonical: list[dict] = []
    for row in existing_rows:
        import json as _json
        raw_data = row["canonical_data"]
        if isinstance(raw_data, str):
            try:
                raw_data = _json.loads(raw_data)
            except Exception:
                raw_data = {}
        existing_canonical.append(
            {
                "id": str(row["id"]),
                "data": raw_data or {},
                "source_vessels": row["source_vessels"] or [],
                "occurrence_count": row["occurrence_count"] or 1,
            }
        )

    import json as _json
    added = 0
    duplicates = 0

    for record in accepted_records:
        is_dup = False
        for ex in existing_canonical:
            if entity_type == "component" and is_duplicate_component(record, ex["data"]):
                is_dup = True
                break
            elif entity_type == "job" and is_duplicate_job(record, ex["data"]):
                is_dup = True
                break
            elif entity_type == "spare" and is_duplicate_spare(record, ex["data"]):
                is_dup = True
                break

        if is_dup:
            duplicates += 1
        else:
            new_id = uuid.uuid4()
            canonical_json = _json.dumps(record)
            source_vessels_json = _json.dumps([vessel_id_str])
            await db.execute(
                text(
                    f"INSERT INTO {table} "
                    f"(id, tenant_id, canonical_data, occurrence_count, source_vessels, "
                    f"first_seen_at, is_deleted) "
                    f"VALUES (:id, :tid, :cd::jsonb, 1, :sv::jsonb, NOW(), false)"
                ),
                {
                    "id": str(new_id),
                    "tid": str(current_user.tenant_id),
                    "cd": canonical_json,
                    "sv": source_vessels_json,
                },
            )
            # Also add to local dedup list to prevent intra-batch duplicates
            existing_canonical.append(
                {
                    "id": str(new_id),
                    "data": record,
                    "source_vessels": [vessel_id_str],
                    "occurrence_count": 1,
                }
            )
            added += 1

    await db.commit()
    return {"added": added, "duplicates": duplicates}


# ===========================================================================
# F-08: Manual Matching
# ===========================================================================


@router.post(
    "/{vessel_id}/manuals/find-matches",
    summary="F-08: Find matching manuals in other vessel projects (same tenant)",
)
async def find_manual_matches(
    vessel_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, Any]:
    """
    For each manual in the vessel, search for matching manuals across other
    vessel projects in the same tenant using SHA-256 exact match first, then
    filename fuzzy similarity. Results are stored in manual_matches table.
    """
    await _get_vessel_or_404(vessel_id, db)

    # Load this vessel's manuals
    own_result = await db.execute(
        select(Manual).where(
            Manual.vessel_id == vessel_id,
            Manual.tenant_id == current_user.tenant_id,
            Manual.is_deleted == False,
        )
    )
    own_manuals = own_result.scalars().all()
    if not own_manuals:
        return {"matches": [], "total": 0}

    # Load all OTHER vessel manuals for the same tenant
    other_result = await db.execute(
        select(Manual).where(
            Manual.vessel_id != vessel_id,
            Manual.tenant_id == current_user.tenant_id,
            Manual.is_deleted == False,
        )
    )
    other_manuals = other_result.scalars().all()

    # Build a lookup for vessel names
    vessel_result = await db.execute(
        select(VesselProject).where(
            VesselProject.tenant_id == current_user.tenant_id,
            VesselProject.is_deleted == False,
        )
    )
    vessel_name_map: dict[str, str] = {
        str(v.id): v.vessel_name for v in vessel_result.scalars().all()
    }

    from difflib import SequenceMatcher

    def _filename_sim(a: str, b: str) -> float:
        # Strip extension and normalise
        a_stem = a.rsplit(".", 1)[0].lower().replace("_", " ").replace("-", " ")
        b_stem = b.rsplit(".", 1)[0].lower().replace("_", " ").replace("-", " ")
        return SequenceMatcher(None, a_stem, b_stem).ratio()

    matches_created: list[dict] = []

    for own in own_manuals:
        for other in other_manuals:
            # --- SHA-256 exact match ---
            if own.sha256_hash and other.sha256_hash and own.sha256_hash == other.sha256_hash:
                score = 1.0
                confidence = "exact"
            else:
                # --- filename fuzzy match ---
                score = _filename_sim(own.original_filename, other.original_filename)
                if score < 0.60:
                    continue
                confidence = "high" if score >= 0.85 else "medium" if score >= 0.70 else "low"

            match_id = uuid.uuid4()
            matched_vessel_name = vessel_name_map.get(str(other.vessel_id), "Unknown Vessel")

            # Upsert into manual_matches (ignore duplicates)
            try:
                await db.execute(
                    text(
                        "INSERT INTO manual_matches "
                        "(id, tenant_id, source_manual_id, matched_manual_id, "
                        "match_score, match_confidence, is_deleted) "
                        "VALUES (:id, :tid, :smid, :mmid, :score, :conf, false) "
                        "ON CONFLICT DO NOTHING"
                    ),
                    {
                        "id": str(match_id),
                        "tid": str(current_user.tenant_id),
                        "smid": str(own.id),
                        "mmid": str(other.id),
                        "score": round(score, 4),
                        "conf": confidence,
                    },
                )
            except Exception:
                pass  # Table may not exist yet; gracefully skip

            matches_created.append(
                {
                    "source_manual_id": str(own.id),
                    "source_manual_name": own.original_filename,
                    "matched_manual_id": str(other.id),
                    "matched_manual_name": other.original_filename,
                    "matched_vessel_id": str(other.vessel_id),
                    "matched_vessel_name": matched_vessel_name,
                    "match_score": round(score, 4),
                    "match_confidence": confidence,
                }
            )

    await db.commit()
    return {"matches": matches_created, "total": len(matches_created)}


@router.get(
    "/{vessel_id}/manuals/matches",
    summary="F-08: List stored manual matches for a vessel",
)
async def list_manual_matches(
    vessel_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
) -> dict[str, Any]:
    """Return stored matches for manuals belonging to this vessel."""
    await _get_vessel_or_404(vessel_id, db)

    try:
        result = await db.execute(
            text(
                "SELECT mm.id, mm.source_manual_id, mm.matched_manual_id, "
                "mm.match_score, mm.match_confidence, mm.created_at, "
                "sm.original_filename AS source_manual_name, "
                "tm.original_filename AS matched_manual_name, "
                "tm.vessel_id AS matched_vessel_id "
                "FROM manual_matches mm "
                "JOIN manuals sm ON sm.id = mm.source_manual_id "
                "JOIN manuals tm ON tm.id = mm.matched_manual_id "
                "WHERE sm.vessel_id = :vid "
                "  AND mm.tenant_id = :tid "
                "  AND mm.is_deleted = false "
                "ORDER BY mm.match_score DESC "
                f"LIMIT {page_size} OFFSET {(page - 1) * page_size}"
            ),
            {"vid": str(vessel_id), "tid": str(current_user.tenant_id)},
        )
        rows = result.mappings().all()
    except Exception:
        rows = []

    return {"items": [dict(r) for r in rows], "page": page, "page_size": page_size}


@router.post(
    "/{vessel_id}/manuals/matches/{match_id}/copy-all",
    summary="F-08: Copy all accepted records from matched vessel to current vessel",
)
async def copy_matched_vessel_records(
    vessel_id: uuid.UUID,
    match_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, Any]:
    """
    Copy all accepted Components, Jobs, and Spares from the source vessel
    referenced in the match into this vessel as pending QC records.
    """
    await _get_vessel_or_404(vessel_id, db)

    # Resolve the match to find the source vessel
    try:
        match_result = await db.execute(
            text(
                "SELECT mm.source_manual_id, mm.matched_manual_id, "
                "sm.vessel_id AS source_vessel_id "
                "FROM manual_matches mm "
                "JOIN manuals sm ON sm.id = mm.source_manual_id "
                "WHERE mm.id = :mid AND mm.tenant_id = :tid AND mm.is_deleted = false"
            ),
            {"mid": str(match_id), "tid": str(current_user.tenant_id)},
        )
        match_row = match_result.mappings().one_or_none()
    except Exception:
        match_row = None

    if match_row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Match not found")

    source_vessel_id = uuid.UUID(str(match_row["source_vessel_id"]))

    copied_components = 0
    copied_jobs = 0
    copied_spares = 0

    # --- Copy Components ---
    comp_result = await db.execute(
        select(Component).where(
            Component.vessel_id == source_vessel_id,
            Component.tenant_id == current_user.tenant_id,
            Component.qc_status == CompQCStatus.accepted,
            Component.is_deleted == False,
        )
    )
    for c in comp_result.scalars().all():
        new_comp = Component(
            tenant_id=current_user.tenant_id,
            vessel_id=vessel_id,
            group1=c.group1,
            group2=c.group2,
            main_machinery=c.main_machinery,
            component_name=c.component_name,
            maker=c.maker,
            model=c.model,
            serial_number=c.serial_number,
            specification=c.specification,
            is_critical=c.is_critical,
            job_pages=c.job_pages,
            spare_pages=c.spare_pages,
            confidence_score=c.confidence_score,
            qc_status=CompQCStatus.pending,
            source_manual_id=c.source_manual_id,
        )
        db.add(new_comp)
        copied_components += 1

    # --- Copy Jobs ---
    job_result = await db.execute(
        select(Job).where(
            Job.vessel_id == source_vessel_id,
            Job.tenant_id == current_user.tenant_id,
            Job.qc_status == CompQCStatus.accepted,
            Job.is_deleted == False,
        )
    )
    for j in job_result.scalars().all():
        new_job = Job(
            tenant_id=current_user.tenant_id,
            vessel_id=vessel_id,
            job_name=j.job_name,
            job_code=j.job_code,
            job_description=j.job_description,
            safety_precaution=j.safety_precaution,
            frequency=j.frequency,
            frequency_type=j.frequency_type,
            is_critical=j.is_critical,
            confidence_score=j.confidence_score,
            qc_status=CompQCStatus.pending,
            source_manual_id=j.source_manual_id,
        )
        db.add(new_job)
        copied_jobs += 1

    # --- Copy Spares ---
    spare_result = await db.execute(
        select(Spare).where(
            Spare.vessel_id == source_vessel_id,
            Spare.tenant_id == current_user.tenant_id,
            Spare.qc_status == CompQCStatus.accepted,
            Spare.is_deleted == False,
        )
    )
    for s in spare_result.scalars().all():
        new_spare = Spare(
            tenant_id=current_user.tenant_id,
            vessel_id=vessel_id,
            part_name=s.part_name,
            part_number=s.part_number,
            specification=s.specification,
            spare_maker=s.spare_maker,
            spare_model=s.spare_model,
            confidence_score=s.confidence_score,
            qc_status=CompQCStatus.pending,
            source_manual_id=s.source_manual_id,
        )
        db.add(new_spare)
        copied_spares += 1

    await db.commit()
    return {
        "copied_components": copied_components,
        "copied_jobs": copied_jobs,
        "copied_spares": copied_spares,
        "total": copied_components + copied_jobs + copied_spares,
    }
