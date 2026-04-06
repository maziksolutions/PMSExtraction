from __future__ import annotations

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import Response
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user
from app.models.component import Component, QCStatus
from app.models.export import ExportSchema, ExportVersion, ExportVersionStatus
from app.models.job import Job
from app.models.spare import Spare
from app.models.user import User, UserRole
from app.models.vessel import VesselProject
from app.schemas.export import ExportSchemaOut, ExportVersionOut
from app.services.exporter import export_service

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


async def _get_or_create_export_schema(
    vessel: VesselProject,
    current_user: User,
    db: AsyncSession,
) -> ExportSchema:
    if vessel.export_schema_id:
        vessel_schema_result = await db.execute(
            select(ExportSchema).where(
                ExportSchema.id == vessel.export_schema_id,
                ExportSchema.tenant_id == current_user.tenant_id,
                ExportSchema.is_deleted == False,
                ExportSchema.is_active == True,
            )
        )
        vessel_schema = vessel_schema_result.scalar_one_or_none()
        if vessel_schema is not None:
            return vessel_schema

    schema_result = await db.execute(
        select(ExportSchema)
        .where(
            ExportSchema.tenant_id == current_user.tenant_id,
            ExportSchema.is_deleted == False,
            ExportSchema.is_active == True,
        )
        .order_by(ExportSchema.created_at.desc())
        .limit(1)
    )
    export_schema = schema_result.scalar_one_or_none()
    if export_schema is not None:
        if vessel.export_schema_id != export_schema.id:
            vessel.export_schema_id = export_schema.id
            db.add(vessel)
            await db.commit()
            await db.refresh(vessel)
        return export_schema

    export_schema = ExportSchema(
        tenant_id=current_user.tenant_id,
        name="Default Export Schema",
        version=1,
        sheet_mappings=None,
        uploaded_by=current_user.id,
        is_active=True,
    )
    db.add(export_schema)
    await db.flush()

    vessel.export_schema_id = export_schema.id
    db.add(vessel)
    await db.commit()
    await db.refresh(export_schema)
    await db.refresh(vessel)
    return export_schema


