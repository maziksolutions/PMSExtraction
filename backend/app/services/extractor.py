from __future__ import annotations

import json
import logging
import os
import uuid
from typing import Any, Optional

import anthropic

from app.core.config import settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Default system prompts per extraction type
# ---------------------------------------------------------------------------

DEFAULT_PROMPTS: dict[str, dict] = {
    "component": {
        "system": (
            "You are a maritime PMS (Planned Maintenance System) data extraction specialist. "
            "Your task is to extract component information from ship technical manuals. "
            "Return ONLY a valid JSON array of component records. Each record must follow this schema:\n"
            "{\n"
            '  "group1": "string (top-level machinery group, e.g. Deck Machinery)",\n'
            '  "group2": "string (sub-group, e.g. Mooring Winches)",\n'
            '  "main_machinery": "string (e.g. Main Engine, Aux Engine, Cargo Pump)",\n'
            '  "component_name": "string (specific component name)",\n'
            '  "maker": "string or null",\n'
            '  "model": "string or null",\n'
            '  "serial_number": "string or null",\n'
            '  "specification": "string or null",\n'
            '  "is_critical": true/false,\n'
            '  "job_pages": "string page range or null",\n'
            '  "spare_pages": "string page range or null",\n'
            '  "source_page_number": integer or null,\n'
            '  "confidence_score": integer 0-100\n'
            "}\n"
            "Extract ALL components mentioned. If no components found, return []. "
            "Return ONLY the JSON array with no explanation or markdown."
        ),
        "user_template": "Extract all components from the following manual text:\n\n{text}",
    },
    "job": {
        "system": (
            "You are a maritime PMS (Planned Maintenance System) data extraction specialist. "
            "Your task is to extract maintenance job information from ship technical manuals. "
            "Return ONLY a valid JSON array of job records. Each record must follow this schema:\n"
            "{\n"
            '  "job_name": "string (descriptive maintenance job name)",\n'
            '  "job_code": "string or null",\n'
            '  "job_description": "string or null",\n'
            '  "safety_precaution": "string or null",\n'
            '  "frequency": integer or null,\n'
            '  "frequency_type": "daily|weekly|monthly|quarterly|half_yearly|yearly|running_hours or null",\n'
            '  "is_critical": true/false,\n'
            '  "source_page_number": integer or null,\n'
            '  "confidence_score": integer 0-100\n'
            "}\n"
            "Extract ALL maintenance jobs and intervals mentioned. If no jobs found, return []. "
            "Return ONLY the JSON array with no explanation or markdown."
        ),
        "user_template": "Extract all maintenance jobs from the following manual text:\n\n{text}",
    },
    "spare": {
        "system": (
            "You are a maritime PMS (Planned Maintenance System) data extraction specialist. "
            "Your task is to extract spare parts information from ship technical manuals. "
            "Return ONLY a valid JSON array of spare part records. Each record must follow this schema:\n"
            "{\n"
            '  "part_name": "string (spare part name)",\n'
            '  "part_number": "string or null",\n'
            '  "specification": "string or null",\n'
            '  "spare_maker": "string or null",\n'
            '  "spare_model": "string or null",\n'
            '  "source_page_number": integer or null,\n'
            '  "confidence_score": integer 0-100\n'
            "}\n"
            "Extract ALL spare parts listed. If no spares found, return []. "
            "Return ONLY the JSON array with no explanation or markdown."
        ),
        "user_template": "Extract all spare parts from the following manual text:\n\n{text}",
    },
}

# ---------------------------------------------------------------------------
# Core extraction function
# ---------------------------------------------------------------------------


