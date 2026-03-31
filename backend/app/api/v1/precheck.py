from __future__ import annotations

import uuid
from difflib import SequenceMatcher
from typing import Annotated, Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user
from app.models.ingestion import Manual
from app.models.user import User
from app.models.vessel import VesselProject

router = APIRouter()

# ---------------------------------------------------------------------------
# Standard major machinery list per vessel type
# Each entry is: (machinery_name, [keywords_for_matching])
# Keywords are matched against Instruction Manual filenames and component pages.
# ---------------------------------------------------------------------------

_COMMON_MACHINERY: list[tuple[str, list[str]]] = [
    ("Main Engine",                  ["main", "engine", "me", "propulsion", "diesel"]),
    ("Auxiliary Engine / Generator", ["auxiliary", "generator", "genset", "aux", "diesel", "alternator"]),
    ("Main Air Compressor",          ["air", "compressor", "starting", "main", "compress"]),
    ("Fuel Oil Purifier",            ["fuel", "oil", "purifier", "separator", "fo", "centrifuge"]),
    ("Lube Oil Purifier",            ["lube", "lubricating", "oil", "purifier", "lo", "centrifuge"]),
    ("Steering Gear",                ["steering", "gear", "rudder", "helm"]),
    ("Oily Water Separator",         ["oily", "water", "separator", "ows", "bilge"]),
    ("Sewage Treatment Plant",       ["sewage", "treatment", "plant", "stp", "biological"]),
    ("Incinerator",                  ["incinerator", "incinerate", "waste"]),
    ("Fresh Water Generator",        ["fresh", "water", "generator", "fwg", "evaporator", "distiller"]),
    ("Boiler / Exhaust Gas Economizer", ["boiler", "exhaust", "economizer", "steam", "ege"]),
    ("Bilge Pump",                   ["bilge", "pump"]),
    ("Fire Pump",                    ["fire", "pump", "firefighting"]),
    ("Emergency Fire Pump",          ["emergency", "fire", "pump", "efp"]),
    ("Lifeboat Engine",              ["lifeboat", "rescue", "boat", "engine"]),
    ("Air Conditioning / Refrigeration", ["air", "conditioning", "refrigeration", "hvac", "ac", "fridge"]),
    ("Windlass",                     ["windlass", "anchor", "mooring"]),
    ("Mooring Winch",                ["mooring", "winch", "capstan"]),
    ("Main Engine Turbocharger",     ["turbocharger", "turbocharg", "tc", "blower"]),
    ("Ballast Water Treatment System", ["ballast", "water", "treatment", "bwts", "bwt"]),
]

_VESSEL_EXTRA_MACHINERY: dict[str, list[tuple[str, list[str]]]] = {
    "Bulk Carrier": [
        ("Cargo Hatch Cover",    ["hatch", "cover", "cargo", "hold"]),
        ("Cargo Crane",          ["crane", "derrick", "cargo", "gear"]),
        ("Ballast Pump",         ["ballast", "pump"]),
    ],
    "Tanker": [
        ("Cargo Pump",           ["cargo", "pump", "transfer"]),
        ("Inert Gas System",     ["inert", "gas", "igs", "ig"]),
        ("Ballast Pump",         ["ballast", "pump"]),
        ("Vapour Emission Control System", ["vapour", "vapor", "vecs", "emission"]),
    ],
    "Chemical Tanker": [
        ("Cargo Pump",           ["cargo", "pump", "transfer"]),
        ("Inert Gas System",     ["inert", "gas", "igs"]),
        ("Ballast Pump",         ["ballast", "pump"]),
        ("Cargo Heating System", ["cargo", "heating", "coil", "heat"]),
    ],
    "Container Ship": [
        ("Reefer Monitoring System", ["reefer", "refrigerated", "container", "monitoring"]),
        ("Cargo Crane",          ["crane", "cargo", "gear"]),
        ("Ballast Pump",         ["ballast", "pump"]),
    ],
    "General Cargo": [
        ("Cargo Crane / Derrick", ["crane", "derrick", "cargo", "gear"]),
        ("Hatch Cover",          ["hatch", "cover"]),
        ("Ballast Pump",         ["ballast", "pump"]),
    ],
    "LNG Carrier": [
        ("Cargo Compressor",     ["cargo", "compressor", "gas", "lng"]),
        ("Cargo Pump",           ["cargo", "pump", "submersible"]),
        ("Gas Detection System", ["gas", "detection", "detector"]),
        ("Reliquefaction Plant", ["reliquefaction", "reliq", "nitrogen"]),
        ("Ballast Pump",         ["ballast", "pump"]),
    ],
    "LPG Carrier": [
        ("Cargo Compressor",     ["cargo", "compressor", "lpg"]),
        ("Cargo Pump",           ["cargo", "pump"]),
        ("Gas Detection System", ["gas", "detection", "detector"]),
        ("Ballast Pump",         ["ballast", "pump"]),
    ],
    "Passenger Ship": [
        ("Bow Thruster",         ["bow", "thruster", "tunnel"]),
        ("Stabilizer",           ["stabilizer", "fin", "anti-roll"]),
        ("Stern Thruster",       ["stern", "thruster"]),
    ],
    "Ro-Ro": [
        ("Car Ramp / Ramp Door", ["ramp", "door", "visor"]),
        ("Bow Thruster",         ["bow", "thruster"]),
        ("Cargo Ventilation",    ["cargo", "ventilation", "fan"]),
    ],
}


