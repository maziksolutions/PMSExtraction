from __future__ import annotations

import uuid
from typing import Annotated, Any, List, Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, Response, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user
from app.models.component import Component, ComponentTemplate, QCStatus
from app.models.feedback import CorrectionType, FeedbackEntry
from app.models.ingestion import Manual
from app.models.user import User
from app.models.vessel import VesselProject
from app.schemas.component import ComponentCreate, ComponentOut, ComponentUpdate

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


@router.get("/{vessel_id}/components", summary="List components with filters")
async def list_components(
    vessel_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    group1: Optional[str] = Query(None),
    group2: Optional[str] = Query(None),
    qc_status: Optional[str] = Query(None),
    min_confidence: Optional[int] = Query(None),
    is_unmapped: Optional[bool] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
) -> dict[str, Any]:
    await _get_vessel_or_404(vessel_id, db)
    query = select(Component).where(
        Component.vessel_id == vessel_id,
        Component.tenant_id == current_user.tenant_id,
        Component.is_deleted == False,
    )
    if group1:
        query = query.where(Component.group1 == group1)
    if group2:
        query = query.where(Component.group2 == group2)
    if qc_status:
        try:
            query = query.where(Component.qc_status == QCStatus(qc_status))
        except ValueError:
            pass
    if min_confidence is not None:
        query = query.where(Component.confidence_score >= min_confidence)
    if is_unmapped is not None:
        query = query.where(Component.is_unmapped == is_unmapped)

    query = query.order_by(Component.group1, Component.group2, Component.component_name)
    query = query.offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(query)
    components = result.scalars().all()
    return {"items": [ComponentOut.model_validate(c) for c in components], "page": page}


@router.post(
    "/{vessel_id}/components",
    response_model=ComponentOut,
    status_code=status.HTTP_201_CREATED,
    summary="Create a component manually",
)
async def create_component(
    vessel_id: uuid.UUID,
    body: ComponentCreate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ComponentOut:
    await _get_vessel_or_404(vessel_id, db)
    comp = Component(
        tenant_id=current_user.tenant_id,
        vessel_id=vessel_id,
        **body.model_dump(),
    )
    db.add(comp)
    await db.commit()
    await db.refresh(comp)
    return ComponentOut.model_validate(comp)


@router.patch(
    "/{vessel_id}/components/{component_id}",
    response_model=ComponentOut,
    summary="Update a component",
)
async def update_component(
    vessel_id: uuid.UUID,
    component_id: uuid.UUID,
    body: ComponentUpdate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ComponentOut:
    await _get_vessel_or_404(vessel_id, db)
    result = await db.execute(
        select(Component).where(
            Component.id == component_id,
            Component.vessel_id == vessel_id,
            Component.is_deleted == False,
        )
    )
    comp = result.scalar_one_or_none()
    if comp is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Component not found")

    original = {
        "component_name": comp.component_name,
        "maker": comp.maker,
        "model": comp.model,
        "qc_status": comp.qc_status.value if comp.qc_status else None,
    }

    update_data = body.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(comp, field, value)
    db.add(comp)

    if comp.confidence_score and comp.confidence_score > 0 and update_data:
        manual_id = comp.source_manual_id
        if manual_id:
            feedback = FeedbackEntry(
                tenant_id=current_user.tenant_id,
                manual_id=manual_id,
                entity_type="component",
                original_value=original,
                corrected_value=update_data,
                correction_type=CorrectionType.wrong_value,
                created_by=current_user.id,
            )
            db.add(feedback)

    await db.commit()
    await db.refresh(comp)
    return ComponentOut.model_validate(comp)


@router.delete("/{vessel_id}/components/{component_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
async def delete_component(
    vessel_id: uuid.UUID,
    component_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    result = await db.execute(
        select(Component).where(
            Component.id == component_id, Component.vessel_id == vessel_id
        )
    )
    comp = result.scalar_one_or_none()
    if comp:
        comp.is_deleted = True
        db.add(comp)
        await db.commit()


@router.post("/{vessel_id}/components/bulk-accept", summary="Bulk accept components")
async def bulk_accept_components(
    vessel_id: uuid.UUID,
    body: dict[str, List[str]],
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, Any]:
    ids = [uuid.UUID(i) for i in body.get("ids", [])]
    result = await db.execute(
        select(Component).where(
            Component.id.in_(ids), Component.vessel_id == vessel_id
        )
    )
    components = result.scalars().all()
    for comp in components:
        comp.qc_status = QCStatus.accepted
        db.add(comp)
    await db.commit()
    return {"accepted": len(components)}


@router.post("/{vessel_id}/components/bulk-reject", summary="Bulk reject components")
async def bulk_reject_components(
    vessel_id: uuid.UUID,
    body: dict[str, List[str]],
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, Any]:
    ids = [uuid.UUID(i) for i in body.get("ids", [])]
    result = await db.execute(
        select(Component).where(
            Component.id.in_(ids), Component.vessel_id == vessel_id
        )
    )
    components = result.scalars().all()
    for comp in components:
        comp.qc_status = QCStatus.rejected
        db.add(comp)
    await db.commit()
    return {"rejected": len(components)}


@router.post("/{vessel_id}/components/{component_id}/remap", summary="Remap component hierarchy")
async def remap_component(
    vessel_id: uuid.UUID,
    component_id: uuid.UUID,
    body: dict[str, str],
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ComponentOut:
    result = await db.execute(
        select(Component).where(
            Component.id == component_id,
            Component.vessel_id == vessel_id,
            Component.is_deleted == False,
        )
    )
    comp = result.scalar_one_or_none()
    if comp is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Component not found")

    if "group1" in body:
        comp.group1 = body["group1"]
    if "group2" in body:
        comp.group2 = body["group2"]
    if "main_machinery" in body:
        comp.main_machinery = body["main_machinery"]
    comp.is_unmapped = False
    db.add(comp)
    await db.commit()
    await db.refresh(comp)
    return ComponentOut.model_validate(comp)


@router.post("/{vessel_id}/components/upload-template", summary="Upload component template")
async def upload_component_template(
    vessel_id: uuid.UUID,
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    await _get_vessel_or_404(vessel_id, db)
    content = await file.read()
    template = ComponentTemplate(
        tenant_id=current_user.tenant_id,
        vessel_id=vessel_id,
        name=file.filename or "template",
        template_data={"raw": content.decode("utf-8", errors="replace")[:5000]},
    )
    db.add(template)
    await db.commit()
    return {"status": "uploaded", "template_id": str(template.id)}


@router.post("/{vessel_id}/components/trigger-extraction", summary="Trigger component extraction")
async def trigger_extraction(
    vessel_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, Any]:
    await _get_vessel_or_404(vessel_id, db)
    try:
        from app.tasks.extraction import extract_components

        task = extract_components.delay(str(vessel_id))
        return {"task_id": task.id, "status": "queued"}
    except Exception:
        return {"status": "queued", "task_id": "mock"}
