"""
Automatic manual classifier.

Primary: Uses Claude AI (Anthropic) for intelligent classification when
ANTHROPIC_API_KEY is configured.

Fallback: Uses pdfplumber + keyword matching when no API key is set.
"""
from __future__ import annotations

import io
import json
import re
from dataclasses import dataclass
from typing import Optional


@dataclass
class ClassificationResult:
    category: str
    confidence: int
    useful_for_extraction: str  # "yes", "partial", "no"
    pages_with_components: str
    pages_with_jobs: str
    pages_with_spares: str
    page_count: int
    supply_type: str = "OEM"  # "OEM" | "yard_supply"


# ---------------------------------------------------------------------------
# Keyword fallback definitions
# ---------------------------------------------------------------------------

CATEGORY_RULES: list[tuple[str, list[str], int]] = [
    ("Machinery Particulars", [
        "machinery list", "machinery particulars", "equipment list",
        "maker list", "manufacturer list", "machinery inventory",
        "installed machinery", "machinery register",
    ], 85),
    ("Instruction Manual", [
        "instruction manual", "operation manual", "operating manual",
        "maintenance manual", "service manual", "user manual",
        "operator manual", "technical manual", "overhaul manual",
    ], 85),
    ("General Arrangement", [
        "general arrangement", "g.a. plan", "ga plan",
        "deck arrangement", "layout plan", "general plan",
    ], 80),
    ("Pipeline Diagrams/P&ID", [
        "p&id", "piping and instrumentation", "pipeline diagram",
        "piping diagram", "schematic diagram", "flow diagram",
        "process flow", "system diagram", "hydraulic diagram",
    ], 80),
    ("LSA/FFA Plans", [
        "life saving appliance", "lsa", "fire fighting appliance",
        "ffa", "fire safety plan", "muster list", "evacuation plan",
        "lifeboat", "life raft", "fire extinguisher plan",
    ], 80),
    ("Tank Capacity Plan", [
        "tank capacity", "capacity plan", "sounding table",
        "ullage table", "trim and stability", "tank arrangement",
    ], 80),
    ("Electrical Diagrams", [
        "electrical diagram", "wiring diagram", "single line diagram",
        "switchboard", "electrical schematic", "power distribution",
        "load list", "cable list",
    ], 78),
    ("Yard/Finished Drawings", [
        "yard drawing", "construction drawing", "as-built",
        "structural drawing", "hull drawing", "shipyard",
    ], 75),
    ("Class Certificates/Surveys", [
        "class certificate", "survey report", "classification",
        "dnv", "lloyd's register", "bureau veritas", "abs",
        "rina", "certificate of registry", "safety certificate",
    ], 82),
]

EXTRACTION_KEYWORDS = {
    "components": ["component", "equipment", "machinery", "system", "unit",
                   "pump", "compressor", "engine", "motor", "valve", "filter"],
    "jobs": ["maintenance", "overhaul", "inspection", "service", "check",
             "test", "lubrication", "adjustment", "interval", "running hours"],
    "spares": ["spare", "spare part", "part number", "item no", "catalog",
               "consumable", "wear part", "spare list"],
}

VALID_CATEGORIES = [
    "Instruction Manual", "Machinery Particulars", "General Arrangement",
    "Pipeline Diagrams/P&ID", "LSA/FFA Plans", "Tank Capacity Plan",
    "Yard/Finished Drawings", "Electrical Diagrams",
    "Class Certificates/Surveys", "Unknown/Unclassifiable",
]


# ---------------------------------------------------------------------------
# PDF text extraction helper
# ---------------------------------------------------------------------------

def _extract_pdf_text(content: bytes, max_pages: int = 9999) -> tuple[list[str], int]:
    """Extract text per page from PDF bytes. Returns (pages_text, total_pages).
    pages_text[i] is the text for page (i+1); tables are included inline."""
    try:
        import pdfplumber  # type: ignore
        pages_text: list[str] = []
        with pdfplumber.open(io.BytesIO(content)) as pdf:
            total = len(pdf.pages)
            for page in pdf.pages[:max_pages]:
                parts: list[str] = []
                t = page.extract_text()
                if t and t.strip():
                    parts.append(t)
                try:
                    for tbl in (page.extract_tables() or []):
                        if not tbl:
                            continue
                        rows = [
                            " | ".join(str(c).strip() if c else "" for c in row)
                            for row in tbl if row and any(c for c in row if c)
                        ]
                        if rows:
                            parts.append("[TABLE] " + " // ".join(rows[:5]))  # first 5 rows for brevity
                except Exception:
                    pass
                pages_text.append("\n".join(parts).strip())
        return pages_text, total
    except Exception:
        return [], 0


