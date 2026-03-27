from __future__ import annotations

import logging
import os
import subprocess
import time
import uuid
from typing import Optional

import httpx
from celery import Task
from celery.exceptions import Retry
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings
from app.models.ingestion import Manual, ManualStatus, VirusScanStatus
from app.tasks import celery_app

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Synchronous DB session for Celery tasks (not async)
# ---------------------------------------------------------------------------

_SYNC_DB_URL = settings.DATABASE_URL.replace(
    "postgresql+asyncpg://", "postgresql+psycopg2://"
)

_engine = create_engine(_SYNC_DB_URL, pool_pre_ping=True)
SyncSession = sessionmaker(bind=_engine, autoflush=True, expire_on_commit=False)


def _get_manual(session: Session, manual_id: str) -> Optional[Manual]:
    result = session.execute(
        select(Manual).where(
            Manual.id == uuid.UUID(manual_id),
            Manual.is_deleted == False,
        )
    )
    return result.scalar_one_or_none()


# ---------------------------------------------------------------------------
# Task: download_sharepoint_file
# ---------------------------------------------------------------------------


@celery_app.task(
    bind=True,
    max_retries=3,
    name="app.tasks.ingestion.download_sharepoint_file",
    default_retry_delay=60,
)
def download_sharepoint_file(
    self: Task,
    manual_id: str,
    sharepoint_path: str,
    access_token: str,
) -> None:
    """
    Download file from SharePoint via Microsoft Graph API, store in blob
    storage, then trigger virus scan.
    """
    from app.services.blob_storage import BlobStorageService

    with SyncSession() as session:
        manual = _get_manual(session, manual_id)
        if manual is None:
            logger.error("Manual %s not found — aborting download task", manual_id)
            return

        # Step 1: mark as downloading
        manual.status = ManualStatus.downloading
        manual.error_message = None
        session.commit()

        try:
            # Step 2: build Graph API download URL
            graph_base = "https://graph.microsoft.com/v1.0"
            headers = {"Authorization": f"Bearer {access_token}"}

            with httpx.Client(timeout=30) as client:
                meta_resp = client.get(
                    f"{graph_base}/me/drive/root:/{sharepoint_path}",
                    headers=headers,
                )
                meta_resp.raise_for_status()
                meta = meta_resp.json()
                download_url: str = meta.get("@microsoft.graph.downloadUrl", "")

            if not download_url:
                raise ValueError("No downloadUrl returned from Graph API")

            # Step 3: stream to blob storage
            blob_key = (
                f"{manual.tenant_id}/{manual.vessel_id}/"
                f"{manual.id}/{manual.original_filename}"
            )
            blob_service = BlobStorageService()

            total_bytes = 0
            with httpx.Client(timeout=300, follow_redirects=True) as dl_client:
                with dl_client.stream("GET", download_url) as stream:
                    stream.raise_for_status()

                    def _byte_generator():
                        nonlocal total_bytes
                        for chunk in stream.iter_bytes(chunk_size=65536):
                            total_bytes += len(chunk)
                            yield chunk

                    content_type = stream.headers.get(
                        "content-type", "application/octet-stream"
                    )
                    blob_service.upload_stream_sync(blob_key, _byte_generator(), content_type)

            manual.blob_storage_key = blob_key
            manual.file_size_bytes = total_bytes
            manual.status = ManualStatus.scanning
            session.commit()

        except (httpx.HTTPError, httpx.TimeoutException, ValueError) as exc:
            logger.warning("Download failed for manual %s: %s", manual_id, exc)
            manual.retry_count = (manual.retry_count or 0) + 1
            manual.error_message = str(exc)

            if manual.retry_count < 3:
                manual.status = ManualStatus.queued
                session.commit()
                # Exponential backoff: 60s, 120s, 240s
                delay = 60 * (2 ** (manual.retry_count - 1))
                raise self.retry(exc=exc, countdown=delay)
            else:
                manual.status = ManualStatus.failed
                session.commit()
            return

    # Step 5: trigger virus scan
    virus_scan_file.delay(manual_id)


# ---------------------------------------------------------------------------
# Task: virus_scan_file
# ---------------------------------------------------------------------------


