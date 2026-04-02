from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import uuid
from difflib import SequenceMatcher
from typing import Any, Optional

import anthropic

from app.core.config import settings

logger = logging.getLogger(__name__)


class ExtractionProvidersFailed(RuntimeError):
    """Raised when all configured extraction providers fail for a chunk."""

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
            "   These have a title like 'TAIKO SHIP-CLEAN SEWAGE TREATMENT PLANT SPECIFICATION'\n"
            "   and rows like: Type | SBH-25 | Quantity | 1 set/ship\n"
            "   EXTRACTION RULES for spec sheets:\n"
            "   → MAIN EQUIPMENT: extract as one component.\n"
            "     - maker = company name from the title or footer (e.g. 'TAIKO KIKAI INDUSTRIES CO.,LTD.' → 'Taiko Kikai')\n"
            "     - model = Type value (e.g. 'SBH-25')\n"
            "     - specification = key ratings: capacity (m³/h or persons/day), power (kW), pressure (bar), BOD/TSS limits\n"
            "   → SUB-ASSEMBLIES: for each named sub-system with its own Type number, extract a separate component:\n"
            "     e.g. 'Discharge Pump' → component_name='Discharge Pump', model='CF-50S', spec='4m³/h×20m, 1.5kW'\n"
            "          'Aeration Blower' → component_name='Aeration Blower', model='TSS-25', spec='2550/min×0.015MPa, 0.4kW'\n"
            "   → Do NOT create a component for spec rows that are just ratings (BOD Volume, Capacity, Pressure).\n"
            "   → Use the specification field for numeric ratings (kW, rpm, capacity, m³, bar, persons/day).\n\n"
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
            '  "location": "physical location or sets installed (e.g. Engine Room, 2 sets) — from Location or Installed column; null if absent",\n'
            '  "machinery_particulars": "machinery particulars document reference or list number — from MP No. or similar column; null if absent",\n'
            '  "specification": "key ratings: power (kW), capacity (m³/h), pressure (bar), rpm, etc. — be specific; null if absent",\n'
            '  "is_critical": true if propulsion/steering/power generation/fire/safety/sewage treatment equipment,\n'
            '  "job_pages": "page range in THIS document containing maintenance jobs/schedules for this component '
            '(e.g. \'45-67\'). Scan for sections titled Maintenance, Service Schedule, Inspection Intervals, '
            'Periodic Maintenance. If the whole document is a maintenance manual, give the full page range. '
            'null only if no maintenance section exists in this document",\n'
            '  "spare_pages": "page range in THIS document containing spare parts for this component '
            '(e.g. \'81-120\'). Scan for sections titled Spare Parts, Recommended Spares, Parts List, '
            'Spare Part Catalogue. null only if no spare parts section exists in this document",\n'
            '  "source_page_number": integer — the [PAGE N] number where this component appears,\n'
            '  "confidence_score": integer 70-98\n'
            "}\n\n"
            "STRICT RULES:\n"
            "- source_page_number MUST come from the [PAGE N] marker in the text — do not guess\n"
            "- job_pages / spare_pages: scan the document headings and identify where maintenance and spare-parts\n"
            "  sections begin and end; express as 'start-end' page range (e.g. '45-67'). ALL components from the\n"
            "  same document share the same job_pages and spare_pages if the document is for one equipment.\n"
            "  Set null ONLY if the document contains no such section at all (e.g. a pure machinery register).\n"
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
            "If this is a machinery list, extract every table row including location and machinery particulars reference if present.\n\n"
            "IMPORTANT — for job_pages and spare_pages:\n"
            "Scan the document for sections containing maintenance schedules or spare parts lists.\n"
            "If you find a maintenance/service section, record its page range as job_pages (e.g. '45-67').\n"
            "If you find a spare parts/recommended spares section, record its page range as spare_pages (e.g. '81-120').\n"
            "All components from the same single-equipment document share the same job_pages and spare_pages.\n"
            "Only set null if that section genuinely does not exist in this document.\n\n"
            "{text}"
        ),
    },
    "job": {
        "system": (
            "You are an expert maritime PMS (Planned Maintenance System) data extraction specialist.\n\n"
            "The text contains [PAGE N] markers — use these numbers for source_page_number.\n\n"
            "Extract ALL maintenance jobs, service intervals, and inspection tasks.\n"
            "Maintenance schedules appear as:\n"
            "  - Tables with columns: Interval | Description/Job (e.g. 'Every day', 'Weekly', 'Monthly')\n"
            "  - Numbered procedure lists under headings like '8. Maintenance', 'Service Schedule'\n"
            "  - Section headings like '8.3 Check V-Belt', '9.4 Maintenance of UV Sterilizer'\n\n"
            "FREQUENCY TYPE MAPPING (use exact values shown):\n"
            "  Every day / Daily / 24h → frequency_type='daily', frequency=1\n"
            "  Weekly / Every week / 7 days → frequency_type='weekly', frequency=1\n"
            "  Biweekly / Fortnightly / Every 2 weeks → frequency_type='biweekly', frequency=2\n"
            "  Monthly / Every month / 30 days → frequency_type='monthly', frequency=1\n"
            "  3 months / Quarterly → frequency_type='quarterly', frequency=3\n"
            "  6 months / Half yearly / Bi-annual → frequency_type='half_yearly', frequency=6\n"
            "  12 months / Yearly / Annually / Once a year → frequency_type='yearly', frequency=12\n"
            "  Biyearly / Every 2 years / Every 24 months → frequency_type='biannual', frequency=24\n"
            "  Running hours (e.g. every 500h, 1000h) → frequency_type='running_hours', frequency=<hour value>\n\n"
            "IMPORTANT — job_name formatting:\n"
            "  - Be specific: 'Replace UV lamp' not 'Replace lamp'\n"
            "  - Include equipment context: 'Check aeration blower air filter'\n"
            "  - Preserve numbered items from tables as separate jobs\n\n"
            "Return ONLY a valid JSON array. Each record:\n"
            "{\n"
            '  "job_name": "concise specific name (e.g. \'Replace UV lamp\', \'Check V-belt tension\')",\n'
            '  "job_code": "section/item number from manual (e.g. \'8.3.2\', \'Item 4\') or null",\n'
            '  "job_description": "full procedure text from the manual or null",\n'
            '  "safety_precaution": "WARNING/CAUTION/NOTICE text relevant to this job or null",\n'
            '  "frequency": integer representing the interval value (1 for daily, 2 for biweekly, 12 for yearly, etc.) or null,\n'
            '  "frequency_type": "daily|weekly|biweekly|monthly|quarterly|half_yearly|yearly|biannual|running_hours or null",\n'
            '  "is_critical": true if this job is for safety/regulatory equipment or has a WARNING label,\n'
            '  "source_page_number": integer from [PAGE N] marker or null,\n'
            '  "confidence_score": integer 70-98\n'
            "}\n\n"
            "RULES:\n"
            "- source_page_number from [PAGE N] markers — do not guess\n"
            "- Extract EVERY distinct job item — do not merge different tasks into one\n"
            "- For maintenance schedule tables: each row/item = one job record\n"
            "- For procedure sections (e.g. '8.3 Check V-belt'): extract as a job with description\n"
            "- Safety precaution: copy the WARNING/CAUTION text shown near the job if any\n"
            "- If no maintenance jobs exist in this document, return []\n"
            "- Return ONLY the JSON array, no markdown fences"
        ),
        "user_template": (
            "Document: {filename}\n\n"
            "Extract all maintenance jobs, service intervals, and inspection tasks. "
            "Use [PAGE N] markers for source_page_number.\n"
            "Look for: maintenance schedule tables (Interval | Description), numbered procedure sections, "
            "and section headings describing service tasks.\n\n{text}"
        ),
    },
    "spare": {
        "system": (
            "You are an expert maritime PMS (Planned Maintenance System) data extraction specialist.\n\n"
            "The text contains [PAGE N] markers — use these numbers for source_page_number.\n\n"
            "Extract ALL spare parts, recommended spares, and consumables.\n"
            "Spare parts lists appear as:\n"
            "  1. Tables: NO. | NAME | MATERIAL | QTY | REMARKS  (or similar columns)\n"
            "  2. Drawing parts lists: numbered items callout on a technical drawing\n"
            "  3. Sections titled: 'Spare Parts', 'Parts List', 'Recommended Spares', 'Spare Part Catalogue'\n"
            "  4. Chapter 13 or similar appendix listing parts by sub-assembly\n\n"
            "Drawing-based parts tables look like:\n"
            "  NO. | NAME | MATERIAL | QTY   (e.g. 1 | UV LAMP | QUARTZ GLASS | 1)\n"
            "  Extract EVERY row. The drawing_position is the NO. column.\n"
            "  The drawing_number is the figure/drawing reference (e.g. 'Fig.7', 'UV STERILIZER drawing').\n\n"
            "Return ONLY a valid JSON array. Each record:\n"
            "{\n"
            '  "part_name": "exact part name from the document (e.g. \'UV LAMP\', \'O-RING\')",\n'
            '  "part_number": "catalog/part number exactly as printed or null",\n'
            '  "drawing_number": "figure or drawing reference (e.g. \'Fig.7\', \'SBH-65055\') or null",\n'
            '  "drawing_position": "item/position number from the parts table (e.g. \'1\', \'11\') or null",\n'
            '  "specification": "material, size, standard, quantity note (e.g. \'QUARTZ GLASS\', \'RUBBER\', \'STAINLESS STEEL\') or null",\n'
            '  "spare_maker": "manufacturer — if manual is for a specific maker (e.g. TAIKO KIKAI), set that maker for all parts; null only if truly unknown",\n'
            '  "spare_model": "model or sub-assembly this spare belongs to (e.g. \'UV Sterilizer SBH-25\', \'Aeration Blower TSS-25\') or null",\n'
            '  "source_page_number": integer from [PAGE N] marker or null,\n'
            '  "confidence_score": integer 70-98\n'
            "}\n\n"
            "RULES:\n"
            "- source_page_number from [PAGE N] markers only\n"
            "- Extract EVERY row from parts tables — never skip rows\n"
            "- For drawing parts tables (NO./NAME/MATERIAL): drawing_position=NO., specification=MATERIAL\n"
            "- Part numbers: include exactly as printed (do not reformat)\n"
            "- spare_maker: infer from document title/header (e.g. 'TAIKO KIKAI INDUSTRIES' → 'Taiko Kikai')\n"
            "- spare_model: identify which sub-assembly the spare belongs to from context (section heading)\n"
            "- If no spare parts found, return []\n"
            "- Return ONLY the JSON array, no markdown fences"
        ),
        "user_template": (
            "Document: {filename}\n\n"
            "Extract all spare parts, recommended spares, and consumables. "
            "Use [PAGE N] markers for source_page_number.\n"
            "Look for: parts tables (NO./NAME/MATERIAL/QTY), drawing parts lists, "
            "sections titled 'Spare Parts', 'Parts List', 'Recommended Spares'.\n\n{text}"
        ),
    },
}