# Matches a standalone page number line: "9", "- 9 -", "– 9 –"
_PAGE_NUM_RE = re.compile(r'^[-–]?\s*(\d{1,4})\s*[-–]?$')
# Matches "Page 9" or "PAGE 9"
_PAGE_LABEL_RE = re.compile(r'^[Pp][Aa][Gg][Ee]\s+(\d{1,4})$')


def _detect_printed_page_num(text: str) -> Optional[int]:
    """
    Detect the page number visibly printed in the document by scanning the
    last 4 lines (footer) then first 4 lines (header) of the extracted text.
    Returns None if no printed page number is found on this page.
    """
    if not text:
        return None
    lines = [ln.strip() for ln in text.strip().splitlines() if ln.strip()]
    if not lines:
        return None
    # Check footer first (most common), then header
    for line in lines[-4:] + lines[:4]:
        m = _PAGE_NUM_RE.fullmatch(line)
        if m:
            n = int(m.group(1))
            if 1 <= n <= 9999:
                return n
        m = _PAGE_LABEL_RE.fullmatch(line)
        if m:
            return int(m.group(1))
    return None


def _make_marked_text(pages_text: list[str], max_chars: int = 400_000) -> tuple[str, set[int]]:
    """
    Build a single string with [PAGE N, doc_page=X] markers.
    - N       : physical PDF page position (1-indexed)
    - doc_page: the page number actually printed in the document,
                or 'none' if the page carries no printed number.

    Returns (marked_text, valid_doc_pages) where valid_doc_pages is the set
    of printed page numbers found in the document — used to validate AI output.
    """
    parts: list[str] = []
    total = 0
    valid_doc_pages: set[int] = set()
    for i, text in enumerate(pages_text, start=1):
        truncated = text[:800] if text else ""
        printed = _detect_printed_page_num(text)
        if printed is not None:
            valid_doc_pages.add(printed)
            marker = f"[PAGE {i}, doc_page={printed}]"
        else:
            marker = f"[PAGE {i}, doc_page=none]"
        snippet = f"{marker}\n{truncated}" if truncated else marker
        total += len(snippet)
        parts.append(snippet)
        if total >= max_chars:
            _log.warning("classifier: document truncated at page %d (>%d chars)", i, max_chars)
            break
    return "\n\n".join(parts), valid_doc_pages


def _filter_to_valid_pages(page_str: str, valid_doc_pages: set[int]) -> str:
    """
    Keep only page numbers that were actually printed in the document.
    Drops any number the AI invented that doesn't appear as a doc_page marker.
    Falls back to returning page_str unchanged if valid_doc_pages is empty
    (document has no printed page numbers at all).
    """
    if not page_str or not valid_doc_pages:
        return page_str
    kept: list[str] = []
    for token in page_str.split(","):
        token = token.strip()
        if not token:
            continue
        try:
            n = int(token)
            if n in valid_doc_pages:
                kept.append(str(n))
            else:
                _log.warning("classifier: dropping page %d — not a printed doc page (valid: %s)",
                             n, sorted(valid_doc_pages)[:15])
        except ValueError:
            pass
    return ", ".join(kept)


def _find_pages_for_topic(pages_text: list[str], keywords: list[str]) -> str:
    matching: list[int] = []
    for i, text in enumerate(pages_text):
        if any(kw in text.lower() for kw in keywords):
            matching.append(i + 1)
    if not matching:
        return ""
    ranges: list[str] = []
    start = end = matching[0]
    for page in matching[1:]:
        if page == end + 1:
            end = page
        else:
            ranges.append(f"{start}-{end}" if start != end else str(start))
            start = end = page
    ranges.append(f"{start}-{end}" if start != end else str(start))
    return ", ".join(ranges)


# ---------------------------------------------------------------------------
# Claude AI classifier
# ---------------------------------------------------------------------------

_log = __import__("logging").getLogger(__name__)


