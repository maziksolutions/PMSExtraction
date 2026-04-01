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
                            page_parts: list[str] = []
                            text = page.extract_text()
                            if text and text.strip():
                                page_parts.append(text)
                            try:
                                for table in (page.extract_tables() or []):
                                    if not table:
                                        continue
                                    rows = [
                                        " | ".join(str(c).strip() if c else "" for c in row)
                                        for row in table if row and any(c for c in row if c)
                                    ]
                                    if rows:
                                        page_parts.append("[TABLE]\n" + "\n".join(rows))
                            except Exception:
                                pass

                            # Ensure every physical page gets a marker even when no text is extracted.
                            # This prevents page numbering and mapping from dropping unmarked pages.
                            if page_parts:
                                parts.append(f"[PAGE {page_num}]\n" + "\n".join(page_parts))
                            else:
                                parts.append(f"[PAGE {page_num}]\n")
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
                supply_type=getattr(result, "supply_type", "OEM"),
                page_count=page_count_val or result.page_count or None,
                extracted_text=extracted_text or None,
            )
        )
        await db.commit()
        logger.info("_process_uploaded_file: classified %s → %s (%d%%) supply=%s", filename, result.category, result.confidence, getattr(result, "supply_type", "OEM"))


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

    # Phase 1: read all files, create DB records
    created_manuals = []
    pending_bg: list[tuple[str, str, str, bytes, str, str]] = []  # (manual_id, vid, tid, content, ext, filename)
    blob_upload_tasks: list[tuple] = []  # (manual_id, blob_key, content, content_type, ext, vessel_id_str)

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

        blob_key = f"{current_user.tenant_id}/{vessel_id}/{manual.id}/{filename}"
        content_type_upload = mime_map_upload.get(ext, "application/octet-stream")
        blob_upload_tasks.append((str(manual.id), blob_key, content, content_type_upload, ext, str(vessel_id)))

        created_manuals.append((manual, ManualOut.model_validate(manual)))
        pending_bg.append((str(manual.id), str(vessel_id), str(current_user.tenant_id), content, ext, filename))

    await db.commit()

    # Phase 2: upload blobs in parallel
    async def _upload_one(manual_id: str, blob_key: str, content: bytes, content_type: str, ext: str, vid: str):
        try:
            _blob = _BlobSvc()
            await _blob.upload_stream(blob_key, _io.BytesIO(content), content_type)
            await db.execute(
                update(Manual).where(Manual.id == uuid.UUID(manual_id)).values(blob_storage_key=blob_key)
            )
            await db.commit()
        except Exception:
            # Blob storage unavailable — fall back to local disk
            try:
                upload_dir = os.path.join(settings.UPLOAD_DIR, vid)
                os.makedirs(upload_dir, exist_ok=True)
                file_path = os.path.join(upload_dir, f"{manual_id}.{ext}")
                with open(file_path, "wb") as fh:
                    fh.write(content)
                await db.execute(
                    update(Manual).where(Manual.id == uuid.UUID(manual_id)).values(blob_storage_key=file_path)
                )
                await db.commit()
            except Exception:
                pass

    await asyncio.gather(*[_upload_one(*args) for args in blob_upload_tasks])

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

    manual_outs = [out for (_manual, out) in created_manuals]
    return {"uploaded": len(manual_outs), "manuals": [m.model_dump() for m in manual_outs]}


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
                    file_path = manual.blob_storage_key
                    content: bytes | None = None

                    logger.info(
                        "_run_screening_task: loading %s blob_key=%r",
                        manual.original_filename, file_path,
                    )

                    # Try local disk first
                    if file_path and os.path.exists(file_path):
                        with open(file_path, "rb") as f:
                            content = f.read()
                        logger.info("_run_screening_task: loaded from disk %d bytes", len(content))
                    else:
                        # Not on local disk — try blob storage (MinIO / Azure).
                        # NOTE: do NOT skip paths that start with "/" — on Railway the
                        # blob_storage_key may look like an absolute path but the file
                        # no longer exists on local disk after a container restart.
                        if file_path:
                            try:
                                from app.services.blob_storage import BlobStorageService
                                blob_svc = BlobStorageService()
                                content = await blob_svc.download_bytes(file_path)
                                logger.info(
                                    "_run_screening_task: downloaded from blob %d bytes for %s",
                                    len(content), manual.original_filename,
                                )
                            except Exception as blob_err:
                                logger.warning(
                                    "_run_screening_task: blob download failed for %s key=%r: %s",
                                    manual.original_filename, file_path, blob_err,
                                )

                    # Reset classification fields BEFORE re-classifying so stale data
                    # never persists if the new result differs (e.g. empty page ranges).
                    await db.execute(
                        update(Manual).where(Manual.id == manual.id).values(
                            pages_with_components="",
                            pages_with_jobs="",
                            pages_with_spares="",
                        )
                    )
                    await db.commit()

                    ext = (manual.file_extension or "").lower()
                    if content and ext == "pdf":
                        cr = await asyncio.to_thread(classify_pdf, content, manual.original_filename)
                    else:
                        # No PDF bytes — fall back to stored extracted_text in DB
                        stored_text = getattr(manual, "extracted_text", None) or ""
                        if stored_text:
                            logger.info(
                                "_run_screening_task: using stored extracted_text (%d chars) for %s",
                                len(stored_text), manual.original_filename,
                            )
                            from app.services.classifier import (
                                _classify_with_groq, _classify_with_gemini, _classify_with_claude,
                                _sanitise_result, _keyword_classify as _kw_cls,
                                _resolve_pages, _scan_pages,
                                VALID_CATEGORIES, ClassificationResult,
                            )
                            # Parse stored text into per-page list by [PAGE N] or [PAGE N, doc_page=X] markers
                            import re as _re
                            parts = _re.split(r'\[PAGE \d+(?:, doc_page=[^\]]+)?\]\n?', stored_text)
                            pages_text = [p.strip() for p in parts if p.strip()]
                            page_count = manual.page_count or len(pages_text)
                            # Try Groq (free, 30 RPM) → Gemini → Claude → keywords for CATEGORY only
                            ai = await asyncio.to_thread(
                                _classify_with_groq, pages_text, manual.original_filename, page_count
                            )
                            if not ai:
                                ai = await asyncio.to_thread(
                                    _classify_with_gemini, pages_text, manual.original_filename, page_count
                                )
                            if not ai:
                                ai = await asyncio.to_thread(
                                    _classify_with_claude, pages_text, manual.original_filename, page_count
                                )
                            if ai:
                                category = ai.get("category", "Unknown/Unclassifiable")
                                if category not in VALID_CATEGORIES:
                                    category = "Unknown/Unclassifiable"
                                
                                # Use AI-provided pages if available
                                from app.services.classifier import _make_marked_text, _filter_to_valid_pages
                                marked_text, valid_doc_pages = _make_marked_text(pages_text, max_chars=80_000)
                                ai_components = ai.get("pages_with_components", "").strip()
                                ai_jobs = ai.get("pages_with_jobs", "").strip()
                                ai_spares = ai.get("pages_with_spares", "").strip()
                                
                                if ai_components or ai_jobs or ai_spares:
                                    components = _filter_to_valid_pages(ai_components, valid_doc_pages)
                                    jobs = _filter_to_valid_pages(ai_jobs, valid_doc_pages)
                                    spares = _filter_to_valid_pages(ai_spares, valid_doc_pages)
                                else:
                                    # Programmatic page scan
                                    resolved = _resolve_pages(pages_text)
                                    components, jobs, spares = _scan_pages(pages_text, resolved, category)
                                
                                cr = _sanitise_result(ClassificationResult(
                                    category=category,
                                    confidence=max(0, min(100, int(ai.get("confidence", 60)))),
                                    useful_for_extraction=ai.get("useful_for_extraction", "partial"),
                                    pages_with_components=components,
                                    pages_with_jobs=jobs,
                                    pages_with_spares=spares,
                                    page_count=page_count,
                                ))
                            else:
                                kw_result = _kw_cls(pages_text, manual.original_filename, page_count)
                                resolved = _resolve_pages(pages_text)
                                components, jobs, spares = _scan_pages(pages_text, resolved, kw_result.category)
                                kw_result.pages_with_components = components
                                kw_result.pages_with_jobs = jobs
                                kw_result.pages_with_spares = spares
                                cr = _sanitise_result(kw_result)
                        else:
                            logger.warning(
                                "_run_screening_task: no PDF and no extracted_text for %s — using keyword fallback",
                                manual.original_filename,
                            )
                            cr = _keyword_classify([], manual.original_filename, 0)

                    # Also re-extract text with [PAGE N] markers if the stored text lacks them
                    new_extracted_text: str | None = None
                    if content and ext == "pdf":
                        stored = getattr(manual, "extracted_text", None) or ""
                        if not stored or "[PAGE " not in stored:
                            try:
                                import io as _io
                                import pdfplumber as _pdfplumber

                                def _reextract(data: bytes) -> str:
                                    parts: list[str] = []
                                    with _pdfplumber.open(_io.BytesIO(data)) as pdf:
                                        for pnum, pg in enumerate(pdf.pages, start=1):
                                            pparts: list[str] = []
                                            t = pg.extract_text()
                                            if t and t.strip():
                                                pparts.append(t)
                                            try:
                                                for tbl in (pg.extract_tables() or []):
                                                    if not tbl:
                                                        continue
                                                    rows = [
                                                        " | ".join(str(c).strip() if c else "" for c in row)
                                                        for row in tbl if row and any(c for c in row if c)
                                                    ]
                                                    if rows:
                                                        pparts.append("[TABLE]\n" + "\n".join(rows))
                                            except Exception:
                                                pass

                                            if pparts:
                                                parts.append(f"[PAGE {pnum}]\n" + "\n".join(pparts))
                                            else:
                                                parts.append(f"[PAGE {pnum}]\n")
                                    return "\n\n".join(parts)

                                new_extracted_text = await asyncio.to_thread(_reextract, content)
                            except Exception as re_err:
                                logger.warning(
                                    "_run_screening_task: text re-extraction failed for %s: %s",
                                    manual.original_filename, re_err,
                                )

                    update_vals: dict = dict(
                        category=cr.category,
                        classification_confidence=cr.confidence,
                        useful_for_extraction=cr.useful_for_extraction,
                        pages_with_components=cr.pages_with_components,
                        pages_with_jobs=cr.pages_with_jobs,
                        pages_with_spares=cr.pages_with_spares,
                        supply_type=getattr(cr, "supply_type", "OEM"),
                        status=ManualStatus.classified,
                    )
                    if new_extracted_text:
                        update_vals["extracted_text"] = new_extracted_text

                    await db.execute(
                        update(Manual).where(Manual.id == manual.id).values(**update_vals)
                    )
                    await db.commit()
                except Exception as exc:
                    logger.error(
                        "_run_screening_task: failed for manual %s: %s",
                        manual.original_filename, exc,
                    )
                _screening_state[vessel_id_str]["done"] += 1
                # Pause between manuals so Gemini free-tier rate limit (RPM) can reset
                await asyncio.sleep(20)

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


