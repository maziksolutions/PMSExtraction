from __future__ import annotations

import uuid
from typing import Annotated, Any, List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user
from app.models.component import QCStatus
from app.models.feedback import CorrectionType, FeedbackEntry
from app.models.spare import ExtractionMethod, Spare
from app.models.user import User
from app.models.vessel import VesselProject
from app.schemas.spare import SpareCreate, SpareOut, SpareUpdate

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


async def _rerun_manual_extraction(manual_ids: list[str]) -> None:
    from app.services.extractor import auto_extract_from_manual

    for manual_id in manual_ids:
        try:
            await auto_extract_from_manual(manual_id)
        except Exception:
            continue


@router.get("/{vessel_id}/spares", summary="List spares with filters")
async def list_spares(
    vessel_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    component_id: Optional[uuid.UUID] = Query(None),
    extraction_method: Optional[str] = Query(None),
    qc_status: Optional[str] = Query(None),
    is_critical: Optional[bool] = Query(None),
    search: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(100, ge=1, le=1000),
) -> dict[str, Any]:
    from sqlalchemy import func as _func, or_
    from app.models.component import Component
    from app.models.ingestion import Manual
    await _get_vessel_or_404(vessel_id, db)
    base_where = [
        Spare.vessel_id == vessel_id,
        Spare.tenant_id == current_user.tenant_id,
        Spare.is_deleted == False,
    ]
    if component_id:
        base_where.append(Spare.component_id == component_id)
    if extraction_method:
        try:
            base_where.append(Spare.extraction_method == ExtractionMethod(extraction_method))
        except ValueError:
            pass
    if qc_status:
        try:
            base_where.append(Spare.qc_status == QCStatus(qc_status))
        except ValueError:
            pass
    if is_critical is not None:
        base_where.append(Spare.is_critical == is_critical)
    if search:
        base_where.append(
            or_(
                Spare.part_name.ilike(f"%{search}%"),
                Spare.part_number.ilike(f"%{search}%"),
                Spare.spare_maker.ilike(f"%{search}%"),
            )
        )

    total_result = await db.execute(select(_func.count()).select_from(Spare).where(*base_where))
    total: int = total_result.scalar_one()

    query = select(Spare).where(*base_where).order_by(Spare.part_name).offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(query)
    spares = result.scalars().all()

    component_ids = {spare.component_id for spare in spares if spare.component_id}
    manual_ids = {spare.source_manual_id for spare in spares if spare.source_manual_id}

    component_lookup: dict[uuid.UUID, Component] = {}
    manual_lookup: dict[uuid.UUID, Manual] = {}

    if component_ids:
        component_result = await db.execute(select(Component).where(Component.id.in_(component_ids)))
        component_lookup = {component.id: component for component in component_result.scalars().all()}
    if manual_ids:
        manual_result = await db.execute(select(Manual).where(Manual.id.in_(manual_ids)))
        manual_lookup = {manual.id: manual for manual in manual_result.scalars().all()}

    items = []
    for spare in spares:
        payload = SpareOut.model_validate(spare).model_dump()
        component = component_lookup.get(spare.component_id) if spare.component_id else None
        manual = manual_lookup.get(spare.source_manual_id) if spare.source_manual_id else None
        payload.update(
            {
                "component_name": component.component_name if component else None,
                "component_maker": component.maker if component else None,
                "component_model": component.model if component else None,
                "source_manual_name": manual.original_filename if manual else None,
                "pdf_reference": manual.original_filename if manual else None,
            }
        )
        items.append(payload)

    return {"items": items, "page": page, "page_size": page_size, "total": total}