def _classify_with_claude(pages_text: list[str], filename: str, page_count: int) -> Optional[dict]:
    """Call Claude API to classify the manual. Returns parsed JSON or None on failure."""
    try:
        import anthropic
        from app.core.config import settings

        if not settings.ANTHROPIC_API_KEY:
            _log.warning("classifier: ANTHROPIC_API_KEY not set — falling back to keyword classifier")
            return None

        client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)

        # Build marked text for Claude — include [PAGE N, doc_page=X] markers
        marked_text, valid_doc_pages = _make_marked_text(pages_text, max_chars=80_000)

        non_empty = sum(1 for p in pages_text if p.strip())
        _log.info(
            "classifier: %s — pages=%d non_empty=%d text_chars=%d printed_pages=%s",
            filename, page_count, non_empty, len(marked_text), sorted(valid_doc_pages),
        )

        prompt = f"""You are an expert maritime document classifier specialising in ship technical documentation and PMS (Planned Maintenance System) data.

Filename: {filename}
Total pages: {page_count}

The document text below includes [PAGE N, doc_page=X] markers where:
- N       = physical PDF page position (do NOT use this in your answer)
- doc_page = the page number visibly printed in the document, or "none" if the page has no printed number

IMPORTANT: Always use doc_page values when reporting pages. Skip pages marked doc_page=none.

Document text:
---
{marked_text}
---

Classify this document into EXACTLY ONE of the following categories:

- **Instruction Manual**: Manufacturer's technical/operation/maintenance manual for a specific piece of equipment (contains operating procedures, maintenance schedules, overhaul instructions, spare parts lists, or equipment specifications). Even a short specification sheet for one piece of equipment (e.g. "SEWAGE TREATMENT PLANT SPECIFICATION") counts as Instruction Manual if it describes a single equipment item in detail.
- **Machinery Particulars**: A list/register/inventory of ALL equipment on the vessel — tabular format with many rows, columns like No. | Equipment | Maker | Model | Serial No. titled "Machinery List", "Equipment Register", "Maker List", or similar.
- **General Arrangement**: Deck plans, layout drawings showing spatial arrangement of the vessel. Mostly drawings with minimal text.
- **Pipeline Diagrams/P&ID**: Piping & Instrumentation Diagrams, system flow diagrams, hydraulic schematics.
- **LSA/FFA Plans**: Life Saving Appliance plans, Fire Fighting Appliance plans, fire safety plans, muster lists.
- **Tank Capacity Plan**: Tank tables, sounding tables, ullage tables, stability booklets, capacity plans.
- **Electrical Diagrams**: Single-line diagrams, wiring diagrams, cable lists, switchboard diagrams.
- **Yard/Finished Drawings**: Shipyard construction drawings, as-built drawings, structural drawings.
- **Class Certificates/Surveys**: Classification certificates, survey reports, safety certificates.
- **Unknown/Unclassifiable**: Cannot determine category with reasonable confidence.

For each field below, list the EXACT page numbers (from [PAGE N] markers) where that content appears.
Use comma-separated individual page numbers — NOT ranges. E.g. "5, 6, 7, 12, 13" not "5-7, 12-13".

- **pages_with_components**: Pages that contain ALL THREE of the following together for at least one piece of equipment: (1) equipment/component NAME, (2) MAKER/MANUFACTURER name, and (3) MODEL number or type designation. Typically found on cover/specification pages with name plate data or "Technical Data" tables. A page with procedures, general descriptions, or diagrams without maker+model does NOT qualify. For Machinery Particulars: pages with rows showing Name + Maker + Model columns. For Tank Capacity Plans: pages with tank name + capacity + sounding data.
- **pages_with_jobs**: Pages containing maintenance schedules, service intervals, or inspection procedures.
  Look for: section headings like "Maintenance", "Service Schedule", "Inspection", "Periodic Maintenance",
  tables with columns "Interval | Description", "Every day / Weekly / Monthly" rows.
- **pages_with_spares**: Pages containing spare parts lists or recommended spares.
  Look for: "Spare Parts", "Parts List", "Recommended Spares", "Spare Part Catalogue",
  tables with columns NO. | NAME | PART NUMBER | QTY.

Determine the supply type:
- **OEM**: Original Equipment Manufacturer manual — issued by the equipment maker. Contains the maker's name/logo on the cover, model numbers, operation/maintenance procedures written by the manufacturer.
- **yard_supply**: Shipyard delivery package — drawings, spare parts lists, or documentation assembled by the yard. Signs: hull number, ship name header, "SUPPLY"/"OUTFIT" columns, multiple equipment assemblies, final drawings with item/qty/material tables.

Return ONLY valid JSON in this exact format:
{{
  "category": "<category name exactly as listed above>",
  "confidence": <integer 0-100>,
  "useful_for_extraction": "<yes | partial | no>",
  "supply_type": "<OEM | yard_supply>",
  "pages_with_components": "<comma-separated doc_page numbers e.g. '1, 2, 9' — only pages with a printed doc_page number, empty string if none>",
  "pages_with_jobs": "<comma-separated doc_page numbers e.g. '9, 12, 13' — only pages with a printed doc_page number, empty string if none>",
  "pages_with_spares": "<comma-separated doc_page numbers e.g. '15, 16' — only pages with a printed doc_page number, empty string if none>",
  "reasoning": "<one sentence explanation>"
}}

Rules:
- CRITICAL: Use ONLY doc_page values from the markers — never use PDF position N. Never invent a number not seen as a doc_page value.
- CRITICAL: Skip pages marked doc_page=none — they have no printed page reference and must NOT appear in your output.
- List every individual doc_page number where the content appears — do NOT use ranges or hyphens
- pages_with_components STRICT RULE: only include a page if it has name + maker + model all present together on that page. Do NOT include pages that only have the equipment name. Do NOT include procedure, description, or drawing pages just because they reference equipment.
- useful_for_extraction = "yes" if Instruction Manual OR Machinery Particulars
- useful_for_extraction = "partial" if spec sheet or drawing with some equipment data (e.g. a spec sheet with maker/model but no maintenance section)
- useful_for_extraction = "no" if purely drawings, plans, certificates, P&IDs with no equipment data
- supply_type = "OEM" for manufacturer-issued manuals; "yard_supply" for shipyard-assembled bundles, outfit drawings, or delivery documentation with hull/ship references
- An equipment specification sheet (one equipment, with maker/model/capacity) → category="Instruction Manual", useful="partial"
- confidence 85-98: very clear; 65-84: probable; 40-64: uncertain; <40: use Unknown/Unclassifiable
- Machinery Particulars vs Instruction Manual: one equipment in depth → Instruction Manual; many equipment rows → Machinery Particulars
- If a section is genuinely absent, return empty string — do NOT invent page numbers"""

        model_id = getattr(settings, "CLAUDE_MODEL_ID", "claude-sonnet-4-6")
        message = client.messages.create(
            model=model_id,
            max_tokens=768,
            messages=[{"role": "user", "content": prompt}],
        )

        raw = message.content[0].text.strip()
        _log.info("classifier: Claude raw response for %s: %s", filename, raw[:300])
        if "```" in raw:
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        parsed = json.loads(raw.strip())
        # Filter page fields to only printed page numbers seen in the document
        if valid_doc_pages:
            for field in ("pages_with_components", "pages_with_jobs", "pages_with_spares"):
                parsed[field] = _filter_to_valid_pages(parsed.get(field, ""), valid_doc_pages)
        _log.info(
            "classifier: %s → category=%s confidence=%s jobs=%s spares=%s",
            filename,
            parsed.get("category"),
            parsed.get("confidence"),
            parsed.get("pages_with_jobs"),
            parsed.get("pages_with_spares"),
        )
        return parsed

    except Exception as exc:
        _log.warning("classifier: Claude call failed for %s: %s", filename, exc)
        return None