async def extract_entities(
    text_chunk: str,
    extraction_type: str,
    filename: str,
    custom_prompt: str | None = None,
) -> list[dict]:
    """
    Call Claude to extract structured entities from a text chunk.

    Args:
        text_chunk: The manual text to process.
        extraction_type: One of "component", "job", "spare".
        filename: Source filename (used for logging).
        custom_prompt: Optional override for the system prompt.

    Returns:
        List of dicts parsed from Claude's JSON response, or [] on error.
    """
    model_id: str = getattr(settings, "CLAUDE_MODEL_ID", None) or "claude-sonnet-4-6"

    prompt_config = DEFAULT_PROMPTS.get(extraction_type, DEFAULT_PROMPTS["component"])
    system_prompt = custom_prompt or prompt_config["system"]
    user_message = prompt_config["user_template"].format(text=text_chunk)

    try:
        client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
        max_tokens = getattr(settings, "EXTRACTION_MAX_TOKENS", 8192)
        message = client.messages.create(
            model=model_id,
            max_tokens=max_tokens,
            system=system_prompt,
            messages=[{"role": "user", "content": user_message}],
        )

        raw_text: str = message.content[0].text.strip()

        # Strip markdown code fences if present
        if raw_text.startswith("```"):
            lines = raw_text.splitlines()
            # Remove opening fence (```json or ```)
            lines = lines[1:] if lines[0].startswith("```") else lines
            # Remove closing fence
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            raw_text = "\n".join(lines).strip()

        parsed: Any = json.loads(raw_text)
        if isinstance(parsed, list):
            return [r for r in parsed if isinstance(r, dict)]
        return []

    except json.JSONDecodeError as exc:
        logger.warning(
            "extract_entities: JSON parse error for %s/%s: %s",
            filename,
            extraction_type,
            exc,
        )
        return []
    except Exception as exc:
        logger.error(
            "extract_entities: unexpected error for %s/%s: %s",
            filename,
            extraction_type,
            exc,
        )
        return []


# ---------------------------------------------------------------------------
# Full-manual auto-extraction (background task)
# ---------------------------------------------------------------------------