def _standard_machinery_for_vessel(vessel_type: str) -> list[tuple[str, list[str]]]:
    """Return the full machinery list (common + vessel-type-specific)."""
    extra = _VESSEL_EXTRA_MACHINERY.get(vessel_type, [])
    return _COMMON_MACHINERY + extra


# ---------------------------------------------------------------------------
# Matching helpers
# ---------------------------------------------------------------------------


def _filename_keywords(filename: str) -> list[str]:
    import re
    stem = filename.rsplit(".", 1)[0] if "." in filename else filename
    tokens = re.split(r"[_\-\.\s]+", stem)
    return [t.lower() for t in tokens if len(t) >= 2]


def _keyword_overlap_score(need_kws: list[str], manual_tokens: list[str]) -> float:
    if not need_kws:
        return 0.0
    hits = sum(1 for kw in need_kws if any(kw in tok for tok in manual_tokens))
    return hits / len(need_kws)


def _fuzzy_score(a: str, b: str) -> float:
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()


def _compute_match_score(need_kws: list[str], manual: Manual) -> int:
    """
    Score how well an Instruction Manual covers a required machinery item.
    Checks filename tokens and original_filename fuzzy match.
    """
    manual_tokens = _filename_keywords(manual.original_filename)
    overlap = _keyword_overlap_score(need_kws, manual_tokens)
    seq_sim = _fuzzy_score(" ".join(need_kws), " ".join(manual_tokens))
    raw = 0.65 * overlap + 0.35 * seq_sim
    return min(100, int(round(raw * 100)))


def _precheck_status(score: int) -> str:
    if score >= 75:
        return "found"
    elif score >= 55:
        return "low_confidence"
    else:
        return "missing"


# ---------------------------------------------------------------------------
# Helper
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


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.post(
    "/{vessel_id}/precheck/run",
    summary="F-10: Run instruction manual pre-check against standard major machinery list",
)
async def run_precheck(
    vessel_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, Any]:
    """
    Check whether Instruction Manuals exist for all standard major machinery
    required on this vessel type.  Upserts results into instruction_manual_precheck.
    """
    vessel = await _get_vessel_or_404(vessel_id, db)
    vessel_type: str = getattr(vessel, "vessel_type", "") or ""

    # Build required machinery list for this vessel type
    required = _standard_machinery_for_vessel(vessel_type)

    # Load all Instruction Manuals for the vessel
    im_result = await db.execute(
        select(Manual).where(
            Manual.vessel_id == vessel_id,
            Manual.tenant_id == current_user.tenant_id,
            Manual.category == "Instruction Manual",
            Manual.is_deleted == False,
        )
    )
    instruction_manuals = im_result.scalars().all()

    precheck_items: list[dict] = []

    for machinery_name, need_kws in required:
        best_score = 0
        best_manual: Optional[Manual] = None

        for im in instruction_manuals:
            score = _compute_match_score(need_kws, im)
            if score > best_score:
                best_score = score
                best_manual = im

        item_status = _precheck_status(best_score)
        matched_manual_id = str(best_manual.id) if best_manual else None
        new_id = uuid.uuid4()

        try:
            existing = await db.execute(
                text(
                    "SELECT id FROM instruction_manual_precheck "
                    "WHERE vessel_id = :vid AND tenant_id = :tid "
                    "  AND machinery_name = :mn AND is_deleted = false "
                    "LIMIT 1"
                ),
                {"vid": str(vessel_id), "tid": str(current_user.tenant_id), "mn": machinery_name},
            )
            existing_row = existing.mappings().one_or_none()

            if existing_row:
                await db.execute(
                    text(
                        "UPDATE instruction_manual_precheck "
                        "SET status = :st, match_score = :score, "
                        "matched_manual_id = :mmid, updated_at = NOW() "
                        "WHERE id = :id"
                    ),
                    {
                        "st": item_status,
                        "score": best_score,
                        "mmid": matched_manual_id,
                        "id": str(existing_row["id"]),
                    },
                )
                row_id = str(existing_row["id"])
            else:
                await db.execute(
                    text(
                        "INSERT INTO instruction_manual_precheck "
                        "(id, tenant_id, vessel_id, machinery_name, "
                        "machinery_maker, machinery_model, status, "
                        "matched_manual_id, match_score, is_deleted) "
                        "VALUES (:id, :tid, :vid, :mn, :mm, :mo, :st, :mmid, :score, false)"
                    ),
                    {
                        "id": str(new_id),
                        "tid": str(current_user.tenant_id),
                        "vid": str(vessel_id),
                        "mn": machinery_name,
                        "mm": None,
                        "mo": None,
                        "st": item_status,
                        "mmid": matched_manual_id,
                        "score": best_score,
                    },
                )
                row_id = str(new_id)

        except Exception:
            row_id = str(new_id)

        precheck_items.append(
            {
                "id": row_id,
                "vessel_id": str(vessel_id),
                "machinery_name": machinery_name,
                "status": item_status,
                "match_score": best_score,
                "matched_manual_id": matched_manual_id,
                "matched_manual": best_manual.original_filename if best_manual else None,
                "user_acknowledgement": None,
            }
        )

    try:
        await db.commit()
    except Exception:
        pass

    missing = sum(1 for i in precheck_items if i["status"] == "missing")
    found = sum(1 for i in precheck_items if i["status"] == "found")
    return {
        "status": "completed",
        "vessel_type": vessel_type,
        "total": len(precheck_items),
        "found": found,
        "missing": missing,
        "items": precheck_items,
        "run_at": __import__("datetime").datetime.utcnow().isoformat(),
    }