# ---------------------------------------------------------------------------
# Groq AI classifier (free tier — 30 RPM, uses llama-3.3-70b)
# ---------------------------------------------------------------------------

def _classify_with_groq(pages_text: list[str], filename: str, page_count: int) -> Optional[dict]:
    """Call Groq API (free tier) via OpenAI-compatible SDK. Returns parsed JSON or None."""
    try:
        from openai import OpenAI
        from app.core.config import settings

        if not settings.GROQ_API_KEY:
            return None

        client = OpenAI(
            api_key=settings.GROQ_API_KEY,
            base_url="https://api.groq.com/openai/v1",
        )

        marked_text, valid_doc_pages = _make_marked_text(pages_text, max_chars=80_000)
        non_empty = sum(1 for p in pages_text if p.strip())
        _log.info(
            "classifier[groq]: %s — pages=%d non_empty=%d text_chars=%d printed_pages=%s",
            filename, page_count, non_empty, len(marked_text), sorted(valid_doc_pages),
        )

        prompt = _build_classification_prompt(filename, page_count, marked_text)
        response = client.chat.completions.create(
            model="llama-3.1-8b-instant",  # 20k TPM free tier vs 1k for 70b
            messages=[{"role": "user", "content": prompt}],
            max_tokens=1024,
            temperature=0,
        )
        raw = (response.choices[0].message.content or "").strip()
        if not raw:
            _log.warning("classifier[groq]: empty response for %s", filename)
            return None

        _log.info("classifier[groq]: raw response for %s: %s", filename, raw[:300])
        if "```" in raw:
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        parsed = json.loads(raw.strip())
        # Filter page fields to only printed page numbers seen in the document
        if valid_doc_pages:
            for field in ("pages_with_components", "pages_with_jobs", "pages_with_spares"):
                parsed[field] = _filter_to_valid_pages(parsed.get(field, ""), valid_doc_pages)
        _log.info(
            "classifier[groq]: %s → category=%s confidence=%s jobs=%s spares=%s",
            filename,
            parsed.get("category"),
            parsed.get("confidence"),
            parsed.get("pages_with_jobs"),
            parsed.get("pages_with_spares"),
        )
        return parsed

    except Exception as exc:
        _log.warning("classifier: Groq call failed for %s: %s", filename, exc)
        return None