@router.post(
    "/{vessel_id}/spares",
    response_model=SpareOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_spare(
    vessel_id: uuid.UUID,
    body: SpareCreate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> SpareOut:
    await _get_vessel_or_404(vessel_id, db)
    spare = Spare(
        tenant_id=current_user.tenant_id,
        vessel_id=vessel_id,
        **body.model_dump(),
    )
    db.add(spare)
    await db.commit()
    await db.refresh(spare)
    return SpareOut.model_validate(spare)


@router.patch("/{vessel_id}/spares/{spare_id}", response_model=SpareOut)
async def update_spare(
    vessel_id: uuid.UUID,
    spare_id: uuid.UUID,
    body: SpareUpdate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> SpareOut:
    await _get_vessel_or_404(vessel_id, db)
    result = await db.execute(
        select(Spare).where(
            Spare.id == spare_id, Spare.vessel_id == vessel_id, Spare.is_deleted == False
        )
    )
    spare = result.scalar_one_or_none()
    if spare is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Spare not found")

    original = {"part_name": spare.part_name, "qc_status": spare.qc_status.value}
    update_data = body.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(spare, field, value)
    db.add(spare)

    if spare.source_manual_id and update_data:
        feedback = FeedbackEntry(
            tenant_id=current_user.tenant_id,
            manual_id=spare.source_manual_id,
            entity_type="spare",
            original_value=original,
            corrected_value=update_data,
            correction_type=CorrectionType.wrong_value,
            created_by=current_user.id,
        )
        db.add(feedback)

    await db.commit()
    await db.refresh(spare)
    return SpareOut.model_validate(spare)


@router.delete("/{vessel_id}/spares/{spare_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response, response_model=None)
async def delete_spare(
    vessel_id: uuid.UUID,
    spare_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    result = await db.execute(
        select(Spare).where(Spare.id == spare_id, Spare.vessel_id == vessel_id)
    )
    spare = result.scalar_one_or_none()
    if spare:
        spare.is_deleted = True
        db.add(spare)
        await db.commit()


@router.post("/{vessel_id}/spares/bulk-accept")
async def bulk_accept_spares(
    vessel_id: uuid.UUID,
    body: dict[str, List[str]],
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, Any]:
    ids = [uuid.UUID(i) for i in body.get("ids", [])]
    result = await db.execute(select(Spare).where(Spare.id.in_(ids), Spare.vessel_id == vessel_id))
    spares = result.scalars().all()
    for spare in spares:
        spare.qc_status = QCStatus.accepted
        db.add(spare)
    await db.commit()
    return {"accepted": len(spares)}


@router.post("/{vessel_id}/spares/bulk-reject")
async def bulk_reject_spares(
    vessel_id: uuid.UUID,
    body: dict[str, List[str]],
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, Any]:
    ids = [uuid.UUID(i) for i in body.get("ids", [])]
    result = await db.execute(select(Spare).where(Spare.id.in_(ids), Spare.vessel_id == vessel_id))
    spares = result.scalars().all()
    for spare in spares:
        spare.qc_status = QCStatus.rejected
        db.add(spare)
    await db.commit()
    return {"rejected": len(spares)}


@router.post("/{vessel_id}/spares/{spare_id}/merge")
async def merge_spare(
    vessel_id: uuid.UUID,
    spare_id: uuid.UUID,
    body: dict[str, str],
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> SpareOut:
    result = await db.execute(
        select(Spare).where(
            Spare.id == spare_id, Spare.vessel_id == vessel_id, Spare.is_deleted == False
        )
    )
    spare = result.scalar_one_or_none()
    if spare is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Spare not found")

    target_id = uuid.UUID(body["target_spare_id"])
    spare.merged_into_id = target_id
    spare.is_duplicate = True
    spare.is_deleted = True
    db.add(spare)
    await db.commit()
    await db.refresh(spare)
    return SpareOut.model_validate(spare)


@router.post("/{vessel_id}/spares/{spare_id}/reassign-component")
async def reassign_component(
    vessel_id: uuid.UUID,
    spare_id: uuid.UUID,
    body: dict[str, str],
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> SpareOut:
    result = await db.execute(
        select(Spare).where(
            Spare.id == spare_id, Spare.vessel_id == vessel_id, Spare.is_deleted == False
        )
    )
    spare = result.scalar_one_or_none()
    if spare is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Spare not found")

    spare.component_id = uuid.UUID(body["component_id"])
    db.add(spare)
    await db.commit()
    await db.refresh(spare)
    return SpareOut.model_validate(spare)


@router.post("/{vessel_id}/spares/trigger-extraction")
async def trigger_spare_extraction(
    vessel_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, Any]:
    await _get_vessel_or_404(vessel_id, db)
    from app.models.ingestion import Manual

    result = await db.execute(
        select(Manual).where(
            Manual.vessel_id == vessel_id,
            Manual.tenant_id == current_user.tenant_id,
            Manual.is_deleted == False,
            Manual.pages_with_spares.isnot(None),
            Manual.pages_with_spares != "",
        )
    )
    manuals = result.scalars().all()
    manual_ids = [str(manual.id) for manual in manuals]
    if not manual_ids:
        return {"started": False, "total": 0, "message": "No manuals with spare page references found."}

    background_tasks.add_task(_rerun_manual_extraction, manual_ids)
    return {"started": True, "total": len(manual_ids), "message": "Spare extraction started."}


@router.get("/{vessel_id}/spares/{spare_id}/page-image")
async def get_spare_page_image(
    vessel_id: uuid.UUID,
    spare_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, Any]:
    result = await db.execute(
        select(Spare).where(
            Spare.id == spare_id, Spare.vessel_id == vessel_id, Spare.is_deleted == False
        )
    )
    spare = result.scalar_one_or_none()
    if spare is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Spare not found")

    if spare.source_manual_id and spare.page_reference:
        blob_key = f"page-images/{spare.source_manual_id}/page_{spare.page_reference}.png"
        try:
            from app.services.blob_storage import BlobStorageService

            blob_svc = BlobStorageService()
            url = blob_svc.get_presigned_url(blob_key)
            return {"image_url": url}
        except Exception:
            pass

    return {"image_url": None, "message": "Page image not available"}
