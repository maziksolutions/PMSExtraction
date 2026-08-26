from __future__ import annotations



import uuid

from typing import Annotated, Any, Optional



import asyncio

import os



import logging as _log_mod

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Query, UploadFile, status



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

from app.services.upload_security import validate_uploaded_file_bytes



router = APIRouter()



# In-memory screening progress tracker (per vessel_id string)

# Structure: { vessel_id: { "total": int, "done": int, "status": "idle"|"running"|"completed" } }

import redis
import json

_screening_state: dict[str, dict] = {}
_sync_redis_client: Optional[redis.Redis] = None

_active_screening_tasks: dict[str, asyncio.Task] = {}
_screening_paused_flags: dict[str, bool] = {}


def pause_screening(vessel_id_str: str) -> bool:
    state = get_screening_state(vessel_id_str)
    if state and state.get("status") == "running":
        _screening_paused_flags[vessel_id_str] = True
        set_screening_state(vessel_id_str, status="paused")
        return True
    return False


def resume_screening(vessel_id_str: str) -> bool:
    state = get_screening_state(vessel_id_str)
    if state and state.get("status") == "paused":
        _screening_paused_flags[vessel_id_str] = False
        set_screening_state(vessel_id_str, status="running")
        return True
    return False


def stop_screening(vessel_id_str: str) -> bool:
    _screening_paused_flags.pop(vessel_id_str, None)
    task = _active_screening_tasks.pop(vessel_id_str, None)
    if task and not task.done():
        task.cancel()
        set_screening_state(vessel_id_str, status="idle")
        return True
    state = get_screening_state(vessel_id_str)
    if state and state.get("status") in ("running", "paused"):
        set_screening_state(vessel_id_str, status="idle")
        return True
    return False

def _get_sync_redis_client() -> Optional[redis.Redis]:
    global _sync_redis_client
    if _sync_redis_client is None:
        try:
            _sync_redis_client = redis.Redis.from_url(settings.REDIS_URL, decode_responses=True, socket_timeout=2.0)
        except Exception as exc:
            logger.warning("Failed to initialize sync Redis client for ingestion: %s", exc)
    return _sync_redis_client


def set_screening_state(
    vessel_id_str: str,
    *,
    total: int | None = None,
    done: int | None = None,
    status: str | None = None,
    current_manual_name: str | None = None,
    detailed_status: str | None = None,
) -> None:
    key = f"screening_state:{vessel_id_str}"
    state = {}
    try:
        r = _get_sync_redis_client()
        if r:
            val = r.get(key)
            if val:
                state = json.loads(val)
    except Exception as exc:
        logger.debug("Failed to read screening state from Redis: %s", exc)

    if not state:
        state = _screening_state.get(vessel_id_str, {})

    if not state:
        state = {
            "total": 0,
            "done": 0,
            "status": "idle",
            "current_manual_name": None,
            "detailed_status": None,
        }

    if total is not None:
        state["total"] = total
    if done is not None:
        state["done"] = done
    if status is not None:
        state["status"] = status
        if status in ("completed", "failed", "idle"):
            state["current_manual_name"] = None
            state["detailed_status"] = None
    if current_manual_name is not None:
        state["current_manual_name"] = current_manual_name
    if detailed_status is not None:
        state["detailed_status"] = detailed_status

    # Save to local cache
    _screening_state[vessel_id_str] = state

    # Save to Redis
    try:
        r = _get_sync_redis_client()
        if r:
            r.set(key, json.dumps(state), ex=86400)
    except Exception as exc:
        logger.debug("Failed to write screening state to Redis: %s", exc)


def get_screening_state(vessel_id_str: str) -> dict[str, Any]:
    key = f"screening_state:{vessel_id_str}"
    try:
        r = _get_sync_redis_client()
        if r:
            val = r.get(key)
            if val:
                return json.loads(val)
    except Exception as exc:
        logger.debug("Failed to fetch screening state from Redis: %s", exc)

    return _screening_state.get(
        vessel_id_str,
        {"total": 0, "done": 0, "status": "idle", "current_manual_name": None, "detailed_status": None},
    )





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


@router.get("/debug-restore-m29", tags=["Debug"])
async def debug_restore_m29(db: AsyncSession = Depends(get_db)):
    from sqlalchemy import text
    try:
        # Find the manuals matching M-29
        res = await db.execute(text("""
            SELECT id, original_filename FROM manuals 
            WHERE original_filename LIKE '%M-29%' AND is_deleted = false;
        """))
        rows = res.fetchall()
        results = []
        for row in rows:
            mid = row[0]
            filename = row[1]
            
            # Count deleted records
            c_del = (await db.execute(text("SELECT COUNT(*) FROM components WHERE source_manual_id = :mid AND is_deleted = true;"), {"mid": mid})).scalar()
            j_del = (await db.execute(text("SELECT COUNT(*) FROM jobs WHERE source_manual_id = :mid AND is_deleted = true;"), {"mid": mid})).scalar()
            s_del = (await db.execute(text("SELECT COUNT(*) FROM spares WHERE source_manual_id = :mid AND is_deleted = true;"), {"mid": mid})).scalar()
            
            # Restore
            await db.execute(text("UPDATE components SET is_deleted = false WHERE source_manual_id = :mid;"), {"mid": mid})
            await db.execute(text("UPDATE jobs SET is_deleted = false WHERE source_manual_id = :mid;"), {"mid": mid})
            await db.execute(text("UPDATE spares SET is_deleted = false WHERE source_manual_id = :mid;"), {"mid": mid})
            await db.execute(text("UPDATE manuals SET status = 'classified', error_message = null WHERE id = :mid;"), {"mid": mid})
            await db.commit()
            
            results.append({
                "manual_id": str(mid),
                "filename": filename,
                "components_restored": c_del,
                "jobs_restored": j_del,
                "spares_restored": s_del
            })
        return {"status": "success", "results": results}
    except Exception as e:
        return {"status": "error", "message": str(e)}


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
        from urllib.parse import urlparse
        hostname = urlparse(folder_url).netloc  # e.g. unionmaritime.sharepoint.com
        sp_service = SharePointService(sharepoint_hostname=hostname)
        result = await sp_service.list_folder_contents_v2(
            folder_url,
            drive_id=body.drive_id,
            folder_id=body.folder_id
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=503,
            detail=f"SharePoint not configured: {exc}. Ensure AZURE_CLIENT_ID and AZURE_CLIENT_SECRET are set in Railway environment variables.",
        )
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"SharePoint listing failed: {exc}",
        )

    return SharePointFileListResponse(**result)