@celery_app.task(
    name="app.tasks.ingestion.virus_scan_file",
)
def virus_scan_file(manual_id: str) -> None:
    """
    Simulate virus scan (ClamAV integration point).
    Marks the manual as clean and triggers format processing.
    """
    with SyncSession() as session:
        manual = _get_manual(session, manual_id)
        if manual is None:
            logger.error("Manual %s not found for virus scan", manual_id)
            return

        # Real integration point: call ClamAV daemon via python-clamd
        # For now: simulate a 1-second scan and mark clean
        time.sleep(1)

        manual.virus_scan_status = VirusScanStatus.clean
        session.commit()

    # Continue pipeline
    process_file_format.delay(manual_id)


# ---------------------------------------------------------------------------
# Task: process_file_format
# ---------------------------------------------------------------------------


@celery_app.task(
    name="app.tasks.ingestion.process_file_format",
)
def process_file_format(manual_id: str) -> None:
    """
    Convert DOC to DOCX via LibreOffice if needed, detect language,
    and trigger translation if non-English.
    """
    with SyncSession() as session:
        manual = _get_manual(session, manual_id)
        if manual is None:
            logger.error("Manual %s not found for format processing", manual_id)
            return

        manual.status = ManualStatus.converting
        session.commit()

        try:
            blob_key = manual.blob_storage_key
            extension = manual.file_extension.lower().lstrip(".")

            # DOC -> DOCX conversion via LibreOffice headless
            if extension == "doc" and blob_key:
                from app.services.blob_storage import BlobStorageService

                blob_service = BlobStorageService()
                tmp_dir = f"/tmp/{manual_id}"
                os.makedirs(tmp_dir, exist_ok=True)
                tmp_input = os.path.join(tmp_dir, manual.original_filename)

                stream = blob_service.get_object_stream(blob_key)
                with open(tmp_input, "wb") as f:
                    for chunk in stream:
                        f.write(chunk)

                result = subprocess.run(
                    [
                        "libreoffice",
                        "--headless",
                        "--convert-to",
                        "docx",
                        "--outdir",
                        tmp_dir,
                        tmp_input,
                    ],
                    capture_output=True,
                    text=True,
                    timeout=120,
                )

                if result.returncode == 0:
                    new_filename = manual.original_filename.rsplit(".", 1)[0] + ".docx"
                    tmp_output = os.path.join(tmp_dir, new_filename)
                    new_key = blob_key.rsplit("/", 1)[0] + "/" + new_filename

                    with open(tmp_output, "rb") as fout:
                        blob_service.upload_stream_sync(
                            new_key,
                            fout,
                            "application/vnd.openxmlformats-officedocument"
                            ".wordprocessingml.document",
                        )
                    manual.blob_storage_key = new_key
                    manual.file_extension = "docx"
                else:
                    logger.warning(
                        "LibreOffice conversion failed for %s: %s",
                        manual_id,
                        result.stderr,
                    )

            # Language detection via Azure Translator detect endpoint
            detected_lang = _detect_language(manual_id, blob_key)
            manual.detected_language = detected_lang
            session.commit()

            if detected_lang and detected_lang != "en":
                manual.status = ManualStatus.translating
                session.commit()
                translate_manual.delay(manual_id)
            else:
                manual.status = ManualStatus.classified
                session.commit()
                # Sprint 3: Auto-trigger classification after file is processed
                try:
                    from app.tasks.classification import classify_manual
                    classify_manual.delay(manual_id)
                except Exception as cls_exc:
                    logger.warning("Failed to dispatch classify_manual for %s: %s", manual_id, cls_exc)

        except Exception as exc:
            logger.error("Format processing failed for manual %s: %s", manual_id, exc)
            manual.status = ManualStatus.failed
            manual.error_message = str(exc)
            session.commit()


def _detect_language(manual_id: str, blob_key: Optional[str]) -> str:
    """
    Detect document language using Azure Translator detect endpoint.
    Returns ISO 639-1 code. Falls back to 'en' if no API key is configured.
    """
    translator_key = settings.AZURE_TRANSLATOR_KEY
    if not translator_key:
        logger.debug(
            "AZURE_TRANSLATOR_KEY not set — skipping language detection, assuming 'en'"
        )
        return "en"

    sample_text = f"Document {manual_id}"  # In real usage: extract first N chars from file

    try:
        url = f"{settings.AZURE_TRANSLATOR_ENDPOINT}/detect"
        headers = {
            "Ocp-Apim-Subscription-Key": translator_key,
            "Content-Type": "application/json",
        }
        params = {"api-version": "3.0"}
        body = [{"Text": sample_text}]

        with httpx.Client(timeout=10) as client:
            resp = client.post(url, headers=headers, params=params, json=body)
            resp.raise_for_status()
            data = resp.json()
            return data[0].get("language", "en")

    except Exception as exc:
        logger.warning("Language detection failed: %s — defaulting to 'en'", exc)
        return "en"


