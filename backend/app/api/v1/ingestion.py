from __future__ import annotations

import uuid
from typing import Annotated, Any

import asyncio
import os

import logging as _log_mod
from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, Query, UploadFile, status

logger = _log_mod.getLogger(__name__)
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

    if not folder_url:
        raise HTTPException(status_code=400, detail="No SharePoint folder URL provided.")

    try:
        sp_service = SharePointService()
        files = await sp_service.list_folder_contents(folder_url)
    except ValueError as exc:
        # Missing Azure credentials — surface a clear error
        raise HTTPException(
            status_code=503,
            detail=f"SharePoint not configured: {exc}. Ensure AZURE_TENANT_ID, AZURE_CLIENT_ID, and AZURE_CLIENT_SECRET are set in Railway environment variables.",
        )
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"SharePoint listing failed: {exc}",
        )

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

    # Create manuals and collect (manual_id, download_url) for task dispatch
    manual_tasks: list[tuple[str, str]] = []
    for file_info in body.selected_files:
        name = file_info.get("name", "unknown")
        # Prefer pre-signed download_url from listing; fall back to path
        download_url = file_info.get("download_url") or file_info.get("path", "")
        manual = Manual(
            tenant_id=current_user.tenant_id,
            vessel_id=vessel_id,
            original_filename=name,
            file_extension=name.rsplit(".", 1)[-1].lower() if "." in name else "pdf",
            file_size_bytes=file_info.get("size", 0),
            sharepoint_path=download_url,
            status=ManualStatus.queued,
            uploaded_by=current_user.id,
        )
        db.add(manual)
        await db.flush()
        manual_tasks.append((str(manual.id), download_url))

    await db.commit()
    await db.refresh(session)

    # Dispatch Celery tasks with correct manual_id and pre-signed download URL
    try:
        from app.tasks.ingestion import download_sharepoint_file
        for manual_id, download_url in manual_tasks:
            download_sharepoint_file.delay(manual_id, download_url, "")
    except Exception:
        pass  # Celery may not be available in dev

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


async def _process_uploaded_file(
    manual_id: str,
    vessel_id_str: str,
    tenant_id_str: str,
    file_bytes: bytes,
    file_ext: str,
    filename: str,
) -> None:
    """
    Background task: extract text from an uploaded file and classify it with Claude.
    Runs after the upload response has already been returned to the user.
    """
    import io as _io
    from app.core.database import AsyncSessionLocal
    from app.models.ingestion import Manual, ManualStatus
    from sqlalchemy import select as _select, update as _update

    async with AsyncSessionLocal() as db:
        # Extract text from PDF/DOCX
        extracted_text = ""
        page_count_val = 0

        if file_ext == "pdf":
            try:
                def _read_pdf(data: bytes) -> tuple[str, int]:
                    import pdfplumber as _pdfplumber
                    parts: list[str] = []
                    with _pdfplumber.open(_io.BytesIO(data)) as pdf:
                        total = len(pdf.pages)
                        for page_num, page in enumerate(pdf.pages, start=1):
                            text = page.extract_text()
                            if text and text.strip():
                                parts.append(text)
                            try:
                                for table in (page.extract_tables() or []):
                                    if not table:
                                        continue
                                    rows = [
                                        " | ".join(str(c).strip() if c else "" for c in row)
                                        for row in table if row and any(c for c in row if c)
                                    ]
                                    if rows:
                                        parts.append(f"[TABLE page {page_num}]\n" + "\n".join(rows))
                            except Exception:
                                pass
                    return "\n\n".join(parts), total

                extracted_text, page_count_val = await asyncio.to_thread(_read_pdf, file_bytes)
            except Exception as exc:
                logger.warning("_process_uploaded_file: PDF extraction failed for %s: %s", filename, exc)

        elif file_ext == "docx":
            try:
                def _read_docx(data: bytes) -> str:
                    import docx as _docx
                    doc = _docx.Document(_io.BytesIO(data))
                    return "\n".join(p.text for p in doc.paragraphs if p.text.strip())

                extracted_text = await asyncio.to_thread(_read_docx, file_bytes)
            except Exception as exc:
                logger.warning("_process_uploaded_file: DOCX extraction failed for %s: %s", filename, exc)

        # Classify with Claude (or keyword fallback)
        from app.services.classifier import classify_pdf, _keyword_classify, ClassificationResult
        try:
            if file_ext == "pdf":
                result = await asyncio.to_thread(classify_pdf, file_bytes, filename)
            else:
                result = await asyncio.to_thread(_keyword_classify, [], filename, 0)
        except Exception:
            result = ClassificationResult(
                category="Unknown/Unclassifiable",
                confidence=40,
                useful_for_extraction="no",
                pages_with_components="",
                pages_with_jobs="",
                pages_with_spares="",
                page_count=page_count_val,
            )

        # Update the manual record
        await db.execute(
            _update(Manual)
            .where(Manual.id == uuid.UUID(manual_id))
            .values(
                status=ManualStatus.classified,
                category=result.category,
                classification_confidence=result.confidence,
                useful_for_extraction=result.useful_for_extraction,
                pages_with_components=result.pages_with_components,
                pages_with_jobs=result.pages_with_jobs,
                pages_with_spares=result.pages_with_spares,
                page_count=page_count_val or result.page_count or None,
                extracted_text=extracted_text or None,
            )
        )
        await db.commit()
        logger.info("_process_uploaded_file: classified %s → %s (%d%%)", filename, result.category, result.confidence)