# ---------------------------------------------------------------------------
# Gemini AI classifier (free tier)
# ---------------------------------------------------------------------------

def _build_classification_prompt(filename: str, page_count: int, marked_text: str) -> str:
    return f"""You are an expert maritime document classifier specialising in ship technical documentation and PMS (Planned Maintenance System) data.

Filename: {filename}
Total pages: {page_count}

The document text below includes [PAGE N, doc_page=X] markers where:
- N       = physical PDF page position (used internally, do NOT use this in your answer)
- doc_page = the page number visibly printed in the document, or "none" if the page has no printed number

IMPORTANT: When reporting page numbers, always use the doc_page value (e.g. "9"), NOT the PDF position N.
Only include pages where doc_page is a number. Skip all pages marked doc_page=none — they have no printed page reference.

Document text:
---
{marked_text}
---

Classify this document into EXACTLY ONE of the following categories:

- **Instruction Manual**: Manufacturer's technical/operation/maintenance manual for a specific piece of equipment (contains operating procedures, maintenance schedules, overhaul instructions, spare parts lists, or equipment specifications). Even a short specification sheet for one piece of equipment counts as Instruction Manual if it describes a single equipment item in detail.
- **Machinery Particulars**: A list/register/inventory of ALL equipment on the vessel — tabular format with many rows, columns like No. | Equipment | Maker | Model | Serial No.
- **General Arrangement**: Deck plans, layout drawings showing spatial arrangement of the vessel.
- **Pipeline Diagrams/P&ID**: Piping & Instrumentation Diagrams, system flow diagrams, hydraulic schematics.
- **LSA/FFA Plans**: Life Saving Appliance plans, Fire Fighting Appliance plans, fire safety plans.
- **Tank Capacity Plan**: Tank tables, sounding tables, ullage tables, stability booklets.
- **Electrical Diagrams**: Single-line diagrams, wiring diagrams, cable lists.
- **Yard/Finished Drawings**: Shipyard construction drawings, as-built drawings.
- **Class Certificates/Surveys**: Classification certificates, survey reports, safety certificates.
- **Unknown/Unclassifiable**: Cannot determine category with reasonable confidence.

For each field below, list the EXACT page numbers (from [PAGE N] markers) where that content appears.
Use comma-separated individual page numbers — NOT ranges. E.g. "5, 6, 7, 12, 13" not "5-7, 12-13".

- **pages_with_components**: Pages that contain ALL THREE of the following together for at least one piece of equipment: (1) equipment/component NAME, (2) MAKER/MANUFACTURER name, and (3) MODEL number or type designation. Typically found on cover pages, name plate data pages, specification tables, or "Technical Data" sections. A page with just a description or just a table of procedures does NOT qualify — all three fields must be present on the same page. For Machinery Particulars, include pages that have rows with Name + Maker + Model columns. For Tank Capacity Plans, include pages with tank name + capacity + sounding data.
- **pages_with_jobs**: Pages containing maintenance schedules, service intervals, overhaul procedures, inspection checklists, lubrication schedules, or any periodic maintenance table. Look for headings: "Maintenance", "Service Schedule", "Periodic Inspection", "Overhaul", "Lubrication", tables with columns like "Interval | Task" or "Running Hours | Description".
- **pages_with_spares**: Pages containing spare parts lists, recommended spares, parts catalogues, or consumables lists. Look for headings: "Spare Parts", "Parts List", "Recommended Spares", tables with columns like "Part No. | Description | Qty" or drawing-based parts tables with item numbers.

Determine the supply type:
- **OEM**: The document is an Original Equipment Manufacturer manual — issued by the equipment maker (e.g. TAIKO KIKAI, Alfa Laval, MAN, Wärtsilä). Contains the maker's name/logo on the cover, model numbers, operation/maintenance procedures written by the manufacturer.
- **yard_supply**: The document comes from the shipyard's delivery package — a bundle of drawings, spare parts lists, or documentation assembled by the yard for the vessel build. Signs: hull number, ship name header, "SUPPLY" or "OUTFIT" columns (e.g. "Working Per Pump / Spare Per Ship"), multiple different equipment assemblies in one file, final drawings with part tables (item no. | description | qty | material), or Japanese/Korean shipyard format.

Return ONLY valid JSON in this exact format:
{{
  "category": "<category name exactly as listed above>",
  "confidence": <integer 0-100>,
  "useful_for_extraction": "<yes | partial | no>",
  "supply_type": "<OEM | yard_supply>",
  "pages_with_components": "<comma-separated doc_page numbers e.g. '1, 2, 9' — only pages with a printed doc_page number, empty string if none>",
  "pages_with_jobs": "<comma-separated doc_page numbers e.g. '9, 12, 13' — only pages with a printed doc_page number, empty string if none>",
  "pages_with_spares": "<comma-separated doc_page numbers e.g. '15, 16' — only pages with a printed doc_page number, empty string if none>",
  "reasoning": "<one sentence explanation>"
}}

Rules:
- CRITICAL: Use ONLY doc_page values from the markers — never use the PDF position N. Never invent a number not seen in a doc_page marker.
- CRITICAL: Skip pages marked doc_page=none — they carry no printed page reference and must NOT appear in your output.
- List every individual doc_page number where that content appears — do NOT use ranges or hyphens
- pages_with_components STRICT RULE: only include a page if it has name + maker + model all present together. Do NOT include pages that only mention the equipment name without maker/model. Do NOT include procedure pages, general description pages, or drawing pages just because they reference equipment.
- useful_for_extraction = "yes" if Instruction Manual, Machinery Particulars, OR Tank Capacity Plan
- useful_for_extraction = "partial" if spec sheet with maker/model but no maintenance section
- useful_for_extraction = "no" if purely drawings, certificates, P&IDs, or LSA/FFA plans
- supply_type = "OEM" for manufacturer-issued manuals; "yard_supply" for shipyard-assembled bundles, outfit drawings, or delivery documentation with hull/ship references
- confidence 85-98: very clear; 65-84: probable; 40-64: uncertain; <40: use Unknown/Unclassifiable
- Machinery Particulars vs Instruction Manual: one equipment in depth → Instruction Manual; many equipment rows → Machinery Particulars
- Be thorough — scan ALL pages. Maintenance schedules are often in the middle or later chapters. Spare parts are often in the last chapter or appendix.
- If a section is genuinely absent, return empty string — do NOT invent page numbers"""