_PAGE_BLOCK_RE = re.compile(r"\[PAGE\s+(\d+)\]\s*\n?(.*?)(?=(?:\n\[PAGE\s+\d+\])|\Z)", re.S)


def _strip_code_fences(raw_text: str) -> str:
    if raw_text.startswith("```"):
        lines = raw_text.splitlines()
        lines = lines[1:] if lines and lines[0].startswith("```") else lines
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        raw_text = "\n".join(lines).strip()
    return raw_text


def _parse_json_records(raw_text: str) -> list[dict]:
    parsed: Any = json.loads(_strip_code_fences(raw_text).strip())
    if isinstance(parsed, list):
        return [r for r in parsed if isinstance(r, dict)]
    if isinstance(parsed, dict):
        for key in ("items", "records", "components", "jobs", "spares", "data", "results"):
            value = parsed.get(key)
            if isinstance(value, list):
                return [r for r in value if isinstance(r, dict)]
        if any(field in parsed for field in ("component_name", "job_name", "part_name", "source_page_number")):
            return [parsed]
    return []


def _redact_error_message(exc: Exception) -> str:
    message = str(exc)
    for secret in (
        getattr(settings, "OPENAI_API_KEY", ""),
        getattr(settings, "ANTHROPIC_API_KEY", ""),
        getattr(settings, "GEMINI_API_KEY", ""),
        getattr(settings, "GROQ_API_KEY", ""),
    ):
        if secret:
            message = message.replace(secret, "***")
    return message