@router.get(
    "/{vessel_id}/precheck",
    summary="F-10: List all pre-check items for a vessel",
)
async def list_precheck(
    vessel_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    precheck_status: Optional[str] = Query(None, alias="status"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
) -> dict[str, Any]:
    """Return stored instruction_manual_precheck items for the vessel."""
    await _get_vessel_or_404(vessel_id, db)

    where_extra = "AND status = :st " if precheck_status else ""
    try:
        result = await db.execute(
            text(
                "SELECT id, tenant_id, vessel_id, machinery_name, machinery_maker, "
                "machinery_model, status, matched_manual_id, match_score, "
                "user_acknowledgement, acknowledgement_reason, acknowledged_by, "
                "created_at, updated_at "
                "FROM instruction_manual_precheck "
                f"WHERE vessel_id = :vid AND tenant_id = :tid "
                f"  AND is_deleted = false {where_extra}"
                "ORDER BY status, machinery_name "
                f"LIMIT {page_size} OFFSET {(page - 1) * page_size}"
            ),
            {
                "vid": str(vessel_id),
                "tid": str(current_user.tenant_id),
                "st": precheck_status,
            },
        )
        rows = result.mappings().all()
        items = [dict(r) for r in rows]
    except Exception:
        items = []

    return {
        "items": items,
        "page": page,
        "page_size": page_size,
        "run_at": items[0]["updated_at"].isoformat() if items and items[0].get("updated_at") else None,
    }


@router.patch(
    "/{vessel_id}/precheck/{item_id}",
    summary="F-10: Acknowledge a pre-check item",
)
async def acknowledge_precheck_item(
    vessel_id: uuid.UUID,
    item_id: uuid.UUID,
    body: dict[str, Any],
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, Any]:
    """Record the user's acknowledgement for a pre-check item."""
    await _get_vessel_or_404(vessel_id, db)

    valid_acks = {"upload_pending", "genuinely_absent", "not_applicable", "confirmed"}
    ack = body.get("user_acknowledgement", "")
    if ack not in valid_acks:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid user_acknowledgement '{ack}'. Must be one of: {sorted(valid_acks)}",
        )

    reason = body.get("acknowledgement_reason", "")

    try:
        check = await db.execute(
            text(
                "SELECT id FROM instruction_manual_precheck "
                "WHERE id = :id AND vessel_id = :vid AND tenant_id = :tid AND is_deleted = false"
            ),
            {"id": str(item_id), "vid": str(vessel_id), "tid": str(current_user.tenant_id)},
        )
        if check.one_or_none() is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pre-check item not found")

        await db.execute(
            text(
                "UPDATE instruction_manual_precheck "
                "SET user_acknowledgement = :ack, acknowledgement_reason = :reason, "
                "    acknowledged_by = :uid, updated_at = NOW() "
                "WHERE id = :id AND tenant_id = :tid"
            ),
            {"ack": ack, "reason": reason, "uid": str(current_user.id),
             "id": str(item_id), "tid": str(current_user.tenant_id)},
        )
        await db.commit()

        row_result = await db.execute(
            text(
                "SELECT id, vessel_id, machinery_name, status, match_score, "
                "matched_manual_id, user_acknowledgement, acknowledgement_reason, "
                "acknowledged_by, updated_at "
                "FROM instruction_manual_precheck WHERE id = :id"
            ),
            {"id": str(item_id)},
        )
        return dict(row_result.mappings().one())

    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Could not update pre-check item: {exc}",
        )