def _classify_with_gemini(pages_text: list[str], filename: str, page_count: int) -> Optional[dict]:
    """Call Gemini API (free tier) via HTTP. Returns parsed JSON or None on failure."""
    try:
        import httpx
        from app.core.config import settings

        if not settings.GEMINI_API_KEY:
            return None

        marked_text, valid_doc_pages = _make_marked_text(pages_text, max_chars=80_000)
        non_empty = sum(1 for p in pages_text if p.strip())
        _log.info(
            "classifier[gemini]: %s — pages=%d non_empty=%d text_chars=%d printed_pages=%s",
            filename, page_count, non_empty, len(marked_text), sorted(valid_doc_pages),
        )

        prompt = _build_classification_prompt(filename, page_count, marked_text)
        url = (
            "https://generativelanguage.googleapis.com/v1beta/models/"
            f"gemini-2.0-flash-lite:generateContent?key={settings.GEMINI_API_KEY}"
        )
        payload = {"contents": [{"parts": [{"text": prompt}]}]}

        import time
        for attempt in range(3):
            response = httpx.post(url, json=payload, timeout=120)
            if response.status_code == 429:
                wait = 30 * (attempt + 1)  # 30s, 60s, 90s
                _log.warning("classifier[gemini]: 429 rate limit for %s — retrying in %ds", filename, wait)
                time.sleep(wait)
                continue
            response.raise_for_status()
            break
        else:
            response.raise_for_status()
        data = response.json()
        raw = data["candidates"][0]["content"]["parts"][0]["text"].strip()

        _log.info("classifier[gemini]: raw response for %s: %s", filename, raw[:300])
        if "```" in raw:
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        parsed = json.loads(raw.strip())
        # Filter page fields to only printed page numbers seen in the document
        if valid_doc_pages:
            for field in ("pages_with_components", "pages_with_jobs", "pages_with_spares"):
                parsed[field] = _filter_to_valid_pages(parsed.get(field, ""), valid_doc_pages)
        _log.info(
            "classifier[gemini]: %s → category=%s confidence=%s jobs=%s spares=%s",
            filename,
            parsed.get("category"),
            parsed.get("confidence"),
            parsed.get("pages_with_jobs"),
            parsed.get("pages_with_spares"),
        )
        return parsed

    except Exception as exc:
        # Redact API key from error message before logging
        _log.warning("classifier: Gemini call failed for %s: %s", filename, str(exc).replace(settings.GEMINI_API_KEY, "***") if settings.GEMINI_API_KEY else exc)
        return None


