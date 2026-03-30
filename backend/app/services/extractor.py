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
            "You are an expert maritime PMS (Planned Maintenance System) data extraction specialist "
            "with deep knowledge of ship machinery, equipment nomenclature, and maintenance systems.\n\n"
            "The document may be a MACHINERY LIST/REGISTER (tabular, one row per equipment item) "
            "or a TECHNICAL MANUAL (prose with descriptions of one piece of equipment). "
            "Extract ALL equipment entries regardless of format — do not miss any rows.\n\n"
            "MACHINERY LIST format: Each table row is ONE component. "
            "Typical columns: No. | Equipment/Description | Maker/Manufacturer | Type/Model | Serial No. | Capacity/Rating | Location.\n\n"
            "TECHNICAL MANUAL format: The manual itself describes one main piece of equipment. "
            "Extract the main equipment plus any sub-components or assemblies mentioned.\n\n"
            "GROUP CLASSIFICATION GUIDE (use these exact values where applicable):\n"
            "  group1 options: Propulsion | Deck Machinery | Auxiliary Machinery | Hull Equipment | "
            "Navigation & Communication | Safety Equipment | Cargo Handling | Hotel/Accommodation\n"
            "  group2 examples: Main Engine | Auxiliary Engine | Boiler | Steering Gear | "
            "Anchor/Mooring | Cargo Pump | Ballast System | Fire Fighting | HVAC | Lifesaving\n\n"
            "Return ONLY a valid JSON array. Each record:\n"
            "{\n"
            '  "group1": "top-level machinery group",\n'
            '  "group2": "machinery sub-group",\n'
            '  "main_machinery": "the main machinery system this component belongs to",\n'
            '  "component_name": "exact name from the document — do not paraphrase",\n'
            '  "maker": "manufacturer/maker name or null",\n'
            '  "model": "model/type number or null",\n'
            '  "serial_number": "serial or hull number or null",\n'
            '  "specification": "capacity, power, flow rate, pressure, kW, rpm, or key specs — be specific, or null",\n'
            '  "is_critical": true if propulsion/steering/power generation/fire/safety equipment, false otherwise,\n'
            '  "job_pages": null,\n'
            '  "spare_pages": null,\n'
            '  "source_page_number": integer page number or null,\n'
            '  "confidence_score": integer 70-98\n'
            "}\n\n"
            "STRICT RULES:\n"
            "- Extract EVERY equipment row — skipping rows is the most common error, do not do it\n"
            "- Fill maker and model whenever those columns exist in the table\n"
            "- specification must capture numeric ratings (e.g. '500 kW', '200 m³/h at 4 bar') not generic descriptions\n"
            "- If the table has section headers (e.g. 'PROPULSION', 'DECK EQUIPMENT'), use them for group1/group2\n"
            "- Do not invent data — use null when information is absent\n"
            "- Return ONLY the JSON array, no explanation, no markdown fences"
        ),
        "user_template": (
            "Extract every machinery and equipment entry from this maritime document. "
            "This is either a machinery list (extract every table row) or a technical manual "
            "(extract the main equipment and all sub-components mentioned).\n\n{text}"
        ),
    },
    "job": {
        "system": (
            "You are an expert maritime PMS (Planned Maintenance System) data extraction specialist.\n\n"
            "Extract ALL maintenance jobs, service intervals, and inspection tasks from this ship technical manual. "
            "Maintenance schedules often appear in tables with columns like: Job | Interval | Running Hours | Remarks.\n\n"
            "FREQUENCY TYPE MAPPING:\n"
            "  - Daily / 24h → 'daily'\n"
            "  - Weekly / 7 days → 'weekly'\n"
            "  - Monthly / 4 weeks / 30 days → 'monthly'\n"
            "  - 3 months / quarterly → 'quarterly'\n"
            "  - 6 months / half yearly → 'half_yearly'\n"
            "  - 12 months / annually / yearly → 'yearly'\n"
            "  - Running hours (e.g. every 500 h, 1000 h, 4000 h) → 'running_hours'\n\n"
            "Return ONLY a valid JSON array. Each record:\n"
            "{\n"
            '  "job_name": "concise descriptive name (e.g. \'Replace lube oil filter\', \'Inspect fuel injectors\')",\n'
            '  "job_code": "job code/number from the manual or null",\n'
            '  "job_description": "detailed procedure description or null",\n'
            '  "safety_precaution": "safety warnings or precautions mentioned or null",\n'
            '  "frequency": integer value (e.g. 500 for every 500 running hours, 6 for 6-monthly) or null,\n'
            '  "frequency_type": "daily|weekly|monthly|quarterly|half_yearly|yearly|running_hours or null",\n'
            '  "is_critical": true if the job relates to propulsion, steering, safety, or regulatory compliance, false otherwise,\n'
            '  "source_page_number": integer page number or null,\n'
            '  "confidence_score": integer 70-98\n'
            "}\n\n"
            "RULES:\n"
            "- Extract every distinct job/interval — do not merge different jobs into one\n"
            "- For running hours jobs, frequency = the hour value (e.g. 500, 1000, 4000)\n"
            "- Include safety precautions when explicitly stated in the manual\n"
            "- If no maintenance jobs are found, return []\n"
            "- Return ONLY the JSON array, no explanation, no markdown fences"
        ),
        "user_template": (
            "Extract all maintenance jobs, service intervals, and inspection tasks "
            "from this ship technical manual:\n\n{text}"
        ),
    },
    "spare": {
        "system": (
            "You are an expert maritime PMS (Planned Maintenance System) data extraction specialist.\n\n"
            "Extract ALL spare parts, recommended spares, and consumables from this ship technical manual. "
            "Spare parts lists typically appear as tables with columns like: "
            "Item No. | Part Name | Part Number | Quantity | Remarks.\n\n"
            "Return ONLY a valid JSON array. Each record:\n"
            "{\n"
            '  "part_name": "exact part name from the document",\n'
            '  "part_number": "manufacturer part number or catalog number or null",\n'
            '  "specification": "size, material, rating, quantity, or relevant spec or null",\n'
            '  "spare_maker": "manufacturer of this spare part or null",\n'
            '  "spare_model": "model or type designation this spare fits or null",\n'
            '  "source_page_number": integer page number or null,\n'
            '  "confidence_score": integer 70-98\n'
            "}\n\n"
            "RULES:\n"
            "- Extract EVERY spare part row from all spare parts tables\n"
            "- Include part numbers exactly as they appear (do not reformat)\n"
            "- specification should capture quantity, material, size where listed\n"
            "- If no spare parts are found, return []\n"
            "- Return ONLY the JSON array, no explanation, no markdown fences"
        ),
        "user_template": (
            "Extract all spare parts, recommended spares, and consumables "
            "from this ship technical manual:\n\n{text}"
        ),
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
        client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
        max_tokens = getattr(settings, "EXTRACTION_MAX_TOKENS", 8192)
        message = await client.messages.create(
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
        # Get text: use stored DB text first, fall back to reading file
        # ------------------------------------------------------------------
        filename = manual.original_filename
        file_path = manual.blob_storage_key
        full_text = ""

        # Primary source: text extracted at upload time and persisted in DB
        if getattr(manual, "extracted_text", None):
            full_text = manual.extracted_text  # type: ignore[assignment]

        # Fallback: re-read from disk if DB text is missing (e.g. older records)
        if not full_text and file_path and os.path.exists(file_path):
            ext = (manual.file_extension or "").lower()
            if ext == "pdf":
                try:
                    import asyncio as _asyncio
                    import pdfplumber

                    def _read_pdf(path: str) -> str:
                        parts: list[str] = []
                        with pdfplumber.open(path) as pdf:
                            for page_num, page in enumerate(pdf.pages, start=1):
                                # Extract prose text
                                text = page.extract_text()
                                if text and text.strip():
                                    parts.append(text)
                                # Also extract tables (machinery lists are mostly tables)
                                try:
                                    tables = page.extract_tables()
                                    for table in (tables or []):
                                        if not table:
                                            continue
                                        rows = []
                                        for row in table:
                                            if row and any(cell for cell in row if cell):
                                                rows.append(" | ".join(
                                                    str(cell).strip() if cell else ""
                                                    for cell in row
                                                ))
                                        if rows:
                                            parts.append(
                                                f"[TABLE page {page_num}]\n" + "\n".join(rows)
                                            )
                                except Exception:
                                    pass
                        return "\n\n".join(parts)

                    full_text = await _asyncio.to_thread(_read_pdf, file_path)
                except Exception as pdf_err:
                    logger.warning("pdfplumber failed for %s: %s", filename, pdf_err)
            elif ext in ("docx",):
                try:
                    import asyncio as _asyncio
                    import docx

                    def _read_docx(path: str) -> str:
                        doc = docx.Document(path)
                        return "\n".join(p.text for p in doc.paragraphs if p.text.strip())

                    full_text = await _asyncio.to_thread(_read_docx, file_path)
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
