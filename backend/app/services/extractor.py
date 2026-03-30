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
            "The text contains [PAGE N] markers — use these numbers for source_page_number.\n\n"
            "DOCUMENT TYPES — handle all of these:\n\n"
            "1. MACHINERY LIST / REGISTER (tabular, one row = one component)\n"
            "   Columns: No. | Equipment | Maker | Model/Type | Serial No. | Capacity | Location\n"
            "   → Extract EVERY row. Use table section headers for group1/group2.\n\n"
            "2. SINGLE-EQUIPMENT SPECIFICATION SHEET (title names ONE main piece of equipment)\n"
            "   The maker and model are usually in the document TITLE or first heading.\n"
            "   → Extract the MAIN EQUIPMENT as one component (take maker from the title/heading).\n"
            "   → Extract each explicitly named SUB-ASSEMBLY or sub-component as a separate component\n"
            "     (e.g. Blower, Motor, Pump, Compressor, Valve, Controller, Heat Exchanger — if named).\n"
            "   → Do NOT create a component for every spec row (Type, Capacity, Source, etc.) —\n"
            "     only create components for physical equipment/assemblies.\n"
            "   → Use the specification field to capture the key ratings (kW, rpm, capacity, m³, bar).\n\n"
            "3. TANK CAPACITY PLAN (each row is one tank)\n"
            "   → component_name = tank name, specification = capacity in m³ or tonnes,\n"
            "     group1 = 'Tanks & Capacities', group2 = tank category.\n\n"
            "GROUP CLASSIFICATION GUIDE:\n"
            "  group1: Propulsion | Deck Machinery | Auxiliary Machinery | Hull Equipment | "
            "Navigation & Communication | Safety Equipment | Cargo Handling | Hotel/Accommodation | Tanks & Capacities\n"
            "  group2 examples: Main Engine | Auxiliary Engine | Boiler | Steering Gear | "
            "Sewage Treatment | Fresh Water System | Ballast System | Fire Fighting | HVAC | "
            "Fuel Oil System | Air System | Lifesaving | Cargo Pump | Anchor/Mooring\n\n"
            "Return ONLY a valid JSON array. Each record:\n"
            "{\n"
            '  "group1": "top-level machinery group",\n'
            '  "group2": "machinery sub-group",\n'
            '  "main_machinery": "the main equipment this component belongs to or IS",\n'
            '  "component_name": "exact name — for main equipment use the full name from the title",\n'
            '  "maker": "manufacturer name — check document title, header, and Name Plate rows; null if absent",\n'
            '  "model": "model/type number — check Type rows and document title; null if absent",\n'
            '  "serial_number": "serial number or null",\n'
            '  "specification": "key ratings: power (kW), capacity (m³/h), pressure (bar), rpm, etc. — be specific; null if absent",\n'
            '  "is_critical": true if propulsion/steering/power generation/fire/safety/sewage treatment equipment,\n'
            '  "job_pages": null,\n'
            '  "spare_pages": null,\n'
            '  "source_page_number": integer — the [PAGE N] number where this component appears,\n'
            '  "confidence_score": integer 70-98\n'
            "}\n\n"
            "STRICT RULES:\n"
            "- source_page_number MUST come from the [PAGE N] marker in the text — do not guess\n"
            "- For specification sheets: maker comes from the TITLE / HEADER (e.g. 'TAIKO Ship-Clean' → maker='Taiko')\n"
            "- For specification sheets: model comes from Type row (e.g. 'Type: SBH-25' → model='SBH-25')\n"
            "- Fill maker and model whenever those columns or rows exist\n"
            "- specification must capture numeric ratings not generic text\n"
            "- Do not invent data — null when genuinely absent\n"
            "- Return ONLY the JSON array, no explanation, no markdown fences"
        ),
        "user_template": (
            "Document: {filename}\n\n"
            "Extract every piece of physical equipment and machinery from this maritime document. "
            "The text contains [PAGE N] markers — use them for source_page_number.\n"
            "If this is a specification sheet for one equipment, extract the main equipment (maker from the title) "
            "and any named sub-assemblies (motors, blowers, pumps, etc.).\n"
            "If this is a machinery list, extract every table row.\n\n"
            "{text}"
        ),
    },
    "job": {
        "system": (
            "You are an expert maritime PMS (Planned Maintenance System) data extraction specialist.\n\n"
            "The text contains [PAGE N] markers — use these numbers for source_page_number.\n\n"
            "Extract ALL maintenance jobs, service intervals, and inspection tasks. "
            "Maintenance schedules appear as tables (Job | Interval | Running Hours | Remarks) "
            "or as numbered procedure lists with frequencies.\n\n"
            "FREQUENCY TYPE MAPPING:\n"
            "  Daily / 24h → 'daily'\n"
            "  Weekly / 7 days → 'weekly'\n"
            "  Monthly / 30 days → 'monthly'\n"
            "  3 months / quarterly → 'quarterly'\n"
            "  6 months / half yearly → 'half_yearly'\n"
            "  12 months / annually → 'yearly'\n"
            "  Running hours (e.g. every 500 h, 1000 h) → 'running_hours', frequency = the hour value\n\n"
            "Return ONLY a valid JSON array. Each record:\n"
            "{\n"
            '  "job_name": "concise name (e.g. \'Replace lube oil filter\', \'Inspect anode\')",\n'
            '  "job_code": "job code/number from manual or null",\n'
            '  "job_description": "procedure detail or null",\n'
            '  "safety_precaution": "safety warnings or null",\n'
            '  "frequency": integer or null,\n'
            '  "frequency_type": "daily|weekly|monthly|quarterly|half_yearly|yearly|running_hours or null",\n'
            '  "is_critical": true if propulsion/steering/safety/regulatory,\n'
            '  "source_page_number": integer from [PAGE N] marker or null,\n'
            '  "confidence_score": integer 70-98\n'
            "}\n\n"
            "RULES:\n"
            "- source_page_number from [PAGE N] markers — do not guess\n"
            "- Extract every distinct job — do not merge different tasks\n"
            "- If no maintenance jobs exist, return []\n"
            "- Return ONLY the JSON array, no markdown fences"
        ),
        "user_template": (
            "Document: {filename}\n\n"
            "Extract all maintenance jobs, service intervals, and inspection tasks. "
            "Use [PAGE N] markers for source_page_number.\n\n{text}"
        ),
    },
    "spare": {
        "system": (
            "You are an expert maritime PMS (Planned Maintenance System) data extraction specialist.\n\n"
            "The text contains [PAGE N] markers — use these numbers for source_page_number.\n\n"
            "Extract ALL spare parts, recommended spares, and consumables. "
            "Spare parts lists appear as tables with columns like:\n"
            "  Item No. | Part Name | Part Number | Drawing No. | Qty | Remarks\n"
            "They may also appear as numbered lists under headings like 'Recommended Spare Parts' or 'Spare Parts List'.\n\n"
            "Return ONLY a valid JSON array. Each record:\n"
            "{\n"
            '  "part_name": "exact part name from the document",\n'
            '  "part_number": "part/catalog number exactly as printed or null",\n'
            '  "drawing_number": "drawing or diagram reference number or null",\n'
            '  "drawing_position": "item/position number on the drawing or null",\n'
            '  "specification": "size, material, quantity, standard (e.g. JIS, ISO), or rating — or null",\n'
            '  "spare_maker": "manufacturer — infer from document maker if not explicit (e.g. if doc is a Taiko manual, spare_maker=Taiko); null only if truly unknown",\n'
            '  "spare_model": "model or equipment type this spare fits or null",\n'
            '  "source_page_number": integer from [PAGE N] marker or null,\n'
            '  "confidence_score": integer 70-98\n'
            "}\n\n"
            "RULES:\n"
            "- source_page_number from [PAGE N] markers only\n"
            "- Extract EVERY row from spare parts tables — never skip rows\n"
            "- Part numbers: include exactly as printed (do not reformat)\n"
            "- spare_maker: if the manual is for one specific maker (e.g. 'TAIKO Ship-Clean'), "
            "  set spare_maker to that maker for all parts unless a different maker is stated\n"
            "- If no spare parts found, return []\n"
            "- Return ONLY the JSON array, no markdown fences"
        ),
        "user_template": (
            "Document: {filename}\n\n"
            "Extract all spare parts, recommended spares, and consumables. "
            "Use [PAGE N] markers for source_page_number.\n\n{text}"
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
    user_message = prompt_config["user_template"].format(text=text_chunk, filename=filename)

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


async def auto_extract_from_manual(manual_id_str: str) -> None:
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

    async with AsyncSessionLocal() as db:
        # ------------------------------------------------------------------
        # Load the manual (vessel_id and tenant_id come from the record itself)
        # ------------------------------------------------------------------
        result = await db.execute(
            select(Manual).where(
                Manual.id == manual_id,
                Manual.is_deleted == False,
            )
        )
        manual: Optional[Manual] = result.scalar_one_or_none()
        if manual is None:
            logger.warning("auto_extract_from_manual: manual %s not found", manual_id_str)
            return

        vessel_id = manual.vessel_id
        tenant_id = manual.tenant_id

        # Load vessel for shipyard fallback
        from app.models.vessel import VesselProject
        vessel_result = await db.execute(
            select(VesselProject).where(
                VesselProject.id == vessel_id,
                VesselProject.is_deleted == False,
            )
        )
        vessel_obj = vessel_result.scalar_one_or_none()
        vessel_shipyard = getattr(vessel_obj, "shipyard", None) or None

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
        # Get text with [PAGE N] markers.
        # Use stored DB text if it already has markers; otherwise re-extract
        # from blob storage (handles both old records and blob-stored files).
        # ------------------------------------------------------------------
        filename = manual.original_filename
        file_path = manual.blob_storage_key
        full_text = ""

        stored_text = getattr(manual, "extracted_text", None) or ""
        if stored_text and "[PAGE " in stored_text:
            # Already has page markers — use as-is
            full_text = stored_text
            logger.info("auto_extract_from_manual: using stored extracted_text for %s", filename)
        else:
            # Need to (re-)extract: try blob storage first, then local disk
            file_bytes: Optional[bytes] = None
            ext = (manual.file_extension or "").lower()

            # Try blob storage (MinIO / Azure)
            is_local_path = file_path and (
                file_path.startswith("/") or (len(file_path) > 1 and file_path[1] == ":")
            )
            if file_path and not is_local_path:
                try:
                    from app.services.blob_storage import BlobStorageService
                    blob_svc = BlobStorageService()
                    file_bytes = await blob_svc.download_bytes(file_path)
                    logger.info(
                        "auto_extract_from_manual: downloaded %d bytes from blob for %s",
                        len(file_bytes), filename,
                    )
                except Exception as blob_err:
                    logger.warning(
                        "auto_extract_from_manual: blob download failed for %s: %s", filename, blob_err
                    )

            # Fallback to local disk
            if file_bytes is None and file_path and os.path.exists(file_path):
                with open(file_path, "rb") as fh:
                    file_bytes = fh.read()

            if file_bytes is not None:
                if ext == "pdf":
                    try:
                        import asyncio as _asyncio
                        import pdfplumber
                        import io as _io

                        def _read_pdf_bytes(data: bytes) -> str:
                            parts: list[str] = []
                            with pdfplumber.open(_io.BytesIO(data)) as pdf:
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
                                    if page_parts:
                                        parts.append(f"[PAGE {page_num}]\n" + "\n".join(page_parts))
                            return "\n\n".join(parts)

                        full_text = await _asyncio.to_thread(_read_pdf_bytes, file_bytes)
                        # Persist the freshly-extracted text so future calls are instant
                        if full_text:
                            await db.execute(
                                update(Manual)
                                .where(Manual.id == manual_id)
                                .values(extracted_text=full_text)
                            )
                            await db.commit()
                    except Exception as pdf_err:
                        logger.warning("pdfplumber failed for %s: %s", filename, pdf_err)
                elif ext == "docx":
                    try:
                        import asyncio as _asyncio
                        import docx
                        import io as _io

                        def _read_docx_bytes(data: bytes) -> str:
                            doc = docx.Document(_io.BytesIO(data))
                            return "\n".join(p.text for p in doc.paragraphs if p.text.strip())

                        full_text = await _asyncio.to_thread(_read_docx_bytes, file_bytes)
                    except Exception as docx_err:
                        logger.warning("docx extraction failed for %s: %s", filename, docx_err)
            elif stored_text:
                # Last resort: use stored text even without page markers
                full_text = stored_text
                logger.warning(
                    "auto_extract_from_manual: using stored text without [PAGE] markers for %s", filename
                )

        if not full_text.strip():
            logger.warning("auto_extract_from_manual: no text extracted from %s, skipping", filename)
            return

        # ------------------------------------------------------------------
        # Determine which entity types to extract based on category and
        # classifier signals (pages_with_spares / pages_with_jobs)
        # ------------------------------------------------------------------
        norm_category = category.strip()
        extraction_types: list[str] = ["component"]  # always extract components

        has_spares_signal = bool(getattr(manual, "pages_with_spares", None))
        has_jobs_signal = bool(getattr(manual, "pages_with_jobs", None))

        if norm_category == "Instruction Manual":
            # Full instruction manuals always contain jobs + spares
            extraction_types = ["component", "job", "spare"]
        elif has_jobs_signal:
            extraction_types.append("job")
            if has_spares_signal:
                extraction_types.append("spare")
        elif has_spares_signal:
            extraction_types.append("spare")

        # ------------------------------------------------------------------
        # Chunk the full text so every page is processed.
        # Claude claude-sonnet-4-6 has a 200k token context window.
        # 120,000 chars ≈ 30,000 tokens — leaves ample room for system
        # prompt and a large JSON response.
        # ------------------------------------------------------------------
        CHUNK_SIZE = 120_000
        OVERLAP = 2_000  # small overlap to avoid cutting mid-table

        def _chunk_text(text: str) -> list[str]:
            if len(text) <= CHUNK_SIZE:
                return [text]
            chunks: list[str] = []
            start = 0
            while start < len(text):
                end = min(start + CHUNK_SIZE, len(text))
                chunks.append(text[start:end])
                start = end - OVERLAP
            return chunks

        text_chunks = _chunk_text(full_text)
        logger.info(
            "auto_extract_from_manual: %s → %d chars, %d chunk(s)",
            filename, len(full_text), len(text_chunks),
        )

        # ------------------------------------------------------------------
        # Run extractions across all chunks
        # ------------------------------------------------------------------
        components_to_add: list[Component] = []
        jobs_to_add: list[Job] = []
        spares_to_add: list[Spare] = []

        for etype in extraction_types:
            all_records: list[dict] = []
            for chunk_idx, chunk in enumerate(text_chunks):
                chunk_label = f"{filename} [chunk {chunk_idx + 1}/{len(text_chunks)}]"
                records = await extract_entities(chunk, etype, chunk_label)
                all_records.extend(records)

            # Deduplicate components by name (case-insensitive) to avoid
            # duplicates from the overlap region between chunks
            if etype == "component" and len(text_chunks) > 1:
                seen: set[str] = set()
                deduped: list[dict] = []
                for r in all_records:
                    key = (r.get("component_name") or "").strip().lower()
                    if key and key not in seen:
                        seen.add(key)
                        deduped.append(r)
                    elif not key:
                        deduped.append(r)
                all_records = deduped

            records = all_records

            for record in records:
                confidence = int(record.get("confidence_score", 70))
                source_page = record.get("source_page_number")

                if etype == "component":
                    _maker = record.get("maker") or None
                    _model = record.get("model") or None
                    # For components without maker info, use shipyard as maker
                    if not _maker and vessel_shipyard:
                        _maker = vessel_shipyard
                    if not _model and _maker:
                        _model = "N/A"
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
                        maker=_maker,
                        model=_model,
                        serial_number=record.get("serial_number") or None,
                        specification=record.get("specification") or None,
                        is_critical=bool(record.get("is_critical", False)),
                        job_pages=record.get("job_pages") or None,
                        spare_pages=record.get("spare_pages") or None,
                        page_reference=int(source_page) if source_page is not None else None,
                        pdf_reference=filename,
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
                        drawing_number=record.get("drawing_number") or None,
                        drawing_position=record.get("drawing_position") or None,
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

        # Auto-merge extracted components into matching library components
        try:
            from app.services.component_matcher import auto_merge_extracted_components
            merged, unmatched = await auto_merge_extracted_components(
                db=db,
                vessel_id=vessel_id,
                tenant_id=tenant_id,
            )
            logger.info(
                "auto_extract_from_manual: auto-merge vessel=%s merged=%d unmatched=%d",
                vessel_id_str, merged, unmatched,
            )
        except Exception as merge_exc:
            logger.warning("auto_extract_from_manual: auto-merge failed: %s", merge_exc)