@router.post(
    "/{vessel_id}/ingestion/upload",
    status_code=status.HTTP_201_CREATED,
    summary="Directly upload PDF manuals for a vessel",
)
async def upload_manuals(
    vessel_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    background_tasks: BackgroundTasks,
    files: list[UploadFile] = File(...),
) -> dict[str, Any]:
    """
    Upload one or more files directly.
    Files are saved to blob storage immediately and returned to the user.
    PDF text extraction + AI classification run in the background so the
    upload response is instant regardless of file size.
    """
    import hashlib as _hashlib
    import io as _io
    from app.services.blob_storage import BlobStorageService as _BlobSvc

    await _get_vessel_or_404(vessel_id, db)

    ALLOWED_EXTENSIONS = {"pdf", "docx", "doc", "xlsx", "xls"}
    MAX_SIZE = 50 * 1024 * 1024  # 50 MB per file

    mime_map_upload = {
        "pdf": "application/pdf",
        "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "doc": "application/msword",
        "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "xls": "application/vnd.ms-excel",
    }

    created_manuals = []
    pending_bg: list[tuple[str, str, str, bytes]] = []  # (manual_id, blob_key, ext, content)

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

        # Duplicate check via SHA-256
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

        # Save record immediately with status=queued; classification runs in background
        manual = Manual(
            tenant_id=current_user.tenant_id,
            vessel_id=vessel_id,
            original_filename=filename,
            file_extension=ext,
            file_size_bytes=len(content),
            sharepoint_path="",
            status=ManualStatus.queued,
            uploaded_by=current_user.id,
            sha256_hash=sha256,
            is_duplicate=is_dup,
            duplicate_of_id=original_manual.id if is_dup else None,
            category=None,
            classification_confidence=None,
        )
        db.add(manual)
        await db.flush()

        # Upload raw bytes to blob storage
        blob_key = f"{current_user.tenant_id}/{vessel_id}/{manual.id}/{filename}"
        content_type_upload = mime_map_upload.get(ext, "application/octet-stream")
        try:
            _blob = _BlobSvc()
            await _blob.upload_stream(blob_key, _io.BytesIO(content), content_type_upload)
            manual.blob_storage_key = blob_key
            db.add(manual)
        except Exception:
            # Blob storage unavailable — fall back to local disk
            try:
                upload_dir = os.path.join(settings.UPLOAD_DIR, str(vessel_id))
                os.makedirs(upload_dir, exist_ok=True)
                file_path = os.path.join(upload_dir, f"{manual.id}.{ext}")
                with open(file_path, "wb") as f:
                    f.write(content)
                manual.blob_storage_key = file_path
                db.add(manual)
            except Exception:
                pass

        created_manuals.append(ManualOut.model_validate(manual))
        pending_bg.append((str(manual.id), str(vessel_id), str(current_user.tenant_id), content, ext, filename))

    await db.commit()

    # Kick off background processing for each file (text extraction + classification)
    for manual_id, vid, tid, content, ext, filename in pending_bg:
        background_tasks.add_task(
            _process_uploaded_file,
            manual_id=manual_id,
            vessel_id_str=vid,
            tenant_id_str=tid,
            file_bytes=content,
            file_ext=ext,
            filename=filename,
        )

    return {"uploaded": len(created_manuals), "manuals": [m.model_dump() for m in created_manuals]}


