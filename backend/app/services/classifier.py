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
    - doc_page: printed page number found in the document text, or physical
                page number N when no printed numbers exist in the document.

    Returns (marked_text, valid_doc_pages) where valid_doc_pages is the set
    of reference page numbers to validate AI output against.
    """
    # First pass — detect printed page numbers for every page
    printed_nums: list[Optional[int]] = [
        _detect_printed_page_num(text) for text in pages_text
    ]
    detected = {n for n in printed_nums if n is not None}

    # If the document has no printed page numbers at all, fall back to physical
    # page positions so the AI can still reference pages meaningfully.
    if not detected:
        _log.info("classifier: no printed page numbers detected — using physical page positions")
        printed_nums = list(range(1, len(pages_text) + 1))
        detected = set(printed_nums)

    parts: list[str] = []
    total = 0
    valid_doc_pages: set[int] = set()
    for i, (text, dp) in enumerate(zip(pages_text, printed_nums), start=1):
        truncated = text[:800] if text else ""
        if dp is not None:
            valid_doc_pages.add(dp)
            marker = f"[PAGE {i}, doc_page={dp}]"
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

- **Instruction Manual**: OEM manufacturer's manual for a SINGLE piece of equipment — has sequential written chapters covering operation, maintenance, troubleshooting, overhaul. Written by the equipment maker (e.g. TAIKO KIKAI, MAN, Wärtsilä). Contains prose/paragraph text describing how to operate and service the equipment.
- **Machinery Particulars**: Vessel-level tabular register of ALL equipment — many rows with columns like No. | Equipment Name | Maker | Model | Serial No. | Capacity. Not focused on one machine.
- **General Arrangement**: Deck plans and layout drawings showing spatial arrangement of the vessel. Mostly drawings with minimal text.
- **Pipeline Diagrams/P&ID**: Piping & Instrumentation Diagrams, system flow diagrams, hydraulic schematics.
- **LSA/FFA Plans**: Life Saving Appliance plans, Fire Fighting Appliance plans, fire safety plans, muster lists.
- **Tank Capacity Plan**: Tank tables, sounding tables, ullage tables, stability booklets, capacity plans.
- **Electrical Diagrams**: Single-line diagrams, wiring diagrams, cable lists, switchboard schematics.
- **Yard/Finished Drawings**: Shipyard delivery package — assembly drawings, outfit drawings, final construction drawings. Key signs: engineering drawing format (title block, drawing number, revision table), assembly views with item-numbered parts tables (Item No. | Description | Qty | Material), multiple equipment types bundled, hull/vessel name reference, spare parts lists attached to drawings. Does NOT need written operational procedures. A document of assembly drawings with parts/spares lists from the shipyard is Yard/Finished Drawings even if it mentions equipment names.
- **Class Certificates/Surveys**: Classification certificates, survey reports, safety certificates issued by DNV, Lloyd's, BV, ABS, etc.
- **Unknown/Unclassifiable**: Cannot determine category with reasonable confidence.

For each field below, list the EXACT page numbers (from [PAGE N] markers) where that content appears.
Use comma-separated individual page numbers — NOT ranges. E.g. "5, 6, 7, 12, 13" not "5-7, 12-13".

- **pages_with_components**:
  - If category is **Instruction Manual** or **Machinery Particulars**: only pages that have ALL THREE — (1) equipment NAME, (2) MAKER/MANUFACTURER, and (3) MODEL number. Cover pages, name-plate data, "Technical Data" / "Specifications" tables.
  - If category is **Yard/Finished Drawings**: pages where any component or equipment name is visible — assembly drawings, parts lists with item numbers. No maker/model requirement.
  - If category is **Tank Capacity Plan**: pages with tank names + capacity or sounding data.
  - All other categories: leave empty.
- **pages_with_jobs**: Only for **Instruction Manuals**. Pages with maintenance schedules, service intervals, inspection checklists, lubrication — "Maintenance", "Service Schedule", "Periodic Inspection" headings, tables with "Interval | Task" or "Running Hours" columns. Leave empty for ALL other types.
- **pages_with_spares**: Only for **Instruction Manuals** and **Yard/Finished Drawings**. Pages with spare parts lists, recommended spares, consumables — "Spare Parts", "Parts List", "Recommended Spares", tables with "Part No. | Description | Qty". Leave empty for all other types.

Return ONLY valid JSON in this exact format:
{{
  "category": "<category name exactly as listed above>",
  "confidence": <integer 0-100>,
  "useful_for_extraction": "<yes | partial | no>",
  "pages_with_components": "<comma-separated doc_page numbers e.g. '1, 2, 9' — only pages with a printed doc_page number, empty string if none>",
  "pages_with_jobs": "<comma-separated doc_page numbers e.g. '9, 12, 13' — only pages with a printed doc_page number, empty string if none>",
  "pages_with_spares": "<comma-separated doc_page numbers e.g. '15, 16' — only pages with a printed doc_page number, empty string if none>",
  "reasoning": "<one sentence explanation>"
}}

Rules:
- CRITICAL: Use ONLY doc_page values from the markers — never use PDF position N. Never invent a number not seen as a doc_page value.
- CRITICAL: Skip pages marked doc_page=none — they have no printed page reference and must NOT appear in your output.
- List every individual doc_page number where the content appears — do NOT use ranges or hyphens
- pages_with_jobs must be empty for everything except Instruction Manual
- pages_with_spares must be empty for everything except Instruction Manual and Yard/Finished Drawings
- useful_for_extraction = "yes" if Instruction Manual OR Machinery Particulars
- useful_for_extraction = "partial" if spec sheet or drawing with some equipment data
- useful_for_extraction = "no" if purely drawings, plans, certificates, P&IDs with no equipment data
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

- **Instruction Manual**: OEM manufacturer's manual for a SINGLE piece of equipment — has sequential written chapters covering operation, maintenance, troubleshooting, overhaul. Written by the equipment maker (e.g. TAIKO KIKAI, MAN, Wärtsilä). Contains prose/paragraph text describing how to operate and service the equipment.
- **Machinery Particulars**: Vessel-level tabular register of ALL equipment — many rows with columns like No. | Equipment Name | Maker | Model | Serial No. | Capacity. Not focused on one machine.
- **General Arrangement**: Deck plans and layout drawings showing spatial arrangement. Mostly drawings with minimal text.
- **Pipeline Diagrams/P&ID**: Piping & Instrumentation Diagrams, system flow diagrams, hydraulic schematics.
- **LSA/FFA Plans**: Life Saving Appliance plans, Fire Fighting Appliance plans, fire safety plans, muster lists.
- **Tank Capacity Plan**: Tank tables, sounding tables, ullage tables, stability booklets, capacity plans.
- **Electrical Diagrams**: Single-line diagrams, wiring diagrams, cable lists, switchboard schematics.
- **Yard/Finished Drawings**: Shipyard delivery package — assembly drawings, outfit drawings, final construction drawings. Key signs: engineering drawing format (title block, drawing number, revision table, scale), assembly views with item-numbered parts tables (Item No. | Description | Qty | Material), multiple equipment types bundled together, hull/vessel name reference, spare parts lists attached to drawings. Does NOT need to contain written operational procedures. A document of assembly drawings with attached parts/spares lists from the shipyard is Yard/Finished Drawings even if it mentions equipment names.
- **Class Certificates/Surveys**: Classification certificates, survey reports, safety certificates issued by DNV, Lloyd's, BV, ABS, etc.
- **Unknown/Unclassifiable**: Cannot determine category with reasonable confidence.

For each field below, list the EXACT page numbers (from [PAGE N] markers) where that content appears.
Use comma-separated individual page numbers — NOT ranges. E.g. "5, 6, 7, 12, 13" not "5-7, 12-13".

- **pages_with_components**:
  - If category is **Instruction Manual** or **Machinery Particulars**: only include a page if it has ALL THREE together — (1) equipment NAME, (2) MAKER/MANUFACTURER, and (3) MODEL number. Typically cover pages, name-plate data pages, "Technical Data" or "Specifications" tables.
  - If category is **Yard/Finished Drawings**: include pages where any component or equipment name is visible — assembly drawings, parts lists with item numbers, outfit lists. No maker/model requirement.
  - If category is **Tank Capacity Plan**: include pages with tank names + capacity or sounding data.
  - All other categories: leave empty.
- **pages_with_jobs**: Only populate for **Instruction Manuals**. Pages with maintenance schedules, service intervals, inspection checklists, lubrication schedules — headings like "Maintenance", "Service Schedule", "Periodic Inspection", tables with "Interval | Task" or "Running Hours | Description" columns. Leave empty for ALL other document types.
- **pages_with_spares**: Only populate for **Instruction Manuals** and **Yard/Finished Drawings**. Pages with spare parts lists, recommended spares, consumables — headings "Spare Parts", "Parts List", "Recommended Spares", tables with "Part No. | Description | Qty". Leave empty for all other document types.

Return ONLY valid JSON in this exact format:
{{
  "category": "<category name exactly as listed above>",
  "confidence": <integer 0-100>,
  "useful_for_extraction": "<yes | partial | no>",
  "pages_with_components": "<comma-separated doc_page numbers e.g. '1, 2, 9' — only pages with a printed doc_page number, empty string if none>",
  "pages_with_jobs": "<comma-separated doc_page numbers e.g. '9, 12, 13' — only pages with a printed doc_page number, empty string if none>",
  "pages_with_spares": "<comma-separated doc_page numbers e.g. '15, 16' — only pages with a printed doc_page number, empty string if none>",
  "reasoning": "<one sentence explanation>"
}}

Rules:
- CRITICAL: Use ONLY doc_page values from the markers — never use the PDF position N. Never invent a number not seen in a doc_page marker.
- CRITICAL: Skip pages marked doc_page=none — they carry no printed page reference and must NOT appear in your output.
- List every individual doc_page number where that content appears — do NOT use ranges or hyphens
- pages_with_jobs must be empty for everything except Instruction Manual
- pages_with_spares must be empty for everything except Instruction Manual and Yard/Finished Drawings
- useful_for_extraction = "yes" if Instruction Manual, Machinery Particulars, OR Tank Capacity Plan
- useful_for_extraction = "partial" if spec sheet with maker/model but no maintenance section
- useful_for_extraction = "no" if purely drawings, certificates, P&IDs, or LSA/FFA plans
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

# Only Instruction Manuals have maintenance jobs
_HAS_JOBS_CATEGORIES = {
    "Instruction Manual",
}

# Instruction Manuals and Yard/Finished Drawings can reference spare parts
_HAS_SPARES_CATEGORIES = {
    "Instruction Manual",
    "Yard/Finished Drawings",
}

# Categories that CAN have component pages
_HAS_COMPONENTS_CATEGORIES = {
    "Instruction Manual",
    "Machinery Particulars",
    "Tank Capacity Plan",
    "Yard/Finished Drawings",  # assembly drawings reference equipment/components
}

# supply_type is rule-based — not AI-determined
# Instruction Manuals are issued by the OEM; Class Certificates by the class society (not yard)
_OEM_CATEGORIES = {
    "Instruction Manual",
    "Class Certificates/Surveys",
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
    """Apply category-based rules to page fields and supply_type."""
    # Jobs exist only in Instruction Manuals
    if result.category not in _HAS_JOBS_CATEGORIES:
        result.pages_with_jobs = ""

    # Spares exist only in Instruction Manuals and Yard/Finished Drawings
    if result.category not in _HAS_SPARES_CATEGORIES:
        result.pages_with_spares = ""

    # Components only in relevant categories
    if result.category not in _HAS_COMPONENTS_CATEGORIES:
        result.pages_with_components = ""

    # Tank Capacity Plan: tanks are components, force useful=yes
    if result.category == "Tank Capacity Plan":
        result.useful_for_extraction = "yes"

    # supply_type is determined by category rule, never left to AI guessing
    result.supply_type = "OEM" if result.category in _OEM_CATEGORIES else "yard_supply"

    # _clamp_pages: last-resort safety for keyword fallback path
    # (AI paths already filtered via _filter_to_valid_pages inside each classifier)
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
