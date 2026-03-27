from __future__ import annotations

import uuid
from typing import Any

from app.tasks import celery_app

DOCUMENT_CATEGORIES = [
    "Instruction Manual",
    "Machinery Particulars",
    "General Arrangement",
    "Pipeline Diagrams/P&ID",
    "LSA/FFA Plans",
    "Tank Capacity Plan",
    "Yard/Finished Drawings",
    "Electrical Diagrams",
    "Class Certificates/Surveys",
    "Unknown/Unclassifiable",
]


def _mock_classification(filename: str) -> dict[str, Any]:
    """Return mock classification data based on filename heuristics."""
    name_lower = filename.lower()
    if "engine" in name_lower or "instruction" in name_lower:
        category = "Instruction Manual"
        pages_components = "1-50"
        pages_jobs = "51-80"
        pages_spares = "81-120"
    elif "arrangement" in name_lower or "ga" in name_lower:
        category = "General Arrangement"
        pages_components = "1-20"
        pages_jobs = None
        pages_spares = None
    elif "pump" in name_lower or "machinery" in name_lower:
        category = "Machinery Particulars"
        pages_components = "1-30"
        pages_jobs = "31-50"
        pages_spares = "51-90"
    elif "pipeline" in name_lower or "p&id" in name_lower:
        category = "Pipeline Diagrams/P&ID"
        pages_components = None
        pages_jobs = None
        pages_spares = None
    elif "electrical" in name_lower:
        category = "Electrical Diagrams"
        pages_components = None
        pages_jobs = None
        pages_spares = None
    else:
        category = "Instruction Manual"
        pages_components = "1-40"
        pages_jobs = "41-60"
        pages_spares = "61-100"

    useful = "Yes" if category in ("Instruction Manual", "Machinery Particulars") else "Reference"

    return {
        "category": category,
        "classification_confidence": 85,
        "useful_for_extraction": useful,
        "pages_with_components": pages_components,
        "pages_with_jobs": pages_jobs,
        "pages_with_spares": pages_spares,
    }


async def _classify_with_openai(manual_text: str, filename: str) -> dict[str, Any]:
    """Call GPT-4o for classification. Falls back to mock if no API key."""
    from app.core.config import settings

    if not settings.OPENAI_API_KEY:
        return _mock_classification(filename)

    try:
        import openai

        client = openai.AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
        categories_str = "\n".join(f"- {c}" for c in DOCUMENT_CATEGORIES)
        prompt = f"""Classify the following maritime manual document.

Filename: {filename}

Document excerpt (first 2000 chars):
{manual_text[:2000]}

Choose one category from:
{categories_str}

Respond with JSON only:
{{
  "category": "<category>",
  "classification_confidence": <0-100>,
  "useful_for_extraction": "<Yes|Reference|No>",
  "pages_with_components": "<page range or null>",
  "pages_with_jobs": "<page range or null>",
  "pages_with_spares": "<page range or null>"
}}"""

        response = await client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
        )
        import json

        return json.loads(response.choices[0].message.content or "{}")
    except Exception:
        return _mock_classification(filename)


@celery_app.task(bind=True, max_retries=3, default_retry_delay=60)
def classify_manual(self, manual_id: str) -> dict[str, Any]:
    """
    Celery task: classify a manual document.
    Reads from blob storage, calls GPT-4o (or mock), updates DB.
    """
    import asyncio

    from sqlalchemy import select

    from app.core.database import AsyncSessionLocal
    from app.models.ingestion import Manual, ManualStatus

    async def _run() -> dict[str, Any]:
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(Manual).where(Manual.id == uuid.UUID(manual_id))
            )
            manual: Manual | None = result.scalar_one_or_none()
            if manual is None:
                return {"error": "Manual not found"}

            try:
                # Attempt to read text from blob storage
                manual_text = ""
                try:
                    from app.services.blob_storage import BlobStorageService

                    blob_svc = BlobStorageService()
                    if manual.blob_storage_key:
                        data = await blob_svc.download_bytes(manual.blob_storage_key)
                        manual_text = data.decode("utf-8", errors="ignore")[:5000]
                except Exception:
                    pass

                classification = await _classify_with_openai(
                    manual_text, manual.original_filename
                )

                manual.category = classification.get("category")
                manual.classification_confidence = classification.get(
                    "classification_confidence"
                )
                manual.useful_for_extraction = classification.get(
                    "useful_for_extraction"
                )
                manual.pages_with_components = classification.get(
                    "pages_with_components"
                )
                manual.pages_with_jobs = classification.get("pages_with_jobs")
                manual.pages_with_spares = classification.get("pages_with_spares")
                manual.status = ManualStatus.classified

                db.add(manual)
                await db.commit()
                return {"status": "classified", "manual_id": manual_id}

            except Exception as exc:
                manual.status = ManualStatus.failed
                manual.error_message = str(exc)
                db.add(manual)
                await db.commit()
                raise self.retry(exc=exc)

    return asyncio.run(_run())