async def _process_sharepoint_file_bg(
    manual_id: str,
    vessel_id_str: str,
    tenant_id_str: str,
    download_url: str,
    filename: str,
    session_id_str: str,
) -> None:
    """
    FastAPI BackgroundTask: Download a file from SharePoint, upload it to blob storage,
    and then run text extraction and classification.
    """
    from app.core.database import AsyncSessionLocal
    from app.models.ingestion import Manual, ManualStatus, IngestionSession, IngestionSessionStatus
    from app.services.blob_storage import BlobStorageService
    from sqlalchemy import select as _select, update as _update
    import httpx
    import io

    # Step 1: Update manual status to downloading
    async with AsyncSessionLocal() as db:
        await db.execute(
            _update(Manual)
            .where(Manual.id == uuid.UUID(manual_id))
            .values(status=ManualStatus.downloading)
        )
        await db.commit()

    # Step 2: Download the file content from SharePoint
    try:
        import os
        is_mock = not (os.getenv("AZURE_CLIENT_ID") and os.getenv("AZURE_CLIENT_SECRET"))
        if is_mock or "mock" in download_url:
            content = (
                b"%PDF-1.4\n"
                b"1 0 obj <</Type/Catalog/Pages 2 0 R>> endobj\n"
                b"2 0 obj <</Type/Pages/Kids[3 0 R]/Count 1>> endobj\n"
                b"3 0 obj <</Type/Page/Parent 2 0 R/MediaBox[0 0 595 842]/Contents 4 0 R>> endobj\n"
                b"4 0 obj <</Length 49>> stream\n"
                b"BT /F1 12 Tf 70 700 Td (Mock manual content for vessel PMS) Tj ET\n"
                b"endstream endobj\n"
                b"xref\n"
                b"0 5\n"
                b"0000000000 65535 f\n"
                b"0000000009 00000 n\n"
                b"0000000056 00000 n\n"
                b"0000000111 00000 n\n"
                b"0000000202 00000 n\n"
                b"trailer <</Size 5/Root 1 0 R>>\n"
                b"startxref\n"
                b"302\n"
                b"%%EOF\n"
            )
            content_type = "application/pdf"
        else:
            async with httpx.AsyncClient(timeout=300, follow_redirects=True) as client:
                resp = await client.get(download_url)
                resp.raise_for_status()
                content = resp.content
                content_type = resp.headers.get("content-type", "application/octet-stream")

        # Step 3: Upload to Blob Storage
        blob_key = f"{tenant_id_str}/{vessel_id_str}/{manual_id}/{filename}"
        blob_service = BlobStorageService()
        await blob_service.upload_stream(
            blob_key,
            io.BytesIO(content),
            content_type,
        )

        # Update manual metadata with key and size, and reset status to queued (ready for user action)
        async with AsyncSessionLocal() as db:
            await db.execute(
                _update(Manual)
                .where(Manual.id == uuid.UUID(manual_id))
                .values(
                    blob_storage_key=blob_key,
                    file_size_bytes=len(content),
                    status=ManualStatus.queued,
                )
            )
            await db.commit()

        # Step 5: Update the IngestionSession's downloaded_files counter
        async with AsyncSessionLocal() as db:
            await db.execute(
                _update(IngestionSession)
                .where(IngestionSession.id == uuid.UUID(session_id_str))
                .values(downloaded_files=IngestionSession.downloaded_files + 1)
            )
            await db.commit()

            # Check if all files in the session are done
            session_ref = await db.scalar(
                _select(IngestionSession).where(IngestionSession.id == uuid.UUID(session_id_str))
            )
            if session_ref:
                processed = session_ref.downloaded_files + session_ref.failed_files
                if processed >= session_ref.total_files:
                    session_status = IngestionSessionStatus.completed
                    if session_ref.failed_files == session_ref.total_files:
                        session_status = IngestionSessionStatus.failed
                    
                    await db.execute(
                        _update(IngestionSession)
                        .where(IngestionSession.id == uuid.UUID(session_id_str))
                        .values(status=session_status)
                    )
                    await db.commit()

    except Exception as exc:
        logger.error("SharePoint download/process background task failed for %s: %s", filename, exc, exc_info=True)
        async with AsyncSessionLocal() as db:
            await db.execute(
                _update(Manual)
                .where(Manual.id == uuid.UUID(manual_id))
                .values(status=ManualStatus.failed, error_message=str(exc))
            )
            await db.execute(
                _update(IngestionSession)
                .where(IngestionSession.id == uuid.UUID(session_id_str))
                .values(failed_files=IngestionSession.failed_files + 1)
            )
            await db.commit()

            # Check if all files in the session are done
            session_ref = await db.scalar(
                _select(IngestionSession).where(IngestionSession.id == uuid.UUID(session_id_str))
            )
            if session_ref:
                processed = session_ref.downloaded_files + session_ref.failed_files
                if processed >= session_ref.total_files:
                    session_status = IngestionSessionStatus.completed
                    if session_ref.failed_files == session_ref.total_files:
                        session_status = IngestionSessionStatus.failed
                    
                    await db.execute(
                        _update(IngestionSession)
                        .where(IngestionSession.id == uuid.UUID(session_id_str))
                        .values(status=session_status)
                    )
                    await db.commit()


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
    background_tasks: BackgroundTasks,
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

    # Create manuals and collect (manual_id, download_url, filename) for task dispatch
    manual_tasks: list[tuple[str, str, str]] = []
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
            batch_number=body.batch_number,
        )
        db.add(manual)
        await db.flush()
        manual_tasks.append((str(manual.id), download_url, name))

    await db.commit()
    await db.refresh(session)

    # Dispatch background tasks using FastAPI's BackgroundTasks (bypassing Celery if worker is not running)
    for manual_id, download_url, name in manual_tasks:
        background_tasks.add_task(
            _process_sharepoint_file_bg,
            manual_id=manual_id,
            vessel_id_str=str(vessel_id),
            tenant_id_str=str(current_user.tenant_id),
            download_url=download_url,
            filename=name,
            session_id_str=str(session.id),
        )

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
    from datetime import timedelta
    manuals_result = await db.execute(
        select(Manual).where(
            Manual.vessel_id == vessel_id,
            Manual.tenant_id == current_user.tenant_id,
            Manual.is_deleted == False,
            Manual.created_at >= session.created_at - timedelta(seconds=10),
        )
    )

    manuals = manuals_result.scalars().all()



    return {

        **IngestionSessionOut.model_validate(session).model_dump(),
        "manuals": [ManualOut.model_validate(m) for m in manuals],
    }


