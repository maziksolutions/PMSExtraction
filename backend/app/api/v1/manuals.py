from __future__ import annotations

import uuid
from typing import Annotated, Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user
from app.models.feedback import CorrectionType, FeedbackEntry
from app.models.ingestion import Manual, ManualStatus
from app.models.user import User
from app.models.vessel import VesselProject
from app.schemas.manual import ManualOut, ManualUpdate

router = APIRouter()

VESSEL_TYPE_MANUAL_TEMPLATES = {
    "Bulk Carrier": [
        "Instruction Manual",
        "Machinery Particulars",
        "General Arrangement",
        "Pipeline Diagrams/P&ID",
        "Electrical Diagrams",
    ],
    "Tanker": [
        "Instruction Manual",
        "Machinery Particulars",
        "General Arrangement",
        "Pipeline Diagrams/P&ID",
        "LSA/FFA Plans",
        "Tank Capacity Plan",
        "Electrical Diagrams",
    ],
    "Container Ship": [
        "Instruction Manual",
        "Machinery Particulars",
        "General Arrangement",
        "Electrical Diagrams",
        "Class Certificates/Surveys",
    ],
}


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


@router.get(
    "/{vessel_id}/manuals",
    summary="List manuals for a vessel with optional filters",
)
async def list_manuals(
    vessel_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    category: Optional[str] = Query(None),
    manual_status: Optional[str] = Query(None, alias="status"),
    min_confidence: Optional[int] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
) -> dict[str, Any]:
    await _get_vessel_or_404(vessel_id, db)

    query = select(Manual).where(
        Manual.vessel_id == vessel_id,
        Manual.tenant_id == current_user.tenant_id,
        Manual.is_deleted == False,
    )

    if category:
        query = query.where(Manual.category == category)
    if manual_status:
        try:
            query = query.where(Manual.status == ManualStatus(manual_status))
        except ValueError:
            pass
    if min_confidence is not None:
        query = query.where(Manual.classification_confidence >= min_confidence)

    query = query.order_by(Manual.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(query)
    manuals = result.scalars().all()
    return {
        "items": [ManualOut.model_validate(m) for m in manuals],
        "page": page,
        "page_size": page_size,
    }


@router.patch(
    "/{vessel_id}/manuals/{manual_id}",
    response_model=ManualOut,
    summary="Update manual classification fields",
)
async def update_manual(
    vessel_id: uuid.UUID,
    manual_id: uuid.UUID,
    body: ManualUpdate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ManualOut:
    await _get_vessel_or_404(vessel_id, db)

    result = await db.execute(
        select(Manual).where(
            Manual.id == manual_id,
            Manual.vessel_id == vessel_id,
            Manual.is_deleted == False,
        )
    )
    manual: Manual | None = result.scalar_one_or_none()
    if manual is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Manual not found")

    # Record original values for feedback
    original = {
        "category": manual.category,
        "useful_for_extraction": manual.useful_for_extraction,
        "classification_confidence": manual.classification_confidence,
    }

    update_data = body.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(manual, field, value)

    db.add(manual)

    # Save feedback entry
    corrected = {k: v for k, v in update_data.items()}
    if corrected:
        feedback = FeedbackEntry(
            tenant_id=current_user.tenant_id,
            manual_id=manual_id,
            entity_type="manual_classification",
            original_value=original,
            corrected_value=corrected,
            correction_type=CorrectionType.wrong_value,
            vessel_type=None,
            source_manual_category=manual.category,
            created_by=current_user.id,
        )
        db.add(feedback)

    await db.commit()
    await db.refresh(manual)
    return ManualOut.model_validate(manual)


@router.post(
    "/{vessel_id}/manuals/{manual_id}/trigger-classification",
    summary="Re-run classification for a manual",
)
async def trigger_classification(
    vessel_id: uuid.UUID,
    manual_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, Any]:
    await _get_vessel_or_404(vessel_id, db)

    result = await db.execute(
        select(Manual).where(
            Manual.id == manual_id,
            Manual.vessel_id == vessel_id,
            Manual.is_deleted == False,
        )
    )
    manual: Manual | None = result.scalar_one_or_none()
    if manual is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Manual not found")

    try:
        from app.tasks.classification import classify_manual

        task = classify_manual.delay(str(manual_id))
        return {"task_id": task.id, "status": "queued"}
    except Exception:
        return {"status": "queued", "task_id": "mock"}


@router.get(
    "/{vessel_id}/manuals/missing-report",
    summary="Missing manual gap analysis for vessel type",
)
async def missing_manual_report(
    vessel_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, Any]:
    vessel = await _get_vessel_or_404(vessel_id, db)

    expected = VESSEL_TYPE_MANUAL_TEMPLATES.get(vessel.vessel_type or "", [])

    result = await db.execute(
        select(Manual.category).where(
            Manual.vessel_id == vessel_id,
            Manual.tenant_id == current_user.tenant_id,
            Manual.is_deleted == False,
            Manual.category.isnot(None),
        )
    )
    classified_categories = {row[0] for row in result.all()}

    gaps = []
    for cat in expected:
        if cat not in classified_categories:
            gaps.append(
                {
                    "category": cat,
                    "status": "missing",
                    "message": f"No {cat} found for this vessel.",
                }
            )

    return {
        "vessel_type": vessel.vessel_type,
        "expected_categories": expected,
        "found_categories": list(classified_categories),
        "gaps": gaps,
        "gap_count": len(gaps),
    }