@router.post(
    "/{vessel_id}/manuals/screen-selected",
    summary="Screen (classify) selected manuals for a vessel using Claude AI",
)
async def screen_selected_manuals(
    vessel_id: uuid.UUID,
    body: dict,
    background_tasks: BackgroundTasks,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, Any]:
    """Re-classifies selected manuals for the vessel using Claude AI (or keyword fallback)."""
    await _get_vessel_or_404(vessel_id, db)

    manual_ids: list[str] = body.get("manual_ids", [])
    if not manual_ids:
        return {"started": False, "message": "No manual_ids provided.", "total": 0}

    vessel_id_str = str(vessel_id)
    _screening_state[vessel_id_str] = {
        "total": len(manual_ids),
        "done": 0,
        "status": "running",
    }
    background_tasks.add_task(
        _run_screening_task, vessel_id_str, str(current_user.tenant_id), manual_ids
    )
    return {"started": True, "total": len(manual_ids)}


# In-memory extraction progress tracker (per vessel_id string)
_extract_state: dict[str, dict] = {}


async def _run_extract_selected_task(vessel_id_str: str, manual_ids: list[str]) -> None:
    """Background task: runs auto_extract_from_manual for each selected manual."""
    from app.services.extractor import auto_extract_from_manual

    _extract_state[vessel_id_str] = {"total": len(manual_ids), "done": 0, "status": "running"}
    try:
        for manual_id in manual_ids:
            try:
                await auto_extract_from_manual(manual_id)
            except Exception as exc:
                logger.error("_run_extract_selected_task: extraction failed for manual %s: %s", manual_id, exc)
            _extract_state[vessel_id_str]["done"] += 1
        _extract_state[vessel_id_str]["status"] = "completed"
    except Exception as exc:
        logger.error("_run_extract_selected_task: task failed: %s", exc)
        _extract_state[vessel_id_str]["status"] = "failed"