async def _extract_with_claude(
    *,
    system_prompt: str,
    user_message: str,
    filename: str,
    extraction_type: str,
) -> list[dict]:
    if not settings.ANTHROPIC_API_KEY:
        raise RuntimeError("ANTHROPIC_API_KEY is not configured")

    client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
    max_tokens = getattr(settings, "EXTRACTION_MAX_TOKENS", 8192)
    model_id: str = getattr(settings, "CLAUDE_MODEL_ID", None) or "claude-sonnet-4-6"
    message = await client.messages.create(
        model=model_id,
        max_tokens=max_tokens,
        system=system_prompt,
        messages=[{"role": "user", "content": user_message}],
    )
    raw_text: str = message.content[0].text.strip()
    logger.info("extract_entities[claude]: %s/%s responded", filename, extraction_type)
    return _parse_json_records(raw_text)


async def _extract_with_openai(
    *,
    system_prompt: str,
    user_message: str,
    filename: str,
    extraction_type: str,
) -> list[dict]:
    if not settings.OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY is not configured")

    from openai import AsyncOpenAI

    client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
    max_tokens = getattr(settings, "EXTRACTION_MAX_TOKENS", 8192)
    model_id: str = getattr(settings, "OPENAI_MODEL_ID", None) or "gpt-4.1-mini"
    response = await client.chat.completions.create(
        model=model_id,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ],
        max_tokens=max_tokens,
        temperature=0,
    )
    raw_text = (response.choices[0].message.content or "").strip()
    if not raw_text:
        raise RuntimeError("OpenAI returned an empty response")
    logger.info("extract_entities[openai]: %s/%s responded", filename, extraction_type)
    return _parse_json_records(raw_text)