# ---------------------------------------------------------------------------
# Public interface
# ---------------------------------------------------------------------------

# Categories that cannot contain maintenance jobs or spare parts
_NO_JOB_SPARE_CATEGORIES = {
    "General Arrangement",
    "Pipeline Diagrams/P&ID",
    "LSA/FFA Plans",
    "Electrical Diagrams",
    "Yard/Finished Drawings",
    "Class Certificates/Surveys",
    "Unknown/Unclassifiable",
}

# Categories that CAN have component pages (tanks, equipment lists etc.)
_HAS_COMPONENTS_CATEGORIES = {
    "Instruction Manual",
    "Machinery Particulars",
    "Tank Capacity Plan",  # tanks listed in capacity plan are components
}


def _clamp_pages(page_str: str, max_page: int) -> str:
    """
    Remove any page numbers from a comma-separated string that exceed max_page.
    This prevents AI hallucination of page numbers beyond the actual document length.
    """
    if not page_str or not max_page:
        return page_str
    valid: list[str] = []
    for token in page_str.split(","):
        token = token.strip()
        if not token:
            continue
        try:
            n = int(token)
            if 1 <= n <= max_page:
                valid.append(str(n))
            else:
                _log.warning("classifier: dropping out-of-range page %d (max=%d)", n, max_page)
        except ValueError:
            pass  # skip non-numeric tokens
    return ", ".join(valid)


def _sanitise_result(result: ClassificationResult) -> ClassificationResult:
    """Force page ranges to empty string where they cannot logically exist,
    and clamp page numbers to the actual document length."""
    if result.category in _NO_JOB_SPARE_CATEGORIES:
        result.pages_with_jobs = ""
        result.pages_with_spares = ""
    if result.category not in _HAS_COMPONENTS_CATEGORIES:
        result.pages_with_components = ""
    # Tank Capacity Plan never has jobs or spares
    if result.category == "Tank Capacity Plan":
        result.pages_with_jobs = ""
        result.pages_with_spares = ""
        # Tanks ARE components — override AI if it said no
        result.useful_for_extraction = "yes"
    # _clamp_pages is a last-resort safety net for the keyword fallback path
    # (AI paths already filter via _filter_to_valid_pages inside each classifier)
    if result.page_count:
        result.pages_with_components = _clamp_pages(result.pages_with_components, result.page_count)
        result.pages_with_jobs = _clamp_pages(result.pages_with_jobs, result.page_count)
        result.pages_with_spares = _clamp_pages(result.pages_with_spares, result.page_count)
    return result