@router.post("/export-schemas", response_model=ExportSchemaOut, status_code=status.HTTP_201_CREATED)
async def create_export_schema(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ExportSchemaOut:
    """Upload an Excel template and auto-detect sheet/column structure."""
    content = await file.read()
    parsed = export_service.parse_template(content, file.filename or "template.xlsx")

    schema = ExportSchema(
        tenant_id=current_user.tenant_id,
        name=file.filename or "Export Template",
        version=1,
        sheet_mappings=parsed.get("sheet_mappings"),
        uploaded_by=current_user.id,
    )
    db.add(schema)
    await db.commit()
    await db.refresh(schema)
    return ExportSchemaOut.model_validate(schema)


@router.put("/export-schemas/{schema_id}/mapping", response_model=ExportSchemaOut)
async def update_schema_mapping(
    schema_id: uuid.UUID,
    body: dict[str, Any],
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ExportSchemaOut:
    result = await db.execute(
        select(ExportSchema).where(
            ExportSchema.id == schema_id, ExportSchema.is_deleted == False
        )
    )
    schema = result.scalar_one_or_none()
    if schema is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Schema not found")

    schema.sheet_mappings = body.get("sheet_mappings", schema.sheet_mappings)
    db.add(schema)
    await db.commit()
    await db.refresh(schema)
    return ExportSchemaOut.model_validate(schema)


@router.get("/export-schemas")
async def list_export_schemas(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, Any]:
    result = await db.execute(
        select(ExportSchema).where(
            ExportSchema.tenant_id == current_user.tenant_id,
            ExportSchema.is_deleted == False,
            ExportSchema.is_active == True,
        )
    )
    schemas = result.scalars().all()
    return {"items": [ExportSchemaOut.model_validate(s) for s in schemas]}


@router.post("/vessels/{vessel_id}/exports", status_code=status.HTTP_201_CREATED)
async def trigger_export(
    vessel_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, Any]:
    """Generate an export for a vessel. Checks pre-export conditions."""
    vessel = await _get_vessel_or_404(vessel_id, db)
    export_schema = await _get_or_create_export_schema(vessel, current_user, db)

    # Pre-export check: count pending records
    pending_components = await db.scalar(
        select(func.count()).select_from(Component).where(
            Component.vessel_id == vessel_id,
            Component.qc_status == QCStatus.pending,
            Component.is_deleted == False,
        )
    ) or 0

    pending_jobs = await db.scalar(
        select(func.count()).select_from(Job).where(
            Job.vessel_id == vessel_id,
            Job.qc_status == QCStatus.pending,
            Job.is_deleted == False,
        )
    ) or 0

    pending_spares = await db.scalar(
        select(func.count()).select_from(Spare).where(
            Spare.vessel_id == vessel_id,
            Spare.qc_status == QCStatus.pending,
            Spare.is_deleted == False,
        )
    ) or 0

    total_pending = pending_components + pending_jobs + pending_spares
    if total_pending > 0 and current_user.role != UserRole.super_admin:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Cannot export: {total_pending} pending records require QC approval. "
                   "Use 'Override with Super Admin approval' to bypass.",
        )

    # Get next version number
    last_version = await db.scalar(
        select(func.max(ExportVersion.version_number)).where(
            ExportVersion.vessel_id == vessel_id, ExportVersion.is_deleted == False
        )
    ) or 0

    serialized = await export_service.serialize_async(
        db,
        vessel_id,
        export_schema.sheet_mappings if export_schema else None,
    )
    comp_count = len(serialized["components"])
    job_count = len(serialized["jobs"])
    spare_count = len(serialized["spares"])
    excluded_count = len(serialized["excluded"])

    blob_storage_key = (
        f"{current_user.tenant_id}/{vessel_id}/exports/v{last_version + 1}.xlsx"
    )
    export_version = ExportVersion(
        tenant_id=current_user.tenant_id,
        vessel_id=vessel_id,
        export_schema_id=export_schema.id,
        version_number=last_version + 1,
        blob_storage_key=blob_storage_key,
        generated_by=current_user.id,
        row_counts={
            "components": comp_count,
            "jobs": job_count,
            "spares": spare_count,
            "excluded": excluded_count,
        },
        status=ExportVersionStatus.ready,
    )
    db.add(export_version)
    await db.commit()
    await db.refresh(export_version)

    # Purge old versions (keep 10)
    old_versions = await db.execute(
        select(ExportVersion)
        .where(
            ExportVersion.vessel_id == vessel_id,
            ExportVersion.is_deleted == False,
        )
        .order_by(ExportVersion.version_number.desc())
        .offset(10)
    )
    for old in old_versions.scalars().all():
        old.is_deleted = True
        db.add(old)
    await db.commit()

    return ExportVersionOut.model_validate(export_version).model_dump()


@router.get("/vessels/{vessel_id}/exports")
async def list_exports(
    vessel_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, Any]:
    await _get_vessel_or_404(vessel_id, db)
    result = await db.execute(
        select(ExportVersion)
        .where(
            ExportVersion.vessel_id == vessel_id,
            ExportVersion.is_deleted == False,
        )
        .order_by(ExportVersion.version_number.desc())
        .limit(10)
    )
    versions = result.scalars().all()
    return {"items": [ExportVersionOut.model_validate(v) for v in versions]}


@router.get("/vessels/{vessel_id}/exports/{export_id}/download")
async def download_export(
    vessel_id: uuid.UUID,
    export_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Response:
    await _get_vessel_or_404(vessel_id, db)

    result = await db.execute(
        select(ExportVersion).where(
            ExportVersion.id == export_id,
            ExportVersion.vessel_id == vessel_id,
            ExportVersion.is_deleted == False,
        )
    )
    export_v = result.scalar_one_or_none()
    if export_v is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Export not found")

    schema = None
    if export_v.export_schema_id:
        schema_result = await db.execute(
            select(ExportSchema).where(
                ExportSchema.id == export_v.export_schema_id,
                ExportSchema.is_deleted == False,
            )
        )
        schema = schema_result.scalar_one_or_none()

    serialized = await export_service.serialize_async(
        db,
        vessel_id,
        schema.sheet_mappings if schema else None,
    )
    excel_bytes = export_service.to_excel(
        serialized,
        schema.sheet_mappings if schema else None,
    )

    filename = f"vessel_pms_export_v{export_v.version_number}.xlsx"
    return Response(
        content=excel_bytes,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.delete("/vessels/{vessel_id}/exports/{export_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response, response_model=None)
async def delete_export(
    vessel_id: uuid.UUID,
    export_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    result = await db.execute(
        select(ExportVersion).where(
            ExportVersion.id == export_id, ExportVersion.vessel_id == vessel_id
        )
    )
    ev = result.scalar_one_or_none()
    if ev:
        ev.is_deleted = True
        db.add(ev)
        await db.commit()