async def _extract_with_groq(
    *,
    system_prompt: str,
    user_message: str,
    filename: str,
    extraction_type: str,
) -> list[dict]:
    if not settings.GROQ_API_KEY:
        raise RuntimeError("GROQ_API_KEY is not configured")

    from openai import AsyncOpenAI

    client = AsyncOpenAI(
        api_key=settings.GROQ_API_KEY,
        base_url="https://api.groq.com/openai/v1",
    )
    max_tokens = min(getattr(settings, "EXTRACTION_MAX_TOKENS", 8192), 8192)
    response = await client.chat.completions.create(
        model="llama-3.1-8b-instant",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ],
        max_tokens=max_tokens,
        temperature=0,
    )
    raw_text = (response.choices[0].message.content or "").strip()
    if not raw_text:
        raise RuntimeError("Groq returned an empty response")
    logger.info("extract_entities[groq]: %s/%s responded", filename, extraction_type)
    return _parse_json_records(raw_text)


async def _extract_with_gemini(
    *,
    system_prompt: str,
    user_message: str,
    filename: str,
    extraction_type: str,
) -> list[dict]:
    if not settings.GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY is not configured")

    import httpx

    prompt = f"{system_prompt}\n\n{user_message}"
    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"gemini-2.0-flash-lite:generateContent?key={settings.GEMINI_API_KEY}"
    )
    payload = {"contents": [{"parts": [{"text": prompt}]}]}
    async with httpx.AsyncClient(timeout=180) as client:
        response = None
        for attempt, wait_seconds in enumerate((5, 10, 20), start=1):
            response = await client.post(url, json=payload)
            if response.status_code != 429:
                response.raise_for_status()
                break
            if attempt == 3:
                response.raise_for_status()
            logger.warning(
                "extract_entities[gemini]: 429 for %s/%s, retrying in %ss",
                filename,
                extraction_type,
                wait_seconds,
            )
            await asyncio.sleep(wait_seconds)
    data = response.json()
    raw_text = data["candidates"][0]["content"]["parts"][0]["text"].strip()
    logger.info("extract_entities[gemini]: %s/%s responded", filename, extraction_type)
    return _parse_json_records(raw_text)


def _dedupe_records(records: list[dict], extraction_type: str) -> list[dict]:
    seen: set[str] = set()
    deduped: list[dict] = []
    for record in records:
        if extraction_type == "component":
            key = "|".join(
                [
                    (record.get("component_name") or "").strip().lower(),
                    (record.get("main_machinery") or "").strip().lower(),
                    str(record.get("source_page_number") or ""),
                ]
            )
        elif extraction_type == "job":
            key = "|".join(
                [
                    (record.get("job_name") or "").strip().lower(),
                    (record.get("job_code") or "").strip().lower(),
                    str(record.get("source_page_number") or ""),
                ]
            )
        else:
            key = "|".join(
                [
                    (record.get("part_name") or "").strip().lower(),
                    (record.get("part_number") or "").strip().lower(),
                    str(record.get("source_page_number") or ""),
                ]
            )
        if key.strip("|") and key in seen:
            continue
        if key.strip("|"):
            seen.add(key)
        deduped.append(record)
    return deduped


def _parse_page_tokens(value: str | None) -> list[int]:
    if not value:
        return []
    pages: set[int] = set()
    for token in value.split(","):
        cleaned = token.strip()
        if not cleaned:
            continue
        if "-" in cleaned:
            start_raw, end_raw = cleaned.split("-", 1)
            try:
                start = int(start_raw.strip())
                end = int(end_raw.strip())
            except ValueError:
                continue
            for page in range(min(start, end), max(start, end) + 1):
                pages.add(page)
            continue
        try:
            pages.add(int(cleaned))
        except ValueError:
            continue
    return sorted(pages)


def _split_marked_pages(text: str) -> list[tuple[int, str]]:
    pages: list[tuple[int, str]] = []
    for match in _PAGE_BLOCK_RE.finditer(text):
        page_no = int(match.group(1))
        page_body = match.group(2).strip()
        pages.append((page_no, page_body))
    return pages


def _filter_text_to_pages(text: str, selected_pages: list[int]) -> str:
    if not selected_pages or "[PAGE " not in text:
        return text
    page_set = set(selected_pages)
    selected_blocks = [
        f"[PAGE {page_no}]\n{page_body}".strip()
        for page_no, page_body in _split_marked_pages(text)
        if page_no in page_set
    ]
    return "\n\n".join(selected_blocks).strip() or text


def _selected_manual_pages(manual: Any, entity_type: str) -> list[int]:
    physical_attr = {
        "component": "pages_with_components_physical",
        "job": "pages_with_jobs_physical",
        "spare": "pages_with_spares_physical",
    }[entity_type]
    canonical_attr = {
        "component": "pages_with_components",
        "job": "pages_with_jobs",
        "spare": "pages_with_spares",
    }[entity_type]
    return _parse_page_tokens(
        getattr(manual, physical_attr, None) or getattr(manual, canonical_attr, None)
    )


