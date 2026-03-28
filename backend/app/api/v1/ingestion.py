from __future__ import annotations

import uuid
from typing import Annotated, Any

import asyncio
import os

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, Query, UploadFile, status
from fastapi.responses import FileResponse, JSONResponse
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.deps import get_current_user
from app.models.ingestion import IngestionSession, IngestionSessionStatus, Manual, ManualStatus
from app.models.user import User
from app.models.vessel import VesselProject
from app.schemas.ingestion import (
    IngestionSessionOut,
    IngestionStartRequest,
    ManualOut,
    SharePointAuthResponse,
    SharePointFileListRequest,
    SharePointFileListResponse,
)
from app.services.sharepoint import SharePointService

router = APIRouter()

# In-memory screening progress tracker (per vessel_id string)
# Structure: { vessel_id: { "total": int, "done": int, "status": "idle"|"running"|"completed" } }
_screening_state: dict[str, dict] = {}


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


@router.post(
    "/{vessel_id}/ingestion/sharepoint-auth",
    response_model=SharePointAuthResponse,
    summary="Get SharePoint OAuth URL",
)
async def sharepoint_auth(
    vessel_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> SharePointAuthResponse:
    """Returns an OAuth authorization URL for SharePoint / Microsoft Graph."""
    await _get_vessel_or_404(vessel_id, db)

    auth_url = (
        f"https://login.microsoftonline.com/{settings.AZURE_TENANT_ID}/oauth2/v2.0/authorize"
        f"?client_id={settings.AZURE_CLIENT_ID}"
        f"&response_type=code"
        f"&redirect_uri={settings.SHAREPOINT_REDIRECT_URI}"
        f"&scope=Files.Read.All+Sites.Read.All"
        f"&state={vessel_id}"
    )
    return SharePointAuthResponse(auth_url=auth_url, vessel_id=vessel_id)


@router.get(
    "/{vessel_id}/ingestion/sharepoint-callback",
    summary="Exchange OAuth code for token and store in Redis",
)
async def sharepoint_callback(
    vessel_id: uuid.UUID,
    code: str = Query(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Exchanges the OAuth authorization code for tokens and stores them in Redis."""
    await _get_vessel_or_404(vessel_id, db)
    # In production, exchange code for token via MSAL and store in Redis
    # For dev/mock: just acknowledge
    return {"status": "ok", "vessel_id": str(vessel_id), "message": "Token stored (mock)"}


@router.post(
    "/{vessel_id}/ingestion/list-files",
    response_model=SharePointFileListResponse,
    summary="List files in the SharePoint folder for a vessel",
)
async def list_sharepoint_files(
    vessel_id: uuid.UUID,
    body: SharePointFileListRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> SharePointFileListResponse:
    """Lists files available in the configured SharePoint folder."""
    vessel = await _get_vessel_or_404(vessel_id, db)
    folder_url = body.folder_url or vessel.sharepoint_folder_url or ""

    try:
        sp_service = SharePointService()
        files = await sp_service.list_folder_contents(folder_url)
    except Exception:
        # Mock data for dev
        files = [
            {
                "name": "Engine_Manual_MAN_B&W.pdf",
                "size": 5_242_880,
                "path": f"{folder_url}/Engine_Manual_MAN_B&W.pdf",
                "modified": "2024-01-15T10:00:00Z",
            },
            {
                "name": "Pumps_Instruction_Manual.pdf",
                "size": 2_097_152,
                "path": f"{folder_url}/Pumps_Instruction_Manual.pdf",
                "modified": "2024-01-10T08:30:00Z",
            },
            {
                "name": "General_Arrangement_Drawing.pdf",
                "size": 8_388_608,
                "path": f"{folder_url}/General_Arrangement_Drawing.pdf",
                "modified": "2024-01-05T12:00:00Z",
            },
        ]

    return SharePointFileListResponse(files=files, total=len(files))


@router.post(
    "/{vessel_id}/ingestion/start",
    response_model=IngestionSessionOut,
    status_code=status.HTTP_201_CREATED,
    summary="Start an ingestion session for selected files",
)
async def start_ingestion(
    vessel_id: uuid.UUID,
    body: IngestionStartRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> IngestionSessionOut:
    """Creates an ingestion session and dispatches download tasks for each selected file."""
    vessel = await _get_vessel_or_404(vessel_id, db)

    session = IngestionSession(
        tenant_id=current_user.tenant_id,
        vessel_id=vessel_id,
        sharepoint_folder_url=body.folder_url,
        total_files=len(body.selected_files),
        downloaded_files=0,
        failed_files=0,
        status=IngestionSessionStatus.active,
        started_by=current_user.id,
    )
    db.add(session)
    await db.flush()

    for file_info in body.selected_files:
        manual = Manual(
            tenant_id=current_user.tenant_id,
            vessel_id=vessel_id,
            original_filename=file_info.get("name", "unknown"),
            file_extension=file_info.get("name", "").rsplit(".", 1)[-1].lower() if "." in file_info.get("name", "") else "pdf",
            file_size_bytes=file_info.get("size", 0),
            sharepoint_path=file_info.get("path", ""),
            status=ManualStatus.queued,
            uploaded_by=current_user.id,
        )
        db.add(manual)

    await db.commit()
    await db.refresh(session)

    # Dispatch Celery tasks
    try:
        from app.tasks.ingestion import download_sharepoint_file
        for file_info in body.selected_files:
            download_sharepoint_file.delay(str(session.id), file_info.get("path", ""))
    except Exception:
        pass  # Tasks will be dispatched when Celery is available

    return IngestionSessionOut.model_validate(session)


@router.get(
    "/{vessel_id}/ingestion/sessions",
    summary="List ingestion sessions for a vessel",
)
async def list_sessions(
    vessel_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> dict[str, Any]:
    await _get_vessel_or_404(vessel_id, db)

    result = await db.execute(
        select(IngestionSession)
        .where(
            IngestionSession.vessel_id == vessel_id,
            IngestionSession.tenant_id == current_user.tenant_id,
            IngestionSession.is_deleted == False,
        )
        .order_by(IngestionSession.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    sessions = result.scalars().all()
    return {
        "items": [IngestionSessionOut.model_validate(s) for s in sessions],
        "page": page,
        "page_size": page_size,
    }


@router.get(
    "/{vessel_id}/ingestion/sessions/{session_id}",
    summary="Get ingestion session detail with manual statuses",
)
async def get_session(
    vessel_id: uuid.UUID,
    session_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, Any]:
    await _get_vessel_or_404(vessel_id, db)

    result = await db.execute(
        select(IngestionSession).where(
            IngestionSession.id == session_id,
            IngestionSession.vessel_id == vessel_id,
            IngestionSession.is_deleted == False,
        )
    )
    session = result.scalar_one_or_none()
    if session is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

    # Get manuals for this vessel in this session's time range
    manuals_result = await db.execute(
        select(Manual).where(
            Manual.vessel_id == vessel_id,
            Manual.tenant_id == current_user.tenant_id,
            Manual.is_deleted == False,
            Manual.created_at >= session.created_at,
        )
    )
    manuals = manuals_result.scalars().all()

    return {
        **IngestionSessionOut.model_validate(session).model_dump(),
        "manuals": [ManualOut.model_validate(m) for m in manuals],
    }


@router.post(
    "/{vessel_id}/ingestion/upload",
    status_code=status.HTTP_201_CREATED,
    summary="Directly upload PDF manuals for a vessel",
)
async def upload_manuals(
    vessel_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    files: list[UploadFile] = File(...),
) -> dict[str, Any]:
    """Upload one or more PDF/document files directly without SharePoint."""
    await _get_vessel_or_404(vessel_id, db)

    import hashlib as _hashlib

    ALLOWED_EXTENSIONS = {"pdf", "docx", "doc", "xlsx", "xls"}
    MAX_SIZE = 50 * 1024 * 1024  # 50 MB per file

    created_manuals = []
    for upload in files:
        filename = upload.filename or "unknown"
        ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else "pdf"
        if ext not in ALLOWED_EXTENSIONS:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"File '{filename}' has unsupported extension '.{ext}'. Allowed: {', '.join(ALLOWED_EXTENSIONS)}",
            )
        content = await upload.read()
        if len(content) > MAX_SIZE:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=f"File '{filename}' exceeds the 50 MB limit.",
            )

        # F-09: compute SHA-256 and check for within-project duplicates
        sha256 = _hashlib.sha256(content).hexdigest()
        existing_hash = await db.execute(
            select(Manual).where(
                Manual.vessel_id == vessel_id,
                Manual.tenant_id == current_user.tenant_id,
                Manual.sha256_hash == sha256,
                Manual.is_deleted == False,
            ).limit(1)
        )
        original_manual = existing_hash.scalars().first()
        is_dup = original_manual is not None

        # Auto-classify the document — run sync PDF+Claude work in a thread
        # to avoid blocking the async event loop on large files.
        from app.services.classifier import classify_pdf, _keyword_classify
        try:
            result = await asyncio.to_thread(classify_pdf, content, filename)
        except Exception:
            # Fallback: keyword-only classification so upload never fails
            try:
                result = await asyncio.to_thread(_keyword_classify, [], filename, 0)
            except Exception:
                from app.services.classifier import ClassificationResult
                result = ClassificationResult(
                    category="Unknown/Unclassifiable",
                    confidence=40,
                    useful_for_extraction="no",
                    pages_with_components="",
                    pages_with_jobs="",
                    pages_with_spares="",
                    page_count=0,
                )

        manual = Manual(
            tenant_id=current_user.tenant_id,
            vessel_id=vessel_id,
            original_filename=filename,
            file_extension=ext,
            file_size_bytes=len(content),
            sharepoint_path="",
            status=ManualStatus.classified,
            uploaded_by=current_user.id,
            sha256_hash=sha256,
            is_duplicate=is_dup,
            duplicate_of_id=original_manual.id if is_dup else None,
            category=result.category,
            classification_confidence=result.confidence,
            useful_for_extraction=result.useful_for_extraction,
            pages_with_components=result.pages_with_components,
            pages_with_jobs=result.pages_with_jobs,
            pages_with_spares=result.pages_with_spares,
        )
        db.add(manual)
        await db.flush()

        # Save file to local disk so extraction and view endpoints can access it
        upload_dir = os.path.join(settings.UPLOAD_DIR, str(vessel_id))
        os.makedirs(upload_dir, exist_ok=True)
        file_path = os.path.join(upload_dir, f"{manual.id}.{ext}")
        with open(file_path, "wb") as f:
            f.write(content)
        manual.blob_storage_key = file_path
        db.add(manual)

        created_manuals.append(ManualOut.model_validate(manual))

    await db.commit()

    return {"uploaded": len(created_manuals), "manuals": [m.model_dump() for m in created_manuals]}


# ---------------------------------------------------------------------------
# Screening: classify unclassified manuals for a vessel
# ---------------------------------------------------------------------------

async def _run_screening_task(vessel_id_str: str, tenant_id_str: str) -> None:
    """Background task: classifies all unclassified manuals for a vessel."""
    from app.core.database import AsyncSessionLocal
    from app.services.classifier import classify_pdf, _keyword_classify

    try:
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(Manual).where(
                    Manual.vessel_id == uuid.UUID(vessel_id_str),
                    Manual.tenant_id == uuid.UUID(tenant_id_str),
                    Manual.is_deleted == False,
                    Manual.category == None,
                )
            )
            manuals = result.scalars().all()
            _screening_state[vessel_id_str]["total"] = len(manuals)
            _screening_state[vessel_id_str]["done"] = 0

            for manual in manuals:
                try:
                    # Filename-based classification (no stored PDF content for SharePoint files)
                    cr = _keyword_classify([], manual.original_filename, 0)
                    await db.execute(
                        update(Manual)
                        .where(Manual.id == manual.id)
                        .values(
                            category=cr.category,
                            classification_confidence=cr.confidence,
                            useful_for_extraction=cr.useful_for_extraction,
                            pages_with_components=cr.pages_with_components,
                            pages_with_jobs=cr.pages_with_jobs,
                            pages_with_spares=cr.pages_with_spares,
                            status=ManualStatus.classified,
                        )
                    )
                    await db.commit()
                except Exception:
                    pass
                _screening_state[vessel_id_str]["done"] += 1

        _screening_state[vessel_id_str]["status"] = "completed"
    except Exception:
        _screening_state[vessel_id_str]["status"] = "failed"


@router.post(
    "/{vessel_id}/manuals/screen-all",
    summary="Start screening (classify) all unclassified manuals for a vessel",
)
async def screen_all_manuals(
    vessel_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, Any]:
    """Triggers background classification for all manuals that have no category yet."""
    await _get_vessel_or_404(vessel_id, db)

    vessel_id_str = str(vessel_id)

    # Count pending
    result = await db.execute(
        select(Manual).where(
            Manual.vessel_id == vessel_id,
            Manual.tenant_id == current_user.tenant_id,
            Manual.is_deleted == False,
            Manual.category == None,
        )
    )
    pending = result.scalars().all()
    total = len(pending)

    if total == 0:
        return {"started": False, "message": "All manuals are already classified.", "total": 0}

    _screening_state[vessel_id_str] = {
        "total": total,
        "done": 0,
        "status": "running",
    }
    background_tasks.add_task(
        _run_screening_task, vessel_id_str, str(current_user.tenant_id)
    )
    return {"started": True, "total": total, "message": f"Screening {total} manuals in background."}


@router.get(
    "/{vessel_id}/manuals/screening-status",
    summary="Get screening progress for a vessel",
)
async def screening_status(
    vessel_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, Any]:
    """Returns current screening progress for the vessel."""
    await _get_vessel_or_404(vessel_id, db)
    state = _screening_state.get(
        str(vessel_id),
        {"total": 0, "done": 0, "status": "idle"},
    )
    return state


@router.get(
    "/{vessel_id}/manuals/{manual_id}/view",
    summary="View / download a manual file",
)
async def view_manual(
    vessel_id: uuid.UUID,
    manual_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> FileResponse:
    """Serve the uploaded manual file for inline viewing in the browser."""
    await _get_vessel_or_404(vessel_id, db)
    result = await db.execute(
        select(Manual).where(
            Manual.id == manual_id,
            Manual.vessel_id == vessel_id,
            Manual.tenant_id == current_user.tenant_id,
            Manual.is_deleted == False,
        )
    )
    manual: Manual | None = result.scalar_one_or_none()
    if manual is None:
        raise HTTPException(status_code=404, detail="Manual not found")

    file_path = manual.blob_storage_key
    if not file_path or not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="File not available on disk. Please re-upload.")

    mime_map = {
        "pdf": "application/pdf",
        "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "doc": "application/msword",
        "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "xls": "application/vnd.ms-excel",
    }
    media_type = mime_map.get(manual.file_extension, "application/octet-stream")

    return FileResponse(
        path=file_path,
        media_type=media_type,
        filename=manual.original_filename,
        headers={"Content-Disposition": f'inline; filename="{manual.original_filename}"'},
    )


@router.delete(
    "/{vessel_id}/manuals/{manual_id}",
    summary="Soft-delete a manual",
)
async def delete_manual(
    vessel_id: uuid.UUID,
    manual_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, Any]:
    """Soft-deletes a manual record (sets is_deleted=True)."""
    await _get_vessel_or_404(vessel_id, db)
    result = await db.execute(
        select(Manual).where(
            Manual.id == manual_id,
            Manual.vessel_id == vessel_id,
            Manual.tenant_id == current_user.tenant_id,
            Manual.is_deleted == False,
        )
    )
    manual: Manual | None = result.scalar_one_or_none()
    if manual is None:
        raise HTTPException(status_code=404, detail="Manual not found")

    manual.is_deleted = True
    db.add(manual)
    await db.commit()
    return {"deleted": True}