def classify_pdf(content: bytes, filename: str) -> ClassificationResult:
    """
    Classify a PDF manual.
    Priority: Gemini (free) → Claude (paid) → keyword fallback.
    """
    pages_text, total_pages = _extract_pdf_text(content)
    _log.info("classifier: extracted %d pages from %s (%d bytes)", total_pages, filename, len(content))

    # Try Groq first (free, 30 RPM) → Gemini → Claude → keyword fallback
    ai_result = _classify_with_groq(pages_text, filename, total_pages)
    if not ai_result:
        ai_result = _classify_with_gemini(pages_text, filename, total_pages)
    if not ai_result:
        ai_result = _classify_with_claude(pages_text, filename, total_pages)
    if ai_result:
        category = ai_result.get("category", "Unknown/Unclassifiable")
        if category not in VALID_CATEGORIES:
            category = "Unknown/Unclassifiable"
        ai_confidence = max(0, min(100, int(ai_result.get("confidence", 60))))

        # If AI is uncertain, also run keyword classifier and pick the better result
        if category == "Unknown/Unclassifiable" or ai_confidence < 50:
            kw = _keyword_classify(pages_text, filename, total_pages)
            if kw.category != "Unknown/Unclassifiable" and kw.confidence >= ai_confidence:
                _log.info(
                    "classifier: AI returned %s (%d%%) — keyword classifier wins with %s (%d%%)",
                    category, ai_confidence, kw.category, kw.confidence,
                )
                return _sanitise_result(kw)

        raw_supply = ai_result.get("supply_type", "OEM")
        supply_type = raw_supply if raw_supply in ("OEM", "yard_supply") else "OEM"
        result = ClassificationResult(
            category=category,
            confidence=ai_confidence,
            useful_for_extraction=ai_result.get("useful_for_extraction", "partial"),
            pages_with_components=ai_result.get("pages_with_components", ""),
            pages_with_jobs=ai_result.get("pages_with_jobs", ""),
            pages_with_spares=ai_result.get("pages_with_spares", ""),
            page_count=total_pages,
            supply_type=supply_type,
        )
        final = _sanitise_result(result)
        _log.info(
            "classifier: FINAL %s → cat=%s jobs=%r spares=%r components=%r",
            filename, final.category, final.pages_with_jobs, final.pages_with_spares, final.pages_with_components,
        )
        return final

    # Fallback: keyword matching
    return _sanitise_result(_keyword_classify(pages_text, filename, total_pages))


def _keyword_classify(pages_text: list[str], filename: str, total_pages: int) -> ClassificationResult:
    full_text = "\n".join(pages_text[:10])
    combined = (filename + " " + full_text).lower()

    best_category = "Unknown/Unclassifiable"
    best_score = 0
    best_base_conf = 50

    for category, keywords, base_conf in CATEGORY_RULES:
        score = sum(1 for kw in keywords if kw in combined)
        if score > best_score:
            best_score = score
            best_category = category
            best_base_conf = base_conf

    confidence = 40 if best_score == 0 else min(95, best_base_conf + best_score * 2)

    useful_categories = {"Instruction Manual", "Machinery Particulars",
                         "Pipeline Diagrams/P&ID", "Tank Capacity Plan"}
    partial_categories = {"General Arrangement", "Electrical Diagrams",
                          "Yard/Finished Drawings", "Class Certificates/Surveys"}
    if best_category in useful_categories:
        useful = "yes"
    elif best_category in partial_categories:
        useful = "partial"
    else:
        useful = "no"

    pages_components = _find_pages_for_topic(pages_text, EXTRACTION_KEYWORDS["components"])
    pages_jobs = _find_pages_for_topic(pages_text, EXTRACTION_KEYWORDS["jobs"])
    pages_spares = _find_pages_for_topic(pages_text, EXTRACTION_KEYWORDS["spares"])

    if total_pages > 0:
        if not pages_components:
            pages_components = f"1-{min(total_pages, 20)}"
        if not pages_jobs:
            pages_jobs = f"1-{total_pages}"
        if not pages_spares:
            pages_spares = f"1-{total_pages}"

    return ClassificationResult(
        category=best_category,
        confidence=confidence,
        useful_for_extraction=useful,
        pages_with_components=pages_components,
        pages_with_jobs=pages_jobs,
        pages_with_spares=pages_spares,
        page_count=total_pages,
    )