@router.post(
    "/{vessel_id}/manuals/extract-selected",
    summary="Extract data from selected manuals using Claude AI",
)
async def extract_selected_manuals(
    vessel_id: uuid.UUID,
    body: dict,
    background_tasks: BackgroundTasks,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, Any]:
    """Runs extraction on the selected manuals using Claude AI."""
    await _get_vessel_or_404(vessel_id, db)

    manual_ids: list[str] = body.get("manual_ids", [])
    if not manual_ids:
        return {"started": False, "message": "No manual_ids provided.", "total": 0}

    vessel_id_str = str(vessel_id)
    background_tasks.add_task(_run_extract_selected_task, vessel_id_str, manual_ids)
    return {"started": True, "total": len(manual_ids)}


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
        _log.warning("view_manual: manual_id=%s has no blob_storage_key", manual_id)
        raise HTTPException(status_code=404, detail="File not available — this manual has no stored file. Please delete and re-upload it.")

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

    _log.info("view_manual: manual_id=%s blob_key=%s", manual_id, blob_key)

    # Try local disk first (fast path for dev / same-container uploads)
    if os.path.exists(blob_key):
        with open(blob_key, "rb") as fh:
            file_bytes = fh.read()
        _log.info("view_manual: served %d bytes from local disk", len(file_bytes))
        return Response(
            content=file_bytes,
            media_type=media_type,
            headers={"Content-Disposition": f'inline; filename="{manual.original_filename}"'},
        )

    # Not on local disk — download from blob storage (R2 / MinIO / Azure)
    blob_service = BlobStorageService()

    if blob_service._use_azure:
        try:
            presigned_url = await blob_service.get_download_url(blob_key, expires_in=3600)
            return JSONResponse({"url": presigned_url}, status_code=200)
        except Exception as exc:
            _log.warning("view_manual: Azure presigned URL failed key=%s: %s — streaming", blob_key, exc)

    try:
        _log.info("view_manual: downloading from blob storage key=%s", blob_key)
        file_bytes = await blob_service.download_bytes(blob_key)
        _log.info("view_manual: downloaded %d bytes for key=%s", len(file_bytes), blob_key)
        return Response(
            content=file_bytes,
            media_type=media_type,
            headers={"Content-Disposition": f'inline; filename="{manual.original_filename}"'},
        )
    except Exception as exc:
        _log.error("view_manual: blob download FAILED key=%s error=%s", blob_key, exc, exc_info=True)
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