@router.post(
    "/{vessel_id}/ingestion/sessions/{session_id}/manuals/{manual_id}/retry",
    summary="Retry a failed manual download inside a session",
)
async def retry_manual(
    vessel_id: uuid.UUID,
    session_id: uuid.UUID,
    manual_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    background_tasks: BackgroundTasks,
) -> dict[str, Any]:
    await _get_vessel_or_404(vessel_id, db)

    # 1. Fetch manual
    result = await db.execute(
        select(Manual).where(
            Manual.id == manual_id,
            Manual.vessel_id == vessel_id,
            Manual.tenant_id == current_user.tenant_id,
            Manual.is_deleted == False,
        )
    )
    manual = result.scalar_one_or_none()
    if manual is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Manual not found")

    if manual.status != ManualStatus.failed:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Can only retry failed manuals",
        )

    # 2. Fetch session
    session_result = await db.execute(
        select(IngestionSession).where(
            IngestionSession.id == session_id,
            IngestionSession.vessel_id == vessel_id,
            IngestionSession.is_deleted == False,
        )
    )
    session = session_result.scalar_one_or_none()
    if session is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

    # 3. Update Manual status
    manual.status = ManualStatus.queued
    manual.error_message = None
    manual.retry_count = 0

    # 4. Update Session status (decrement failed count and set status back to active)
    session.failed_files = max(0, session.failed_files - 1)
    session.status = IngestionSessionStatus.active

    await db.commit()

    # 5. Dispatch background task
    background_tasks.add_task(
        _process_sharepoint_file_bg,
        manual_id=str(manual.id),
        vessel_id_str=str(vessel_id),
        tenant_id_str=str(current_user.tenant_id),
        download_url=manual.sharepoint_path or "",
        filename=manual.original_filename,
        session_id_str=str(session.id),
    )

    return {"status": "retry_dispatched", "manual_id": manual_id}





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

    from app.services.feedback_learning import build_learning_context



    async with AsyncSessionLocal() as db:

        manual = await db.scalar(

            _select(Manual).where(Manual.id == uuid.UUID(manual_id))

        )

        if manual is None:

            logger.warning("_process_uploaded_file: manual %s not found", manual_id)

            return



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

        learning_context = await build_learning_context(

            db,

            tenant_id=uuid.UUID(tenant_id_str),

            entity_type="manual_classification",

            source_manual_category=getattr(manual, "category", None),

        )

        try:

            if file_ext == "pdf":

                result = await asyncio.to_thread(classify_pdf, file_bytes, filename, learning_context)

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

        # Use only columns that really exist in current DB schema to avoid 500 on mismatched migrations

        from sqlalchemy import inspect

        manual_cols = {c.name for c in inspect(Manual).columns}



        update_vals = {

            "status": ManualStatus.classified,

            "category": result.category,

            "classification_confidence": result.confidence,

            "useful_for_extraction": result.useful_for_extraction,

            "pages_with_components": result.pages_with_components,

            "pages_with_jobs": result.pages_with_jobs,

            "pages_with_spares": result.pages_with_spares,

        }



        extras = {

            "pages_with_components_printed": getattr(result, "pages_with_components_printed", ""),

            "pages_with_jobs_printed": getattr(result, "pages_with_jobs_printed", ""),

            "pages_with_spares_printed": getattr(result, "pages_with_spares_printed", ""),

            "pages_with_components_physical": getattr(result, "pages_with_components_physical", ""),

            "pages_with_jobs_physical": getattr(result, "pages_with_jobs_physical", ""),

            "pages_with_spares_physical": getattr(result, "pages_with_spares_physical", ""),

            "page_explanations": getattr(result, "page_explanations", ""),

        }



        if "supply_type" in manual_cols:

            update_vals["supply_type"] = getattr(result, "supply_type", "OEM")

        if "page_count" in manual_cols:

            update_vals["page_count"] = page_count_val or result.page_count or None

        if "extracted_text" in manual_cols:

            update_vals["extracted_text"] = extracted_text or None



        await db.execute(

            _update(Manual)

            .where(Manual.id == uuid.UUID(manual_id))

            .values(**update_vals)

        )

        await db.commit()

        logger.info("_process_uploaded_file: classified %s ' %s (%d%%) supply=%s", filename, result.category, result.confidence, getattr(result, "supply_type", "OEM"))





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
    batch_number: Optional[int] = Form(1),
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



    ALLOWED_EXTENSIONS = (

        {"pdf", "docx", "xlsx"}

        if settings.REQUIRE_STRICT_UPLOAD_VALIDATION

        else {"pdf", "docx", "doc", "xlsx", "xls"}

    )

    MAX_SIZE = 0  # 0 indicates unlimited size per file



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

        content = await upload.read()

        ext = validate_uploaded_file_bytes(

            filename=filename,

            content=content,

            allowed_extensions=ALLOWED_EXTENSIONS,

            max_size_bytes=MAX_SIZE,

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
            batch_number=batch_number,
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

            # Blob storage unavailable -- fall back to local disk

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

    """Background task: re-classifies the given manuals using bounded parallelism."""

    from app.core.database import AsyncSessionLocal

    from app.services.classifier import classify_pdf, _keyword_classify

    from app.services.feedback_learning import build_learning_context



    try:
        _active_screening_tasks[vessel_id_str] = asyncio.current_task()

        async with AsyncSessionLocal() as db:

            result = await db.execute(

                select(Manual).where(

                    Manual.id.in_([uuid.UUID(mid) for mid in manual_ids]),

                    Manual.is_deleted == False,

                )

            )

            manuals = result.scalars().all()



        runnable_manual_ids = [str(manual.id) for manual in manuals]

        set_screening_state(vessel_id_str, total=len(runnable_manual_ids), done=0, status="running")



        semaphore = asyncio.Semaphore(max(1, int(getattr(settings, "MANUAL_SCREENING_CONCURRENCY", 2) or 2)))

        state_lock = asyncio.Lock()

        delay_seconds = max(0.0, float(getattr(settings, "MANUAL_SCREENING_DELAY_SECONDS", 2.0) or 0.0))



        async def _screen_one(manual_id: str) -> None:

            async with semaphore:
                while _screening_paused_flags.get(vessel_id_str):
                    await asyncio.sleep(1)

                manual_name = manual_id

                try:

                    async with AsyncSessionLocal() as db:

                        manual_result = await db.execute(

                            select(Manual).where(

                                Manual.id == uuid.UUID(manual_id),

                                Manual.is_deleted == False,

                            )

                        )

                        manual = manual_result.scalar_one_or_none()

                        if manual is None:

                            return



                        manual_name = manual.original_filename

                        set_screening_state(

                            vessel_id_str,

                            current_manual_name=manual_name,

                            detailed_status="Loading file content..."

                        )

                        file_path = manual.blob_storage_key

                        content: bytes | None = None



                        logger.info(

                            "_run_screening_task: loading %s blob_key=%r",

                            manual.original_filename, file_path,

                        )



                        if file_path and os.path.exists(file_path):

                            with open(file_path, "rb") as f:

                                content = f.read()

                            logger.info("_run_screening_task: loaded from disk %d bytes", len(content))

                        elif file_path:

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



                        await db.execute(

                            update(Manual).where(Manual.id == manual.id).values(

                                pages_with_components="",

                                pages_with_jobs="",

                                pages_with_spares="",

                            )

                        )

                        await db.commit()



                        ext = (manual.file_extension or "").lower()

                        learning_context = await build_learning_context(

                            db,

                            tenant_id=uuid.UUID(tenant_id_str),

                            entity_type="manual_classification",

                            source_manual_category=getattr(manual, "category", None),

                        )

                        set_screening_state(

                            vessel_id_str,

                            detailed_status="Running AI classification..."

                        )

                        if content and ext == "pdf":
                            def _on_page_scanned(page_num: int, total_pages: int):
                                set_screening_state(
                                    vessel_id_str,
                                    current_manual_name=manual_name,
                                    detailed_status=f"Scanning page {page_num} / {total_pages}..."
                                )

                            cr = await asyncio.to_thread(
                                classify_pdf,
                                content,
                                manual.original_filename,
                                learning_context,
                                _on_page_scanned,
                            )

                        else:

                            stored_text = getattr(manual, "extracted_text", None) or ""

                            if stored_text:

                                logger.info(

                                    "_run_screening_task: using stored extracted_text (%d chars) for %s",

                                    len(stored_text), manual.original_filename,

                                )

                                from app.services.classifier import classify_pages_text

                                import re as _re



                                parts = _re.split(r'\[PAGE \d+(?:, printed_page=[^\]]+)?\]\n?', stored_text)

                                pages_text = [p.strip() for p in parts if p.strip()]

                                page_count = manual.page_count or len(pages_text)

                                cr = await asyncio.to_thread(

                                    classify_pages_text,

                                    pages_text,

                                    manual.original_filename,

                                    page_count,

                                    learning_context,

                                )

                            else:

                                logger.warning(

                                    "_run_screening_task: no PDF and no extracted_text for %s -- using keyword fallback",

                                    manual.original_filename,

                                )

                                cr = _keyword_classify([], manual.original_filename, 0)



                        new_extracted_text: str | None = None
                        if getattr(cr, "pages_text", None) is not None:
                            # Re-use the already extracted text pages
                            formatted_pages = []
                            for idx, p_text in enumerate(cr.pages_text, start=1):
                                if p_text.strip():
                                    formatted_pages.append(f"[PAGE {idx}]\n{p_text}")
                                else:
                                    formatted_pages.append(f"[PAGE {idx}]\n")
                            new_extracted_text = "\n\n".join(formatted_pages)
                        elif content and ext == "pdf":
                            stored = getattr(manual, "extracted_text", None) or ""
                            if not stored or "[PAGE " not in stored:
                                try:
                                    import io as _io
                                    import pdfplumber as _pdfplumber

                                    def _reextract(data: bytes) -> str:
                                        parts: list[str] = []
                                        with _pdfplumber.open(_io.BytesIO(data)) as pdf:
                                            for pnum, pg in enumerate(pdf.pages, start=1):
                                                t_val = pg.extract_text() or ""
                                                if t_val.strip():
                                                    parts.append(f"[PAGE {pnum}]\n{t_val.strip()}")
                                                else:
                                                    parts.append(f"[PAGE {pnum}]\n")
                                        return "\n\n".join(parts)

                                    set_screening_state(
                                        vessel_id_str,
                                        detailed_status="Parsing and re-extracting text..."
                                    )
                                    new_extracted_text = await asyncio.to_thread(_reextract, content)
                                except Exception as re_err:
                                    logger.warning(
                                        "_run_screening_task: text re-extraction failed for %s: %s",
                                        manual.original_filename, re_err,
                                    )



                        update_vals: dict[str, Any] = {

                            "category": getattr(cr, "category", None) or manual.category,

                            "classification_confidence": cr.confidence,

                            "useful_for_extraction": cr.useful_for_extraction,

                            "pages_with_components": cr.pages_with_components,

                            "pages_with_jobs": cr.pages_with_jobs,

                            "pages_with_spares": cr.pages_with_spares,

                            "supply_type": getattr(cr, "supply_type", "OEM"),
                            "status": ManualStatus.classified,
                        }



                        extras = {

                            "pages_with_components_printed": getattr(cr, "pages_with_components_printed", ""),

                            "pages_with_jobs_printed": getattr(cr, "pages_with_jobs_printed", ""),

                            "pages_with_spares_printed": getattr(cr, "pages_with_spares_printed", ""),

                            "pages_with_components_physical": getattr(cr, "pages_with_components_physical", ""),

                            "pages_with_jobs_physical": getattr(cr, "pages_with_jobs_physical", ""),

                            "pages_with_spares_physical": getattr(cr, "pages_with_spares_physical", ""),

                            "page_explanations": getattr(cr, "page_explanations", ""),

                        }

                        from sqlalchemy import inspect



                        manual_cols = {c.name for c in inspect(Manual).columns}

                        for key, value in extras.items():

                            if key in manual_cols:

                                update_vals[key] = value

                        if new_extracted_text:

                            update_vals["extracted_text"] = new_extracted_text



                        await db.execute(

                            update(Manual).where(Manual.id == manual.id).values(**update_vals)

                        )

                        await db.commit()

                except Exception as exc:

                    logger.error("_run_screening_task: failed for manual %s: %s", manual_name, exc)

                finally:

                    async with state_lock:

                        st = get_screening_state(vessel_id_str)

                        set_screening_state(vessel_id_str, done=st.get("done", 0) + 1)



                if delay_seconds:

                    await asyncio.sleep(delay_seconds)



        await asyncio.gather(*[_screen_one(manual_id) for manual_id in runnable_manual_ids])

        set_screening_state(vessel_id_str, status="completed")

    except asyncio.CancelledError:
        set_screening_state(vessel_id_str, status="idle")
    except Exception:
        set_screening_state(vessel_id_str, status="failed")
    finally:
        _active_screening_tasks.pop(vessel_id_str, None)
        _screening_paused_flags.pop(vessel_id_str, None)





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





async def _run_extract_selected_task(
    vessel_id_str: str,
    manual_ids: list[str],
    entity_types: Optional[list[str]] = None,
    page_numbers: Optional[list[int]] = None,
) -> None:

    """Background task: runs auto_extract_from_manual with bounded parallelism."""

    from app.services.extractor import get_extraction_state, set_extraction_state, auto_extract_from_manual, _active_extraction_tasks, _extraction_paused_flags

    _active_extraction_tasks[vessel_id_str] = asyncio.current_task()

    import app.services.extractor as extractor_module
    extractor_module._claude_vision_billing_failed = False

    logger.warning(

        "_run_extract_selected_task: starting vessel=%s manuals=%s entity_types=%s page_numbers=%s",

        vessel_id_str,

        manual_ids,

        entity_types,

        page_numbers,

    )

    set_extraction_state(vessel_id_str, total=len(manual_ids), done=0, status="running")

    try:

        semaphore = asyncio.Semaphore(max(1, int(getattr(settings, "MANUAL_EXTRACTION_CONCURRENCY", 4) or 4)))

        state_lock = asyncio.Lock()

        async def _run_one(manual_id: str) -> None:

            async with semaphore:

                while _extraction_paused_flags.get(vessel_id_str):

                    await asyncio.sleep(1)

                try:

                    logger.warning(

                        "_run_extract_selected_task: extracting manual_id=%s vessel=%s page_numbers=%s",

                        manual_id,

                        vessel_id_str,

                        page_numbers,

                    )

                    await auto_extract_from_manual(manual_id, entity_types=entity_types, page_numbers=page_numbers)

                except Exception as exc:

                    logger.error("_run_extract_selected_task: extraction failed for manual %s: %s", manual_id, exc)

                finally:

                    async with state_lock:

                        state = get_extraction_state(vessel_id_str)

                        set_extraction_state(

                            vessel_id_str,

                            total=state.get("total", len(manual_ids)),

                            done=state.get("done", 0) + 1,

                            status="running",

                        )

        await asyncio.gather(*[_run_one(manual_id) for manual_id in manual_ids])

        state = get_extraction_state(vessel_id_str)

        set_extraction_state(

            vessel_id_str,

            total=state.get("total", len(manual_ids)),

            done=state.get("done", len(manual_ids)),

            status="completed",

        )

        logger.warning(

            "_run_extract_selected_task: completed vessel=%s total=%s done=%s",

            vessel_id_str,

            state.get("total", len(manual_ids)),

            state.get("done", len(manual_ids)),

        )

    except asyncio.CancelledError:

        logger.info("_run_extract_selected_task: task cancelled")

        set_extraction_state(vessel_id_str, status="idle")

    except Exception as exc:

        logger.error("_run_extract_selected_task: task failed: %s", exc)

        state = get_extraction_state(vessel_id_str)

        set_extraction_state(

            vessel_id_str,

            total=state.get("total", len(manual_ids)),

            done=state.get("done", 0),

            status="failed",

        )

    finally:

        _active_extraction_tasks.pop(vessel_id_str, None)

        _extraction_paused_flags.pop(vessel_id_str, None)





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
    entity_types: Optional[list[str]] = body.get("entity_types", None)
    page_numbers: Optional[list[int]] = body.get("page_numbers", None)

    if not manual_ids:

        return {"started": False, "message": "No manual_ids provided.", "total": 0}



    selected_manual_ids = {uuid.UUID(manual_id) for manual_id in manual_ids}

    result = await db.execute(

        select(Manual).where(

            Manual.id.in_(selected_manual_ids),

            Manual.vessel_id == vessel_id,

            Manual.tenant_id == current_user.tenant_id,

            Manual.is_deleted == False,

        )

    )

    manuals = result.scalars().all()

    manual_page_signals = {

        str(manual.id): any(

            [

                manual.pages_with_components_physical or manual.pages_with_components,

                manual.pages_with_jobs_physical or manual.pages_with_jobs,

                manual.pages_with_spares_physical or manual.pages_with_spares,

            ]

        )

        for manual in manuals

    }

    runnable_manual_ids = [manual_id for manual_id in manual_ids if manual_page_signals.get(manual_id)]



    if not runnable_manual_ids:

        return {

            "started": False,

            "total": 0,

            "message": "Selected manuals have no saved component/job/spare page refs. Save the screening refs first, then extract.",

        }



    vessel_id_str = str(vessel_id)

    from app.api.v1.extraction import set_extraction_state



    set_extraction_state(vessel_id_str, total=len(runnable_manual_ids), done=0, status="running")

    background_tasks.add_task(_run_extract_selected_task, vessel_id_str, runnable_manual_ids, entity_types, page_numbers)

    return {"started": True, "total": len(runnable_manual_ids)}





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

    state = get_screening_state(str(vessel_id))
    return state


@router.post("/{vessel_id}/screening-pause", summary="Pause active screening")
async def pause_screen(
    vessel_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, Any]:
    await _get_vessel_or_404(vessel_id, db)
    success = pause_screening(str(vessel_id))
    return {"success": success, "status": "paused" if success else "failed"}


@router.post("/{vessel_id}/screening-resume", summary="Resume paused screening")
async def resume_screen(
    vessel_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, Any]:
    await _get_vessel_or_404(vessel_id, db)
    success = resume_screening(str(vessel_id))
    return {"success": success, "status": "running" if success else "failed"}


@router.post("/{vessel_id}/screening-stop", summary="Stop/Cancel active screening")
async def stop_screen(
    vessel_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, Any]:
    await _get_vessel_or_404(vessel_id, db)
    success = stop_screening(str(vessel_id))
    return {"success": success, "status": "idle" if success else "failed"}





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

        raise HTTPException(status_code=404, detail="File not available -- this manual has no stored file. Please delete and re-upload it.")



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

    safe_filename = (manual.original_filename or "manual").replace("\r", "_").replace("\n", "_").replace('"', "'")



    _log.info("view_manual: manual_id=%s blob_key=%s", manual_id, blob_key)



    # Try local disk first (fast path for dev / same-container uploads)

    if os.path.exists(blob_key):

        with open(blob_key, "rb") as fh:

            file_bytes = fh.read()

        _log.info("view_manual: served %d bytes from local disk", len(file_bytes))

        return Response(

            content=file_bytes,

            media_type=media_type,

            headers={"Content-Disposition": f'inline; filename="{safe_filename}"'},

        )



    # Not on local disk -- download from blob storage (R2 / MinIO / Azure)
    blob_service = BlobStorageService()

    try:
        presigned_url = await blob_service.get_download_url(blob_key, expires_in=3600)
        return JSONResponse({"url": presigned_url}, status_code=200)
    except Exception as exc:
        _log.warning("view_manual: presigned URL generation failed key=%s: %s -- falling back to streaming", blob_key, exc)



    try:

        _log.info("view_manual: downloading from blob storage key=%s", blob_key)

        file_bytes = await blob_service.download_bytes(blob_key)

        _log.info("view_manual: downloaded %d bytes for key=%s", len(file_bytes), blob_key)

        return Response(

            content=file_bytes,

            media_type=media_type,

            headers={"Content-Disposition": f'inline; filename="{safe_filename}"'},

        )

    except Exception as exc:

        _log.error("view_manual: blob download FAILED key=%s error=%s", blob_key, exc, exc_info=True)

        raise HTTPException(status_code=502, detail=f"Could not retrieve file from storage: {exc}")





@router.get(
    "/{vessel_id}/manuals/{manual_id}/page-status",
    summary="Get page-by-page extraction status and count breakdown for a manual",
)
async def get_manual_page_status(
    vessel_id: uuid.UUID,
    manual_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    components_pages_unsaved: Optional[str] = Query(None),
    jobs_pages_unsaved: Optional[str] = Query(None),
    spares_pages_unsaved: Optional[str] = Query(None),
) -> dict[str, Any]:
    """
    Returns the page-by-page status and count breakdown for a manual.
    Allows passing unsaved page references to reform pages dynamically.
    """
    await _get_vessel_or_404(vessel_id, db)

    # Fetch manual
    result = await db.execute(
        select(Manual).where(
            Manual.id == manual_id,
            Manual.vessel_id == vessel_id,
            Manual.tenant_id == current_user.tenant_id,
            Manual.is_deleted == False,
        )
    )
    manual: Optional[Manual] = result.scalar_one_or_none()
    if manual is None:
        raise HTTPException(status_code=404, detail="Manual not found")

    from app.services.extractor import _parse_page_tokens

    # Use unsaved query params if provided, otherwise fallback to DB physical / canonical fields
    comp_ref_str = (
        components_pages_unsaved
        if components_pages_unsaved is not None
        else (manual.pages_with_components_physical or manual.pages_with_components)
    )
    job_ref_str = (
        jobs_pages_unsaved
        if jobs_pages_unsaved is not None
        else (manual.pages_with_jobs_physical or manual.pages_with_jobs)
    )
    spare_ref_str = (
        spares_pages_unsaved
        if spares_pages_unsaved is not None
        else (manual.pages_with_spares_physical or manual.pages_with_spares)
    )

    component_pages = set(_parse_page_tokens(comp_ref_str))
    job_pages = set(_parse_page_tokens(job_ref_str))
    spare_pages = set(_parse_page_tokens(spare_ref_str))
    all_targeted_pages = component_pages.union(job_pages).union(spare_pages)

    # Determine page range
    max_page = max(all_targeted_pages) if all_targeted_pages else 0
    total_pages = max(manual.page_count or 0, max_page)
    if total_pages == 0 and all_targeted_pages:
        total_pages = max_page

    # Fetch all active components, jobs, spares for this manual
    from app.models.component import Component
    from app.models.job import Job
    from app.models.spare import Spare

    comp_res = await db.execute(
        select(Component).where(
            Component.source_manual_id == manual_id,
            Component.vessel_id == vessel_id,
            Component.tenant_id == current_user.tenant_id,
            Component.is_deleted == False,
        )
    )
    components = comp_res.scalars().all()

    job_res = await db.execute(
        select(Job).where(
            Job.source_manual_id == manual_id,
            Job.vessel_id == vessel_id,
            Job.tenant_id == current_user.tenant_id,
            Job.is_deleted == False,
        )
    )
    jobs = job_res.scalars().all()

    spare_res = await db.execute(
        select(Spare).where(
            Spare.source_manual_id == manual_id,
            Spare.vessel_id == vessel_id,
            Spare.tenant_id == current_user.tenant_id,
            Spare.is_deleted == False,
        )
    )
    spares = spare_res.scalars().all()

    # Group by page number
    items_by_page = {}
    for comp in components:
        p = comp.page_reference
        if p is not None:
            items_by_page.setdefault(p, []).append({
                "type": "component",
                "name": comp.component_name,
                "detail": f"{comp.maker or ''} {comp.model or ''}".strip(),
            })

    for job in jobs:
        p = job.page_reference
        if p is not None:
            items_by_page.setdefault(p, []).append({
                "type": "job",
                "name": job.job_name,
                "detail": job.job_code or "",
            })

    for spare in spares:
        p = spare.page_reference
        if p is not None:
            items_by_page.setdefault(p, []).append({
                "type": "spare",
                "name": spare.part_name,
                "detail": spare.part_number or "",
            })

    pages_data = []
    for p in range(1, total_pages + 1):
        is_targeted = (p in component_pages) or (p in job_pages) or (p in spare_pages)
        page_items = items_by_page.get(p, [])
        extracted_count = len(page_items)

        # Skip pages that are not targeted and have no items extracted to keep the list focused
        if not is_targeted and extracted_count == 0:
            continue

        if not is_targeted:
            page_status = "skipped"
        else:
            if manual.status == ManualStatus.failed:
                page_status = "failed"
            elif manual.status in [ManualStatus.queued, ManualStatus.downloading, ManualStatus.converting, ManualStatus.translating, ManualStatus.scanning]:
                page_status = "pending"
            else:
                page_status = "success"

        pages_data.append({
            "page_number": p,
            "is_targeted": is_targeted,
            "status": page_status,
            "extracted_count": extracted_count,
            "targeted_types": {
                "component": p in component_pages,
                "job": p in job_pages,
                "spare": p in spare_pages,
            },
            "items": page_items
        })

    return {
        "manual_id": str(manual_id),
        "original_filename": manual.original_filename,
        "page_count": manual.page_count,
        "status": manual.status,
        "pages": pages_data,
    }


@router.get(
    "/{vessel_id}/manuals/statistics",
    summary="Get manual extraction statistics for a vessel",
)
async def get_vessel_manual_statistics(
    vessel_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, Any]:
    """
    Returns high-level and granular statistics on the manual extraction process
    for the vessel, including pages processed, counts of items, LLM requests, and estimated costs.
    """
    await _get_vessel_or_404(vessel_id, db)

    # 1. Fetch all manuals (both active and soft-deleted) that have valid blob storage keys
    result = await db.execute(
        select(Manual).where(
            Manual.vessel_id == vessel_id,
            Manual.tenant_id == current_user.tenant_id,
            Manual.blob_storage_key.is_not(None),
        )
    )
    manuals = result.scalars().all()

    # 2. Fetch all extracted active items for this vessel
    from app.models.component import Component
    from app.models.job import Job
    from app.models.spare import Spare

    comp_res = await db.execute(
        select(Component.source_manual_id, Component.page_reference).where(
            Component.vessel_id == vessel_id,
            Component.tenant_id == current_user.tenant_id,
            Component.is_deleted == False,
        )
    )
    components = comp_res.all()

    job_res = await db.execute(
        select(Job.source_manual_id, Job.page_reference).where(
            Job.vessel_id == vessel_id,
            Job.tenant_id == current_user.tenant_id,
            Job.is_deleted == False,
        )
    )
    jobs = job_res.all()

    spare_res = await db.execute(
        select(Spare.source_manual_id, Spare.page_reference).where(
            Spare.vessel_id == vessel_id,
            Spare.tenant_id == current_user.tenant_id,
            Spare.is_deleted == False,
        )
    )
    spares = spare_res.all()

    # Map item lists to manuals
    comps_by_manual = {}
    jobs_by_manual = {}
    spares_by_manual = {}
    for source_manual_id, page_ref in components:
        if source_manual_id:
            comps_by_manual.setdefault(source_manual_id, []).append(page_ref)
    for source_manual_id, page_ref in jobs:
        if source_manual_id:
            jobs_by_manual.setdefault(source_manual_id, []).append(page_ref)
    for source_manual_id, page_ref in spares:
        if source_manual_id:
            spares_by_manual.setdefault(source_manual_id, []).append(page_ref)

    # Constants for estimation
    # Claude Sonnet 3.5 is the primary provider.
    # Input tokens per page: 1600 tokens (image vision) or 800 tokens (text)
    # Output tokens per page: 300 tokens
    # Pricing: Input=$3.00/MTok, Output=$15.00/MTok
    CLAUDE_INPUT_COST = 3.0 / 1_000_000
    CLAUDE_OUTPUT_COST = 15.0 / 1_000_000
    
    total_manuals = len(manuals)
    total_pages = 0
    total_targeted_pages = 0
    total_components = len(components)
    total_jobs = len(jobs)
    total_spares = len(spares)
    total_requests = 0
    total_cost = 0.0

    manuals_breakdown = []

    from app.services.extractor import _parse_page_tokens

    for manual in manuals:
        m_id = manual.id
        m_filename = manual.original_filename
        m_category = manual.category or "Unclassified"
        m_page_count = manual.page_count or 0
        m_status = manual.status

        # Calculate targeted pages
        comp_pages = _parse_page_tokens(manual.pages_with_components_physical or manual.pages_with_components)
        job_pages = _parse_page_tokens(manual.pages_with_jobs_physical or manual.pages_with_jobs)
        spare_pages = _parse_page_tokens(manual.pages_with_spares_physical or manual.pages_with_spares)
        
        all_targeted = set(comp_pages).union(job_pages).union(spare_pages)
        m_targeted_count = len(all_targeted)
        
        # Extracted items
        m_comps_count = len(comps_by_manual.get(m_id, []))
        m_jobs_count = len(jobs_by_manual.get(m_id, []))
        m_spares_count = len(spares_by_manual.get(m_id, []))
        
        # Estimate requests
        m_requests = 0
        if manual.status == "failed":
            m_requests = 0
        elif manual.status == "classified" or m_comps_count > 0 or m_jobs_count > 0 or m_spares_count > 0:
            m_requests += len(comp_pages)
            m_requests += len(spare_pages) * 4
            m_requests += max(1, len(job_pages) // 2)

        # Estimate tokens and cost
        m_input_tokens = 0
        m_output_tokens = 0
        
        if m_requests > 0:
            m_input_tokens += len(comp_pages) * 1600
            m_input_tokens += len(spare_pages) * 4 * 1600
            m_input_tokens += max(1, len(job_pages) // 2) * 800
            m_output_tokens += m_requests * 300
            
        m_cost = (m_input_tokens * CLAUDE_INPUT_COST) + (m_output_tokens * CLAUDE_OUTPUT_COST)

        total_pages += m_page_count
        total_targeted_pages += m_targeted_count
        total_requests += m_requests
        total_cost += m_cost

        manuals_breakdown.append({
            "id": str(m_id),
            "filename": m_filename,
            "category": m_category,
            "status": m_status,
            "page_count": m_page_count,
            "targeted_count": m_targeted_count,
            "components_count": m_comps_count,
            "jobs_count": m_jobs_count,
            "spares_count": m_spares_count,
            "requests_estimate": m_requests,
            "cost_estimate": round(m_cost, 4),
            "created_at": manual.created_at.isoformat() if manual.created_at else None,
            "updated_at": manual.updated_at.isoformat() if manual.updated_at else None,
            "comp_pages": comp_pages,
            "job_pages": job_pages,
            "spare_pages": spare_pages,
            "is_deleted": manual.is_deleted,
        })

    claude_cost = total_cost * 0.75
    openai_cost = total_cost * 0.25

    from app.services.anthropic_admin import fetch_and_store_daily_costs
    from app.models.claude_cost import ClaudeDailyCost

    sync_result = await fetch_and_store_daily_costs(db)

    # Query all historical saved console daily cost reports
    db_costs_res = await db.execute(select(ClaudeDailyCost).order_by(ClaudeDailyCost.date.desc()))
    db_costs = db_costs_res.scalars().all()

    saved_usage = [
        {
            "date": c.date.isoformat(),
            "input_tokens": c.input_tokens,
            "output_tokens": c.output_tokens,
            "cost": c.cost
        } for c in db_costs
    ]

    return {
        "summary": {
            "total_manuals": total_manuals,
            "total_pages": total_pages,
            "total_targeted_pages": total_targeted_pages,
            "total_components": total_components,
            "total_jobs": total_jobs,
            "total_spares": total_spares,
            "total_extracted_items": total_components + total_jobs + total_spares,
            "total_requests_estimate": total_requests,
            "total_cost_estimate": round(total_cost, 2),
            "claude_cost": round(claude_cost, 2),
            "openai_cost": round(openai_cost, 2),
        },
        "manuals": manuals_breakdown,
        "api_status": {
            "anthropic_configured": bool(settings.ANTHROPIC_API_KEY),
            "openai_configured": bool(settings.OPENAI_API_KEY),
            "anthropic_model": "claude-3-5-sonnet-20240620",
            "openai_model": "gpt-4o",
            "anthropic_endpoint": "https://api.anthropic.com/v1/messages",
            "openai_endpoint": "https://api.openai.com/v1/chat/completions",
            "claude_input_rate": 3.00,
            "claude_output_rate": 15.00,
            "openai_input_rate": 5.00,
            "openai_output_rate": 15.00,
        },
        "console_data": {
            "status": sync_result["status"],
            "message": sync_result.get("message", ""),
            "usage_report": {
                "usage": saved_usage
            }
        }
    }





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



    # Cascade soft-delete to all records extracted from this manual so they

    # no longer appear in the spares/jobs/components lists or PDF filters.

    from app.models.spare import Spare, ExtractionMethod as _EM

    from app.models.job import Job

    from app.models.component import Component

    await db.execute(

        update(Spare)

        .where(

            Spare.source_manual_id == manual.id,

            Spare.is_deleted == False,

            Spare.extraction_method != _EM.manual,

        )

        .values(is_deleted=True)

    )

    await db.execute(

        update(Job)

        .where(Job.source_manual_id == manual.id, Job.is_deleted == False)

        .values(is_deleted=True)

    )

    await db.execute(

        update(Component)

        .where(Component.source_manual_id == manual.id, Component.is_deleted == False)

        .values(is_deleted=True)

    )



    await db.commit()

    return {"deleted": True}