def _normalise_text(value: str | None) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", (value or "").lower())).strip()


def _component_match_score(search_text: str, component: Any, page_reference: int | None) -> float:
    haystack = _normalise_text(search_text)
    component_text = _normalise_text(
        " ".join(
            filter(
                None,
                [
                    getattr(component, "component_name", None),
                    getattr(component, "main_machinery", None),
                    getattr(component, "maker", None),
                    getattr(component, "model", None),
                ],
            )
        )
    )
    if not haystack or not component_text:
        return 0.0

    hay_tokens = set(haystack.split())
    comp_tokens = set(component_text.split())
    overlap = len(hay_tokens & comp_tokens) / max(len(comp_tokens), 1)
    ratio = SequenceMatcher(None, haystack, component_text).ratio()
    score = max(overlap, ratio)

    component_page = getattr(component, "page_reference", None)
    if page_reference and component_page:
        distance = abs(page_reference - component_page)
        if distance == 0:
            score += 0.15
        elif distance <= 3:
            score += 0.08
        elif distance <= 6:
            score += 0.03

    return score


def _component_has_manual_reference(component: Any, manual: Any) -> bool:
    manual_id = getattr(manual, "id", None)
    manual_name = (getattr(manual, "original_filename", None) or "").strip()
    component_manual_id = getattr(component, "source_manual_id", None)
    pdf_reference = getattr(component, "pdf_reference", None) or ""
    return bool(
        (manual_id and component_manual_id == manual_id)
        or (manual_name and manual_name.lower() in pdf_reference.lower())
    )


def _page_in_reference(page_reference: int | None, pages_value: str | None) -> bool:
    if page_reference is None or not pages_value:
        return False
    return page_reference in set(_parse_page_tokens(pages_value))


def _merge_reference_values(current: str | None, incoming: str | None) -> str | None:
    current_clean = (current or "").strip()
    incoming_clean = (incoming or "").strip()
    if not current_clean:
        return incoming_clean or None
    if not incoming_clean:
        return current_clean or None
    if incoming_clean in current_clean:
        return current_clean
    return f"{current_clean}; {incoming_clean}"


def _link_score(
    *,
    search_text: str,
    component: Any,
    page_reference: int | None,
    relation: str,
    manual: Any,
) -> float:
    score = _component_match_score(search_text, component, page_reference)

    if _component_has_manual_reference(component, manual):
        score += 0.16

    if relation == "job" and _page_in_reference(page_reference, getattr(component, "job_pages", None)):
        score += 0.2
    if relation == "spare" and _page_in_reference(page_reference, getattr(component, "spare_pages", None)):
        score += 0.2

    return score


def _manual_page_refs_summary(manual: Any) -> str:
    parts: list[str] = []
    for label, printed_attr, physical_attr in (
        ("components", "pages_with_components_printed", "pages_with_components_physical"),
        ("jobs", "pages_with_jobs_printed", "pages_with_jobs_physical"),
        ("spares", "pages_with_spares_printed", "pages_with_spares_physical"),
    ):
        printed = getattr(manual, printed_attr, None) or ""
        physical = getattr(manual, physical_attr, None) or ""
        if printed or physical:
            parts.append(f"{label}: printed={printed or 'none'}, physical={physical or 'none'}")
    return "; ".join(parts)


def _build_component_context_text(components: list[Any], manual: Any) -> str:
    if not components:
        return ""
    def _value(component: Any, key: str) -> Any:
        if isinstance(component, dict):
            return component.get(key)
        return getattr(component, key, None)

    lines = [
        "Known component context from this manual:",
        f"Manual screening refs -> {_manual_page_refs_summary(manual) or 'not set'}",
    ]
    for component in components[:40]:
        lines.append(
            " - "
            + " | ".join(
                filter(
                    None,
                    [
                        f"name={_value(component, 'component_name')}",
                        f"main={_value(component, 'main_machinery')}",
                        f"maker={_value(component, 'maker')}",
                        f"model={_value(component, 'model')}",
                        f"page={_value(component, 'page_reference') or _value(component, 'source_page_number')}",
                    ],
                )
            )
        )
    lines.append(
        "When extracting jobs or spares, prefer linking each record to one of these components via job_name wording, spare_model, or component context."
    )
    return "\n".join(lines)

# ---------------------------------------------------------------------------
# Core extraction function
# ---------------------------------------------------------------------------