async def auto_extract_from_manual(
    manual_id_str: str,
    vessel_id_str: str,
    tenant_id_str: str,
) -> None:
    """
    Background task: extract Components, Jobs, and Spares from a Manual.

    Opens its own DB session so it can run as a FastAPI BackgroundTask or
    directly from a Celery worker.
    """
    from app.core.database import AsyncSessionLocal
    from app.models.component import Component, QCStatus
    from app.models.ingestion import Manual, ManualStatus
    from app.models.job import FrequencyType, Job
    from app.models.spare import Spare
    from sqlalchemy import select, update

    manual_id = uuid.UUID(manual_id_str)
    vessel_id = uuid.UUID(vessel_id_str)
    tenant_id = uuid.UUID(tenant_id_str)

    async with AsyncSessionLocal() as db:
        # ------------------------------------------------------------------
        # Load the manual
        # ------------------------------------------------------------------
        result = await db.execute(
            select(Manual).where(
                Manual.id == manual_id,
                Manual.vessel_id == vessel_id,
                Manual.tenant_id == tenant_id,
                Manual.is_deleted == False,
            )
        )
        manual: Optional[Manual] = result.scalar_one_or_none()
        if manual is None:
            logger.warning("auto_extract_from_manual: manual %s not found", manual_id_str)
            return

        category: Optional[str] = manual.category
        if not category or category.strip().lower() in ("", "unknown/unclassifiable", "unknown"):
            logger.info(
                "auto_extract_from_manual: skipping manual %s — category=%r",
                manual_id_str,
                category,
            )
            return

        # ------------------------------------------------------------------
        # Mark as scanning
        # ------------------------------------------------------------------
        await db.execute(
            update(Manual)
            .where(Manual.id == manual_id)
            .values(status=ManualStatus.scanning)
        )
        await db.commit()

        # ------------------------------------------------------------------
        # Extract text from the actual file using pdfplumber
        # ------------------------------------------------------------------
        filename = manual.original_filename
        file_path = manual.blob_storage_key
        full_text = ""

        if file_path and os.path.exists(file_path):
            ext = (manual.file_extension or "").lower()
            if ext == "pdf":
                try:
                    import pdfplumber
                    with pdfplumber.open(file_path) as pdf:
                        pages_text = []
                        for page in pdf.pages:
                            t = page.extract_text()
                            if t:
                                pages_text.append(t)
                        full_text = "\n".join(pages_text)
                except Exception as pdf_err:
                    logger.warning("pdfplumber failed for %s: %s", filename, pdf_err)
            elif ext in ("docx",):
                try:
                    import docx
                    doc = docx.Document(file_path)
                    full_text = "\n".join(p.text for p in doc.paragraphs if p.text.strip())
                except Exception as docx_err:
                    logger.warning("docx extraction failed for %s: %s", filename, docx_err)

        if not full_text.strip():
            logger.warning("auto_extract_from_manual: no text extracted from %s, skipping", filename)
            return

        # Limit to first 80,000 characters to stay within Claude's context window
        MAX_CHARS = 80_000
        if len(full_text) > MAX_CHARS:
            full_text = full_text[:MAX_CHARS]

        # ------------------------------------------------------------------
        # Determine which entity types to extract based on category
        # ------------------------------------------------------------------
        norm_category = category.strip()
        if norm_category == "Instruction Manual":
            extraction_types = ["component", "job", "spare"]
        else:
            # Machinery Particulars and everything else → components only
            extraction_types = ["component"]

        # ------------------------------------------------------------------
        # Run extractions
        # ------------------------------------------------------------------
        components_to_add: list[Component] = []
        jobs_to_add: list[Job] = []
        spares_to_add: list[Spare] = []

        for etype in extraction_types:
            records = await extract_entities(full_text, etype, filename)

            for record in records:
                confidence = int(record.get("confidence_score", 70))
                source_page = record.get("source_page_number")

                if etype == "component":
                    comp = Component(
                        tenant_id=tenant_id,
                        vessel_id=vessel_id,
                        source_manual_id=manual.id,
                        confidence_score=confidence,
                        qc_status=QCStatus.pending,
                        group1=record.get("group1") or "Uncategorised",
                        group2=record.get("group2") or "Uncategorised",
                        main_machinery=record.get("main_machinery") or "Unknown",
                        component_name=record.get("component_name") or "Unknown Component",
                        maker=record.get("maker") or None,
                        model=record.get("model") or None,
                        serial_number=record.get("serial_number") or None,
                        specification=record.get("specification") or None,
                        is_critical=bool(record.get("is_critical", False)),
                        job_pages=record.get("job_pages") or None,
                        spare_pages=record.get("spare_pages") or None,
                        page_reference=int(source_page) if source_page is not None else None,
                    )
                    components_to_add.append(comp)

                elif etype == "job":
                    raw_freq_type = record.get("frequency_type")
                    freq_type: Optional[FrequencyType] = None
                    if raw_freq_type:
                        try:
                            freq_type = FrequencyType(raw_freq_type.lower())
                        except ValueError:
                            freq_type = None

                    raw_freq = record.get("frequency")
                    freq_val: Optional[int] = None
                    if raw_freq is not None:
                        try:
                            freq_val = int(raw_freq)
                        except (TypeError, ValueError):
                            freq_val = None

                    job = Job(
                        tenant_id=tenant_id,
                        vessel_id=vessel_id,
                        source_manual_id=manual.id,
                        confidence_score=confidence,
                        qc_status=QCStatus.pending,
                        job_name=record.get("job_name") or "Unknown Job",
                        job_code=record.get("job_code") or None,
                        job_description=record.get("job_description") or None,
                        safety_precaution=record.get("safety_precaution") or None,
                        frequency=freq_val,
                        frequency_type=freq_type,
                        is_critical=bool(record.get("is_critical", False)),
                        page_reference=int(source_page) if source_page is not None else None,
                    )
                    jobs_to_add.append(job)

                elif etype == "spare":
                    spare = Spare(
                        tenant_id=tenant_id,
                        vessel_id=vessel_id,
                        source_manual_id=manual.id,
                        confidence_score=confidence,
                        qc_status=QCStatus.pending,
                        part_name=record.get("part_name") or "Unknown Part",
                        part_number=record.get("part_number") or None,
                        specification=record.get("specification") or None,
                        spare_maker=record.get("spare_maker") or None,
                        spare_model=record.get("spare_model") or None,
                        page_reference=int(source_page) if source_page is not None else None,
                    )
                    spares_to_add.append(spare)

        # ------------------------------------------------------------------
        # Persist all records
        # ------------------------------------------------------------------
        for obj in [*components_to_add, *jobs_to_add, *spares_to_add]:
            db.add(obj)

        # ------------------------------------------------------------------
        # Restore manual status to classified
        # ------------------------------------------------------------------
        await db.execute(
            update(Manual)
            .where(Manual.id == manual_id)
            .values(status=ManualStatus.classified)
        )

        await db.commit()

        logger.info(
            "auto_extract_from_manual: manual=%s → %d components, %d jobs, %d spares",
            manual_id_str,
            len(components_to_add),
            len(jobs_to_add),
            len(spares_to_add),
        )