# ---------------------------------------------------------------------------
# Screening: classify unclassified manuals for a vessel
# ---------------------------------------------------------------------------

async def _run_screening_task(vessel_id_str: str, tenant_id_str: str, manual_ids: list[str]) -> None:
    """Background task: re-classifies the given manuals using Claude (if PDF on disk) or keywords."""
    from app.core.database import AsyncSessionLocal
    from app.services.classifier import classify_pdf, _keyword_classify

    try:
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(Manual).where(
                    Manual.id.in_([uuid.UUID(mid) for mid in manual_ids]),
                    Manual.is_deleted == False,
                )
            )
            manuals = result.scalars().all()
            _screening_state[vessel_id_str]["total"] = len(manuals)
            _screening_state[vessel_id_str]["done"] = 0

            for manual in manuals:
                try:
                    # Use Claude classification when the file is on disk; otherwise keyword fallback
                    file_path = manual.blob_storage_key
                    if file_path and os.path.exists(file_path):
                        with open(file_path, "rb") as f:
                            content = f.read()
                        cr = await asyncio.to_thread(classify_pdf, content, manual.original_filename)
                    else:
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
    summary="Screen (classify) all manuals for a vessel using Claude AI",
)
async def screen_all_manuals(
    vessel_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, Any]:
    """Re-classifies ALL manuals for the vessel using Claude AI (or keyword fallback)."""
    await _get_vessel_or_404(vessel_id, db)

    vessel_id_str = str(vessel_id)

    result = await db.execute(
        select(Manual).where(
            Manual.vessel_id == vessel_id,
            Manual.tenant_id == current_user.tenant_id,
            Manual.is_deleted == False,
        )
    )
    all_manuals = result.scalars().all()
    total = len(all_manuals)

    if total == 0:
        return {"started": False, "message": "No manuals found for this vessel.", "total": 0}

    manual_ids = [str(m.id) for m in all_manuals]
    _screening_state[vessel_id_str] = {
        "total": total,
        "done": 0,
        "status": "running",
    }
    background_tasks.add_task(
        _run_screening_task, vessel_id_str, str(current_user.tenant_id), manual_ids
    )
    return {"started": True, "total": total, "message": f"Screening {total} manuals with Claude AI."}


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
    summary="Stream a manual file for inline viewing",
)
async def view_manual(
    vessel_id: uuid.UUID,
    manual_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Stream the manual file bytes directly. Works with both local disk and blob storage."""
    import logging as _logging
    from fastapi.responses import Response
    from app.services.blob_storage import BlobStorageService

    _log = _logging.getLogger(__name__)

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

    blob_key = manual.blob_storage_key
    if not blob_key:
        raise HTTPException(status_code=404, detail="File not available. Please re-upload.")

    mime_map = {
        "pdf": "application/pdf",
        "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "doc": "application/msword",
        "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "xls": "application/vnd.ms-excel",
        "png": "image/png",
        "jpg": "image/jpeg",
        "jpeg": "image/jpeg",
        "tiff": "image/tiff",
    }
    ext = (manual.file_extension or "").lower().lstrip(".")
    media_type = mime_map.get(ext, "application/octet-stream")

    # Local file path (starts with / on Linux or drive letter on Windows)
    is_local_path = blob_key.startswith("/") or (len(blob_key) > 1 and blob_key[1] == ":")

    if is_local_path:
        if not os.path.exists(blob_key):
            raise HTTPException(
                status_code=404,
                detail="File was stored on an ephemeral disk that no longer exists. Please re-upload.",
            )
        with open(blob_key, "rb") as fh:
            file_bytes = fh.read()
        return Response(
            content=file_bytes,
            media_type=media_type,
            headers={"Content-Disposition": f'inline; filename="{manual.original_filename}"'},
        )

    # Blob storage key — download bytes then stream to browser
    try:
        blob_service = BlobStorageService()
        file_bytes = await blob_service.download_bytes(blob_key)
        return Response(
            content=file_bytes,
            media_type=media_type,
            headers={"Content-Disposition": f'inline; filename="{manual.original_filename}"'},
        )
    except Exception as exc:
        _log.error("view_manual: blob download failed for key=%s: %s", blob_key, exc)
        raise HTTPException(status_code=502, detail=f"Could not retrieve file from storage: {exc}")


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