async def extract_entities(
    text_chunk: str,
    extraction_type: str,
    filename: str,
    custom_prompt: str | None = None,
    context_note: str | None = None,
) -> list[dict]:
    """
    Call the configured AI providers to extract structured entities from a text chunk.

    Args:
        text_chunk: The manual text to process.
        extraction_type: One of "component", "job", "spare".
        filename: Source filename (used for logging).
        custom_prompt: Optional override for the system prompt.

    Returns:
        List of dicts parsed from Claude's JSON response, or [] on error.
    """
    prompt_config = DEFAULT_PROMPTS.get(extraction_type, DEFAULT_PROMPTS["component"])
    system_prompt = custom_prompt or prompt_config["system"]
    user_message = prompt_config["user_template"].format(text=text_chunk, filename=filename)
    if context_note:
        user_message = f"{user_message}\n\nAdditional extraction context:\n{context_note}"
    providers: list[tuple[str, Any]] = [
        ("openai", _extract_with_openai),
        ("claude", _extract_with_claude),
        ("gemini", _extract_with_gemini),
        ("groq", _extract_with_groq),
    ]
    last_error: Exception | None = None

    for provider_name, provider in providers:
        try:
            records = await provider(
                system_prompt=system_prompt,
                user_message=user_message,
                filename=filename,
                extraction_type=extraction_type,
            )
            logger.info(
                "extract_entities: provider=%s %s/%s records=%d",
                provider_name,
                filename,
                extraction_type,
                len(records),
            )
            return records
        except json.JSONDecodeError as exc:
            last_error = exc
            logger.warning(
                "extract_entities: provider=%s JSON parse error for %s/%s: %s",
                provider_name,
                filename,
                extraction_type,
                exc,
            )
        except Exception as exc:
            last_error = exc
            logger.warning(
                "extract_entities: provider=%s failed for %s/%s: %s",
                provider_name,
                filename,
                extraction_type,
                _redact_error_message(exc),
            )

    if last_error is not None:
        message = _redact_error_message(last_error)
        logger.error(
            "extract_entities: all providers failed for %s/%s: %s",
            filename,
            extraction_type,
            message,
        )
        raise ExtractionProvidersFailed(
            f"All extraction providers failed for {filename}/{extraction_type}: {message}"
        )
    return []


# ---------------------------------------------------------------------------
# Post-processing helpers
# ---------------------------------------------------------------------------


async def _overwrite_component_manual_refs(
    *,
    db: Any,
    manual: Any,
    vessel_id: uuid.UUID,
    tenant_id: uuid.UUID,
) -> int:
    from sqlalchemy import select
    from app.models.component import Component, QCStatus

    result = await db.execute(
        select(Component).where(
            Component.vessel_id == vessel_id,
            Component.tenant_id == tenant_id,
            Component.is_deleted == False,
            Component.qc_status != QCStatus.rejected,
        )
    )
    components = result.scalars().all()

    updated = 0
    job_pages = getattr(manual, "pages_with_jobs", None) or None
    spare_pages = getattr(manual, "pages_with_spares", None) or None
    pdf_ref = manual.original_filename
    for comp in components:
        if not _component_has_manual_reference(comp, manual):
            continue
        changed = False
        if job_pages and comp.job_pages != job_pages and ";" not in (comp.job_pages or ""):
            comp.job_pages = job_pages
            changed = True
        if spare_pages and comp.spare_pages != spare_pages and ";" not in (comp.spare_pages or ""):
            comp.spare_pages = spare_pages
            changed = True
        merged_pdf_ref = _merge_reference_values(comp.pdf_reference, pdf_ref)
        if comp.pdf_reference != merged_pdf_ref:
            comp.pdf_reference = merged_pdf_ref
            changed = True
        if changed:
            db.add(comp)
            updated += 1
    return updated