# ---------------------------------------------------------------------------
# Task: translate_manual
# ---------------------------------------------------------------------------


@celery_app.task(
    name="app.tasks.ingestion.translate_manual",
)
def translate_manual(manual_id: str) -> None:
    """
    Translate manual content to English using Azure AI Translator.
    Stores translated content alongside original in blob storage.
    """
    with SyncSession() as session:
        manual = _get_manual(session, manual_id)
        if manual is None:
            logger.error("Manual %s not found for translation", manual_id)
            return

        manual.status = ManualStatus.translating
        session.commit()

        try:
            translator_key = settings.AZURE_TRANSLATOR_KEY

            if not translator_key:
                # Mock response when no API key is configured
                logger.info(
                    "AZURE_TRANSLATOR_KEY not set — mocking translation for manual %s",
                    manual_id,
                )
                _mock_store_translated(manual)
            else:
                _real_translate(manual, translator_key)

            manual.translated = True
            manual.status = ManualStatus.classified
            session.commit()

            # Sprint 3: Auto-trigger classification after translation
            try:
                from app.tasks.classification import classify_manual
                classify_manual.delay(manual_id)
            except Exception as cls_exc:
                logger.warning("Failed to dispatch classify_manual for %s: %s", manual_id, cls_exc)

        except Exception as exc:
            logger.error("Translation failed for manual %s: %s", manual_id, exc)
            manual.status = ManualStatus.failed
            manual.error_message = str(exc)
            session.commit()


def _mock_store_translated(manual: Manual) -> None:
    """Store a placeholder translated object in blob storage."""
    from app.services.blob_storage import BlobStorageService

    if not manual.blob_storage_key:
        return

    blob_service = BlobStorageService()
    translated_key = manual.blob_storage_key.rsplit("/", 1)
    translated_key_str = (
        translated_key[0] + "/translated_" + translated_key[1]
        if len(translated_key) == 2
        else manual.blob_storage_key + ".translated"
    )

    placeholder = (
        f"[MOCK TRANSLATION] Original language: {manual.detected_language}\n"
        f"File: {manual.original_filename}\n"
        "Translation would appear here with Azure AI Translator.\n"
    ).encode()

    import io

    blob_service.upload_stream_sync(
        translated_key_str, io.BytesIO(placeholder), "text/plain"
    )
    manual.blob_storage_key = translated_key_str


def _real_translate(manual: Manual, translator_key: str) -> None:
    """Call Azure AI Translator Document Translation API."""
    from app.services.blob_storage import BlobStorageService

    blob_service = BlobStorageService()

    if not manual.blob_storage_key:
        return

    source_stream = blob_service.get_object_stream(manual.blob_storage_key)
    source_bytes = b"".join(source_stream)
    # Extract text (simplified — real implementation would use Azure Document Intelligence)
    source_text = source_bytes.decode("utf-8", errors="replace")[:5000]

    url = f"{settings.AZURE_TRANSLATOR_ENDPOINT}/translate"
    headers = {
        "Ocp-Apim-Subscription-Key": translator_key,
        "Content-Type": "application/json",
    }
    params = {
        "api-version": "3.0",
        "from": manual.detected_language or "auto",
        "to": "en",
    }
    body = [{"Text": source_text}]

    with httpx.Client(timeout=30) as client:
        resp = client.post(url, headers=headers, params=params, json=body)
        resp.raise_for_status()
        data = resp.json()

    translated_text = data[0]["translations"][0]["text"]

    translated_key = (
        manual.blob_storage_key.rsplit("/", 1)[0]
        + "/translated_"
        + manual.blob_storage_key.rsplit("/", 1)[-1]
    )

    import io

    blob_service.upload_stream_sync(
        translated_key, io.BytesIO(translated_text.encode()), "text/plain"
    )
    manual.blob_storage_key = translated_key
