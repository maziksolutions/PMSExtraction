from __future__ import annotations

import uuid
from typing import Annotated, Any, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
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


@router.get("/{vessel_id}/spares", summary="List spares with filters")
async def list_spares(
    vessel_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    component_id: Optional[uuid.UUID] = Query(None),
    extraction_method: Optional[str] = Query(None),
    qc_status: Optional[str] = Query(None),
    is_critical: Optional[bool] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
) -> dict[str, Any]:
    await _get_vessel_or_404(vessel_id, db)
    query = select(Spare).where(
        Spare.vessel_id == vessel_id,
        Spare.tenant_id == current_user.tenant_id,
        Spare.is_deleted == False,
    )
    if component_id:
        query = query.where(Spare.component_id == component_id)
    if extraction_method:
        try:
            query = query.where(Spare.extraction_method == ExtractionMethod(extraction_method))
        except ValueError:
            pass
    if qc_status:
        try:
            query = query.where(Spare.qc_status == QCStatus(qc_status))
        except ValueError:
            pass
    if is_critical is not None:
        query = query.where(Spare.is_critical == is_critical)

    query = query.order_by(Spare.part_name).offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(query)
    spares = result.scalars().all()
    return {"items": [SpareOut.model_validate(s) for s in spares], "page": page}


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


@router.delete("/{vessel_id}/spares/{spare_id}", status_code=status.HTTP_204_NO_CONTENT)
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
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, Any]:
    await _get_vessel_or_404(vessel_id, db)
    try:
        from app.tasks.extraction import extract_spares_table

        task = extract_spares_table.delay(str(vessel_id))
        return {"task_id": task.id, "status": "queued"}
    except Exception:
        return {"status": "queued", "task_id": "mock"}


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