async def _link_records_to_components(
    *,
    db: Any,
    manual: Any,
    vessel_id: uuid.UUID,
    tenant_id: uuid.UUID,
) -> tuple[int, int]:
    from sqlalchemy import select
    from app.models.component import Component, QCStatus
    from app.models.job import Job
    from app.models.spare import Spare

    comp_result = await db.execute(
        select(Component).where(
            Component.vessel_id == vessel_id,
            Component.tenant_id == tenant_id,
            Component.is_deleted == False,
            Component.qc_status != QCStatus.rejected,
        )
    )
    all_components = comp_result.scalars().all()
    same_manual_components = [comp for comp in all_components if _component_has_manual_reference(comp, manual)]
    fallback_components = same_manual_components or all_components

    def pick_component(search_text: str, page_reference: int | None, relation: str):
        if not fallback_components:
            return None
        if len(same_manual_components) == 1:
            return same_manual_components[0]
        ranked = sorted(
            (
                (
                    _link_score(
                        search_text=search_text,
                        component=component,
                        page_reference=page_reference,
                        relation=relation,
                        manual=manual,
                    ),
                    component,
                )
                for component in fallback_components
            ),
            key=lambda item: item[0],
            reverse=True,
        )
        best_score, best_component = ranked[0]
        return best_component if best_score >= 0.28 else None

    jobs_result = await db.execute(
        select(Job).where(
            Job.vessel_id == vessel_id,
            Job.tenant_id == tenant_id,
            Job.is_deleted == False,
            Job.source_manual_id == manual.id,
        )
    )
    jobs = jobs_result.scalars().all()
    jobs_linked = 0
    for job in jobs:
        match = pick_component(
            " ".join(filter(None, [job.job_name, job.job_code, job.job_description])),
            job.page_reference,
            "job",
        )
        if match:
            changed = False
            if job.component_id != match.id:
                job.component_id = match.id
                changed = True
            if job.is_unmapped:
                job.is_unmapped = False
                changed = True
            if job.pdf_reference != manual.original_filename:
                job.pdf_reference = manual.original_filename
                changed = True
            source_ref = (
                f"{manual.original_filename} (p.{job.page_reference})"
                if job.page_reference
                else manual.original_filename
            )
            if job.source_reference != source_ref:
                job.source_reference = source_ref
                changed = True
            if changed:
                db.add(job)
                jobs_linked += 1

    spares_result = await db.execute(
        select(Spare).where(
            Spare.vessel_id == vessel_id,
            Spare.tenant_id == tenant_id,
            Spare.is_deleted == False,
            Spare.source_manual_id == manual.id,
        )
    )
    spares = spares_result.scalars().all()
    spares_linked = 0
    for spare in spares:
        match = pick_component(
            " ".join(
                filter(
                    None,
                    [
                        spare.part_name,
                        spare.part_number,
                        spare.spare_model,
                        spare.specification,
                        spare.drawing_number,
                    ],
                )
            ),
            spare.page_reference,
            "spare",
        )
        if match:
            changed = False
            if spare.component_id != match.id:
                spare.component_id = match.id
                changed = True
            if spare.machinery_maker != match.maker:
                spare.machinery_maker = match.maker
                changed = True
            if spare.machinery_model != match.model:
                spare.machinery_model = match.model
                changed = True
            if changed:
                db.add(spare)
                spares_linked += 1

    return jobs_linked, spares_linked


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
        vessel_id_str = str(vessel_id)

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
        norm_cat = (category or "").strip().lower()
        # Skip only if truly unknown AND no page signals from classifier
        pages_with_any = (
            getattr(manual, "pages_with_components", None)
            or getattr(manual, "pages_with_jobs", None)
            or getattr(manual, "pages_with_spares", None)
        )
        if norm_cat in ("", "unknown/unclassifiable", "unknown") and not pages_with_any:
            logger.info(
                "auto_extract_from_manual: skipping manual %s — category=%r, no page signals",
                manual_id_str,
                category,
            )
            return
        # If unknown but has page signals, treat as Instruction Manual for extraction
        if norm_cat in ("", "unknown/unclassifiable", "unknown"):
            category = "Instruction Manual"
            logger.info(
                "auto_extract_from_manual: treating unknown manual %s as Instruction Manual (has page signals)",
                manual_id_str,
            )

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
        # Determine which entity types to extract strictly from screened page refs.
        # This keeps extraction cost aligned to what reviewers selected.
        # ------------------------------------------------------------------
        entity_pages = {
            entity_type: _selected_manual_pages(manual, entity_type)
            for entity_type in ("component", "job", "spare")
        }
        extraction_types = [entity_type for entity_type, pages in entity_pages.items() if pages]

        if not extraction_types:
            logger.info(
                "auto_extract_from_manual: skipping manual %s because no screened extraction pages are set",
                filename,
            )
            await db.execute(
                update(Manual)
                .where(Manual.id == manual_id)
                .values(status=ManualStatus.classified)
            )
            await db.commit()
            return

        type_to_text: dict[str, str] = {}
        for entity_type in extraction_types:
            selected_pages = entity_pages[entity_type]
            filtered_text = _filter_text_to_pages(full_text, selected_pages)
            type_to_text[entity_type] = filtered_text
            logger.info(
                "auto_extract_from_manual: %s using %s screened pages=%s chars=%d",
                filename,
                entity_type,
                selected_pages,
                len(filtered_text),
            )

        await db.execute(
            update(Job)
            .where(Job.source_manual_id == manual.id, Job.is_deleted == False)
            .values(is_deleted=True)
        )
        await db.execute(
            update(Spare)
            .where(Spare.source_manual_id == manual.id, Spare.is_deleted == False)
            .values(is_deleted=True)
        )
        await db.execute(
            update(Component)
            .where(
                Component.source_manual_id == manual.id,
                Component.is_deleted == False,
                Component.qc_status == QCStatus.pending,
            )
            .values(is_deleted=True)
        )
        await db.commit()

        # ------------------------------------------------------------------
        # Chunk the full text so every page is processed.
        # Claude claude-sonnet-4-6 has a 200k token context window.
        # 120,000 chars ≈ 30,000 tokens — leaves ample room for system
        # prompt and a large JSON response.
        # ------------------------------------------------------------------
        CHUNK_SIZE = max(4_000, int(getattr(settings, "EXTRACTION_CHUNK_CHARS", 14_000) or 14_000))
        OVERLAP = max(0, int(getattr(settings, "EXTRACTION_CHUNK_OVERLAP_CHARS", 500) or 500))

        def _chunk_text(text: str) -> list[str]:
            page_blocks = [
                f"[PAGE {page_no}]\n{page_body}".strip()
                for page_no, page_body in _split_marked_pages(text)
            ]
            if page_blocks:
                chunks: list[str] = []
                current_blocks: list[str] = []
                current_size = 0
                for block in page_blocks:
                    block_size = len(block) + 2
                    if current_blocks and current_size + block_size > CHUNK_SIZE:
                        chunks.append("\n\n".join(current_blocks))
                        overlap_blocks: list[str] = []
                        overlap_size = 0
                        for previous_block in reversed(current_blocks):
                            previous_size = len(previous_block) + 2
                            if overlap_blocks and overlap_size + previous_size > OVERLAP:
                                break
                            overlap_blocks.insert(0, previous_block)
                            overlap_size += previous_size
                        current_blocks = overlap_blocks.copy()
                        current_size = sum(len(item) + 2 for item in current_blocks)
                    current_blocks.append(block)
                    current_size += block_size
                if current_blocks:
                    chunks.append("\n\n".join(current_blocks))
                return chunks
            if len(text) <= CHUNK_SIZE:
                return [text]
            chunks: list[str] = []
            start = 0
            while start < len(text):
                end = min(start + CHUNK_SIZE, len(text))
                chunks.append(text[start:end])
                if end >= len(text):
                    break
                start = max(end - OVERLAP, start + 1)
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
        extracted_component_context: list[dict[str, Any]] = []

        for etype in extraction_types:
            source_text = type_to_text.get(etype) or full_text
            text_chunks = _chunk_text(source_text)
            logger.info(
                "auto_extract_from_manual: %s -> %s chars=%d chunks=%d",
                filename,
                etype,
                len(source_text),
                len(text_chunks),
            )
            all_records: list[dict] = []
            for chunk_idx, chunk in enumerate(text_chunks):
                chunk_label = f"{filename} [chunk {chunk_idx + 1}/{len(text_chunks)}]"
                context_note = None
                if etype in {"job", "spare"} and extracted_component_context:
                    context_note = _build_component_context_text(extracted_component_context, manual)
                records = await extract_entities(chunk, etype, chunk_label, context_note=context_note)
                all_records.extend(records)
            records = _dedupe_records(all_records, etype)

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
                        is_unmapped=True,
                        group1=record.get("group1") or "Uncategorised",
                        group2=record.get("group2") or "Uncategorised",
                        main_machinery=record.get("main_machinery") or "Unknown",
                        component_name=record.get("component_name") or "Unknown Component",
                        maker=_maker,
                        model=_model,
                        serial_number=record.get("serial_number") or None,
                        specification=record.get("specification") or None,
                        location=record.get("location") or None,
                        machinery_particulars=record.get("machinery_particulars") or None,
                        is_critical=bool(record.get("is_critical", False)),
                        job_pages=record.get("job_pages") or getattr(manual, "pages_with_jobs", None) or None,
                        spare_pages=record.get("spare_pages") or getattr(manual, "pages_with_spares", None) or None,
                        page_reference=int(source_page) if source_page is not None else None,
                        pdf_reference=filename,
                    )
                    components_to_add.append(comp)
                    extracted_component_context.append(
                        {
                            "component_name": comp.component_name,
                            "main_machinery": comp.main_machinery,
                            "maker": comp.maker,
                            "model": comp.model,
                            "source_page_number": comp.page_reference,
                        }
                    )

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
                        pdf_reference=filename,
                        source_reference=(
                            f"{filename} (p.{int(source_page)})"
                            if source_page is not None
                            else filename
                        ),
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

        try:
            component_ref_updates = await _overwrite_component_manual_refs(
                db=db,
                manual=manual,
                vessel_id=vessel_id,
                tenant_id=tenant_id,
            )
            jobs_linked, spares_linked = await _link_records_to_components(
                db=db,
                manual=manual,
                vessel_id=vessel_id,
                tenant_id=tenant_id,
            )
            await db.commit()
            logger.info(
                "auto_extract_from_manual: manual sync vessel=%s components=%d jobs=%d spares=%d",
                vessel_id_str,
                component_ref_updates,
                jobs_linked,
                spares_linked,
            )
        except Exception as link_exc:
            logger.warning("auto_extract_from_manual: manual sync failed: %s", link_exc)
