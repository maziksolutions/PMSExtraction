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
    pages_with_components_printed: str
    pages_with_jobs_printed: str
    pages_with_spares_printed: str
    pages_with_components_physical: str
    pages_with_jobs_physical: str
    pages_with_spares_physical: str
    page_explanations: str
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

                # If no searchable text is extracted, try OCR on the footer to capture page numbers.
                if not parts:
                    try:
                        import pytesseract  # type: ignore
                        from PIL import Image  # type: ignore

                        page_image = page.to_image(resolution=200).original
                        w, h = page_image.size
                        footer_crop = page_image.crop((0, int(h * 0.7), w, h))
                        ocr_text = pytesseract.image_to_string(footer_crop, config='--psm 6').strip()
                        if ocr_text:
                            parts.append(ocr_text)
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

    # If there are no printed page numbers, fall back to physical indices for
    # mapping so page ranges are not dropped entirely.
    resolved: list[int] = [
        n if n is not None else i
        for i, n in enumerate(printed_nums, start=1)
    ]

    if not detected:
        _log.info("classifier: no printed page numbers detected — using physical page numbers as fallback")

    parts: list[str] = []
    total = 0
    valid_doc_pages: set[int] = detected if detected else set(resolved)
    for i, (text, dp) in enumerate(zip(pages_text, resolved), start=1):
        truncated = text[:800] if text else ""
        marker = f"[PAGE {i}, doc_page={dp}]"
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
    If valid_doc_pages is empty, fall back to returning original numbers so we don't lose all pages.
    """
    if not page_str:
        return ""
    if not valid_doc_pages:
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
                _log.warning("classifier: dropping page %d — not a validated doc page (valid: %s)",
                             n, sorted(valid_doc_pages)[:15])
        except ValueError:
            pass
    return ", ".join(kept)


# ---------------------------------------------------------------------------
# Programmatic page-scanning patterns (hybrid approach)
# AI determines category; these patterns scan page text for page fields.
# ---------------------------------------------------------------------------

# Maker / manufacturer signals on a page
_MAKER_RE = re.compile(
    r'(?:maker|manufacturer|manufactured\s+by|mfr\.?|made\s+by)\s*[:\-]'
    r'|\b(?:CO\.\s*,?\s*LTD\.?|INDUSTRIES|ENGINEERING|MARINE|CORPORATION|CORP\.?|INC\.?|GmbH|A/S)\b',
    re.IGNORECASE,
)

# Model / type code signals on a page
_MODEL_CODE_RE = re.compile(
    r'\b(?:model|type|model\s*no\.?|type\s*no\.?|series)\s*[:\-]?\s*[A-Z0-9]'
    r'|\b[A-Z]{1,5}[-]\d{2,6}[A-Za-z]{0,3}\b',
    re.IGNORECASE,
)

# Maintenance-job signals (intervals, schedules)
_JOB_RE = re.compile(
    r'\b(?:daily|weekly|monthly|quarterly|annually?' 
    r'|every\s+\d+\s*(?:running\s+)?hours?' 
    r'|\d[\d,]*\s*(?:running\s+)?hours?\s*(?:interval|period)?' 
    r'|maintenance\s+schedule|service\s+interval' 
    r'|periodic\s+(?:maintenance|inspection|service)' 
    r'|routine\s+maintenance|overhaul|servicing' 
    r'|check(?:-|\s+)?list|inspection\s+(?:list|schedule)|lubrication\s+(?:chart|schedule))\b',
    re.IGNORECASE,
)

# Spare-parts list signals
_SPARE_RE = re.compile(
    r'\b(?:spare\s+parts?(?:\s+list)?|recommended\s+spares?' 
    r'|parts?\s+(?:list|catalogue|catalog)|spare\s+list|consumables?\s+list' 
    r'|replacement\s+parts?|parts?\s+catalog(?:ue)?|service\s+parts?)\b',
    re.IGNORECASE,
)

# Yard-drawing parts-table signals (item numbers, bill of materials, etc.)
_YARD_PARTS_RE = re.compile(
    r'\b(?:item\s+no\.?|drawing\s+no\.?|dwg\.?\s*no\.?'
    r'|parts?\s+list|bill\s+of\s+materials?|assembly\s+(?:drawing|list)'
    r'|outfit\s+(?:list|drawing)|spare\s+per|part\s+number|description|qty|quantity)\b',
    re.IGNORECASE,
)


def _resolve_pages(pages_text: list[str]) -> list[int]:
    """Return the resolved doc_page number (printed or physical fallback) for each page."""
    printed = [_detect_printed_page_num(text) for text in pages_text]
    return [n if n is not None else i for i, n in enumerate(printed, start=1)]


def _scan_pages(
    pages_text: list[str], resolved_pages: list[int], category: str
) -> tuple[str, str, str, str, str, str, str]:
    """
    Programmatically detect pages_with_components, pages_with_jobs, pages_with_spares
    using regex patterns appropriate for the document category.

    Returns tuple:
      (components, jobs, spares,
       components_physical, jobs_physical, spares_physical,
       page_explanation_json)
    """
    comp_pages: list[str] = []
    job_pages: list[str] = []
    spare_pages: list[str] = []

    comp_phys: list[str] = []
    job_phys: list[str] = []
    spare_phys: list[str] = []

    page_reasons: dict[int, list[str]] = {}

    for physical_num, (text, doc_page) in enumerate(zip(pages_text, resolved_pages), start=1):
        if not text:
            continue

        printed_page = _detect_printed_page_num(text)
        reason_list: list[str] = []

        # --- Components ---
        comp_detected = False
        if category in ("Instruction Manual", "Machinery Particulars"):
            if _MAKER_RE.search(text) and _MODEL_CODE_RE.search(text):
                comp_detected = True
                reason_list.append("Maker + model text detected")
        elif category == "Yard/Finished Drawings":
            if _YARD_PARTS_RE.search(text):
                comp_detected = True
                reason_list.append("Drawing parts table layout detected")
        elif category == "Tank Capacity Plan":
            tl = text.lower()
            if "tank" in tl and any(kw in tl for kw in ("capacity", "sounding", "ullage", "volume", "m³", "m3", "liters", "ltr", "tonnes", "tons")):
                comp_detected = True
                reason_list.append("Tank capacity terminology detected")

        if comp_detected:
            comp_pages.append(str(doc_page))
            comp_phys.append(str(physical_num))

        # --- Jobs (Instruction Manual only) ---
        job_detected = False
        if category == "Instruction Manual" and _JOB_RE.search(text):
            job_detected = True
            reason_list.append("Maintenance/job interval text detected")
            job_pages.append(str(doc_page))
            job_phys.append(str(physical_num))

        # --- Spares (Instruction Manual + Yard/Finished Drawings) ---
        spare_detected = False
        if category in ("Instruction Manual", "Yard/Finished Drawings") and _SPARE_RE.search(text):
            spare_detected = True
            reason_list.append("Spare parts section text detected")
            spare_pages.append(str(doc_page))
            spare_phys.append(str(physical_num))

        if reason_list:
            page_reasons[physical_num] = reason_list

    # Fallback: if no explicit pages found, use broader keyword scan by page.
    if not comp_pages and category in ("Instruction Manual", "Machinery Particulars", "Tank Capacity Plan", "Yard/Finished Drawings"):
        candidate_pages = _find_pages_for_topic(
            pages_text,
            EXTRACTION_KEYWORDS["components"] + ["specification", "table", "parts", "item no", "model", "type"]
        )
        if candidate_pages:
            if isinstance(candidate_pages, str):
                candidates = [int(p.strip()) for p in candidate_pages.split(",") if p.strip()]
            else:
                candidates = candidate_pages
            for dp in candidates:
                comp_pages.append(str(dp))
                # For physical fallback, use doc_page as physical when no printed detected.
                comp_phys.append(str(dp))
                page_reasons.setdefault(dp, []).append("Fallback component keyword match")

    if category == "Instruction Manual" and not job_pages:
        candidate_pages = _find_pages_for_topic(
            pages_text,
            EXTRACTION_KEYWORDS["jobs"] + ["schedule", "interval", "inspection", "maintenance", "service"]
        )
        if candidate_pages:
            if isinstance(candidate_pages, str):
                candidates = [int(p.strip()) for p in candidate_pages.split(",") if p.strip()]
            else:
                candidates = candidate_pages
            for dp in candidates:
                job_pages.append(str(dp))
                job_phys.append(str(dp))
                page_reasons.setdefault(dp, []).append("Fallback job keyword match")

    if category in ("Instruction Manual", "Yard/Finished Drawings") and not spare_pages:
        candidate_pages = _find_pages_for_topic(
            pages_text,
            EXTRACTION_KEYWORDS["spares"] + ["parts list", "bom", "bill of materials", "catalog", "recommended spares"]
        )
        if candidate_pages:
            if isinstance(candidate_pages, str):
                candidates = [int(p.strip()) for p in candidate_pages.split(",") if p.strip()]
            else:
                candidates = candidate_pages
            for dp in candidates:
                spare_pages.append(str(dp))
                spare_phys.append(str(dp))
                page_reasons.setdefault(dp, []).append("Fallback spare keyword match")

    _log.info(
        "classifier[scan]: category=%s comps=%s jobs=%s spares=%s comp_phys=%s jobs_phys=%s spares_phys=%s",
        category, comp_pages, job_pages, spare_pages, comp_phys, job_phys, spare_phys,
    )

    comp_pages_str = ", ".join(sorted(set(comp_pages), key=lambda x:int(x))) if comp_pages else ""
    job_pages_str = ", ".join(sorted(set(job_pages), key=lambda x:int(x))) if job_pages else ""
    spare_pages_str = ", ".join(sorted(set(spare_pages), key=lambda x:int(x))) if spare_pages else ""

    comp_phys_str = ", ".join(sorted(set(comp_phys), key=lambda x:int(x))) if comp_phys else ""
    job_phys_str = ", ".join(sorted(set(job_phys), key=lambda x:int(x))) if job_phys else ""
    spare_phys_str = ", ".join(sorted(set(spare_phys), key=lambda x:int(x))) if spare_phys else ""

    reasons_json = json.dumps({str(k): v for k, v in page_reasons.items()}, ensure_ascii=False)
    return (
        comp_pages_str,
        job_pages_str,
        spare_pages_str,
        comp_phys_str,
        job_phys_str,
        spare_phys_str,
        reasons_json,
    )


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

        # Build marked text for Claude (category classification only — pages handled programmatically)
        marked_text, _ = _make_marked_text(pages_text, max_chars=80_000)

        non_empty = sum(1 for p in pages_text if p.strip())
        _log.info(
            "classifier[claude]: %s — pages=%d non_empty=%d text_chars=%d",
            filename, page_count, non_empty, len(marked_text),
        )

        prompt = _build_classification_prompt(filename, page_count, marked_text)

        model_id = getattr(settings, "CLAUDE_MODEL_ID", "claude-sonnet-4-6")
        message = client.messages.create(
            model=model_id,
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
        )

        raw = message.content[0].text.strip()
        _log.info("classifier[claude]: raw response for %s: %s", filename, raw[:300])
        if "```" in raw:
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        parsed = json.loads(raw.strip())
        _log.info(
            "classifier[claude]: %s → category=%s confidence=%s",
            filename, parsed.get("category"), parsed.get("confidence"),
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

        marked_text, _ = _make_marked_text(pages_text, max_chars=80_000)
        non_empty = sum(1 for p in pages_text if p.strip())
        _log.info(
            "classifier[groq]: %s — pages=%d non_empty=%d text_chars=%d",
            filename, page_count, non_empty, len(marked_text),
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
        _log.info(
            "classifier[groq]: %s → category=%s confidence=%s",
            filename, parsed.get("category"), parsed.get("confidence"),
        )
        return parsed

    except Exception as exc:
        _log.warning("classifier: Groq call failed for %s: %s", filename, exc)
        return None


# ---------------------------------------------------------------------------
# Gemini AI classifier (free tier)
# ---------------------------------------------------------------------------

def _build_classification_prompt(filename: str, page_count: int, marked_text: str) -> str:
    """Build a category and page identification prompt."""
    return f"""You are an expert maritime document classifier specialising in ship technical documentation and PMS (Planned Maintenance System) data.

Filename: {filename}
Total pages: {page_count}

Document text (page markers for context only):
---
{marked_text}
---

Classify this document into EXACTLY ONE of the following categories:

- **Instruction Manual**: OEM manufacturer's manual for a SINGLE piece of equipment — sequential written chapters covering operation, maintenance, troubleshooting, overhaul. Written by the equipment maker (e.g. TAIKO KIKAI, MAN, Wärtsilä). Contains prose/paragraph text.
- **Machinery Particulars**: Vessel-level tabular register of ALL equipment — many rows with columns: Equipment Name | Maker | Model | Serial No. | Capacity. Not focused on one machine.
- **General Arrangement**: Deck plans and layout drawings showing spatial arrangement of the vessel.
- **Pipeline Diagrams/P&ID**: Piping & Instrumentation Diagrams, system flow diagrams, hydraulic schematics.
- **LSA/FFA Plans**: Life Saving Appliance plans, Fire Fighting Appliance plans, fire safety plans, muster lists.
- **Tank Capacity Plan**: Tank tables, sounding tables, ullage tables, stability booklets, capacity plans.
- **Electrical Diagrams**: Single-line diagrams, wiring diagrams, cable lists, switchboard schematics.
- **Yard/Finished Drawings**: Shipyard delivery package — assembly drawings, outfit drawings, final construction drawings. Signs: engineering drawing format (title block, drawing number, revision table), item-numbered parts tables (Item No. | Description | Qty | Material), multiple equipment types bundled, hull/vessel name reference, spare parts lists attached to drawings. Keywords: "yard drawing", "final drawing", "construction drawing", "as-built", "outfit drawing", "spare per". Does NOT require written operational procedures. If the document is a "final drawing" or "yard drawing" for equipment like sewage treatment plant, classify here even if it has equipment details.
- **Class Certificates/Surveys**: Classification certificates, survey reports, safety certificates issued by DNV, Lloyd's, BV, ABS, etc.
- **Unknown/Unclassifiable**: Cannot determine category with reasonable confidence.

Additionally, identify pages containing:
- Components/Equipment: Pages with machinery, equipment lists, maker/model info, or component specifications. For Tank Capacity Plans, look for tank names and capacities. For Yard/Finished Drawings, look for parts tables with item numbers, descriptions, quantities.
- Jobs/Maintenance: Pages with maintenance schedules, service intervals, inspection checklists, or overhaul procedures. Typically in Instruction Manuals.
- Spares/Parts: Pages with spare parts lists, recommended spares, parts catalogs, or consumables. Can be in Instruction Manuals or Yard/Finished Drawings.

Return ONLY valid JSON in this exact format:
{{
  "category": "<category name exactly as listed above>",
  "confidence": <integer 0-100>,
  "useful_for_extraction": "<yes | partial | no>",
  "pages_with_components": "<comma-separated list of doc_page numbers, e.g. '1,3,5-7'>",
  "pages_with_jobs": "<comma-separated list of doc_page numbers>",
  "pages_with_spares": "<comma-separated list of doc_page numbers>",
  "reasoning": "<one sentence explanation>"
}}

Rules:
- confidence 85-98: very clear; 65-84: probable; 40-64: uncertain; <40 → Unknown/Unclassifiable
- useful_for_extraction = "yes" if Instruction Manual, Machinery Particulars, or Tank Capacity Plan
- useful_for_extraction = "partial" if spec sheet or drawing with some equipment data
- useful_for_extraction = "no" if purely drawings, certificates, P&IDs, or LSA/FFA plans
- Machinery Particulars vs Instruction Manual: one equipment in depth → Instruction Manual; many equipment rows → Machinery Particulars
- Yard/Finished Drawings: assembly/outfit drawings with parts tables from shipyard delivery — even if equipment names are present. Prioritize if filename contains "final drawing", "yard", "construction", or "as-built".. Prioritize if filename contains "final drawing", "yard", "construction", or "as-built".
- For pages: use the doc_page numbers from the [PAGE N, doc_page=X] markers. Only include pages that actually exist in the document. If no such pages, use empty string "".
- Page ranges can be expressed as 'start-end' (e.g. '45-67') or individual numbers separated by commas."""


def _classify_with_gemini(pages_text: list[str], filename: str, page_count: int) -> Optional[dict]:
    """Call Gemini API (free tier) via HTTP. Returns parsed JSON or None on failure."""
    try:
        import httpx
        from app.core.config import settings

        if not settings.GEMINI_API_KEY:
            return None

        marked_text, _ = _make_marked_text(pages_text, max_chars=80_000)
        non_empty = sum(1 for p in pages_text if p.strip())
        _log.info(
            "classifier[gemini]: %s — pages=%d non_empty=%d text_chars=%d",
            filename, page_count, non_empty, len(marked_text),
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
        _log.info(
            "classifier[gemini]: %s → category=%s confidence=%s",
            filename, parsed.get("category"), parsed.get("confidence"),
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
        result.pages_with_components_printed = _clamp_pages(result.pages_with_components_printed, result.page_count)
        result.pages_with_jobs_printed = _clamp_pages(result.pages_with_jobs_printed, result.page_count)
        result.pages_with_spares_printed = _clamp_pages(result.pages_with_spares_printed, result.page_count)
        result.pages_with_components_physical = _clamp_pages(result.pages_with_components_physical, result.page_count)
        result.pages_with_jobs_physical = _clamp_pages(result.pages_with_jobs_physical, result.page_count)
        result.pages_with_spares_physical = _clamp_pages(result.pages_with_spares_physical, result.page_count)
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
                # Still use programmatic scan for keyword-fallback category
                resolved = _resolve_pages(pages_text)
                components, jobs, spares = _scan_pages(pages_text, resolved, kw.category)
                kw.pages_with_components = components
                kw.pages_with_jobs = jobs
                kw.pages_with_spares = spares
                return _sanitise_result(kw)

        # Programmatic page scanning for printed/physical and explanations (always available)
        resolved = _resolve_pages(pages_text)
        scanned_comp, scanned_jobs, scanned_spares, scanned_comp_phys, scanned_jobs_phys, scanned_spares_phys, scanned_reasons = _scan_pages(pages_text, resolved, category)

        # Use AI-provided pages if available; fallback to programmatic results.
        marked_text, valid_doc_pages = _make_marked_text(pages_text, max_chars=80_000)
        ai_components = ai_result.get("pages_with_components", "").strip()
        ai_jobs = ai_result.get("pages_with_jobs", "").strip()
        ai_spares = ai_result.get("pages_with_spares", "").strip()

        if ai_components or ai_jobs or ai_spares:
            components = _filter_to_valid_pages(ai_components, valid_doc_pages)
            jobs = _filter_to_valid_pages(ai_jobs, valid_doc_pages)
            spares = _filter_to_valid_pages(ai_spares, valid_doc_pages)
            _log.info("classifier: using AI-identified pages: comp=%s jobs=%s spares=%s", components, jobs, spares)
        else:
            components = scanned_comp
            jobs = scanned_jobs
            spares = scanned_spares
            _log.info("classifier: using programmatic scan: comp=%s jobs=%s spares=%s", components, jobs, spares)

        result = ClassificationResult(
            category=category,
            confidence=ai_confidence,
            useful_for_extraction=ai_result.get("useful_for_extraction", "partial"),
            pages_with_components=components,
            pages_with_jobs=jobs,
            pages_with_spares=spares,
            pages_with_components_printed=scanned_comp if scanned_comp else "",
            pages_with_jobs_printed=scanned_jobs if scanned_jobs else "",
            pages_with_spares_printed=scanned_spares if scanned_spares else "",
            pages_with_components_physical=scanned_comp_phys,
            pages_with_jobs_physical=scanned_jobs_phys,
            pages_with_spares_physical=scanned_spares_phys,
            page_explanations=scanned_reasons,
            page_count=total_pages,
        )
        final = _sanitise_result(result)
        _log.info(
            "classifier: FINAL %s → cat=%s conf=%d components=%r jobs=%r spares=%r",
            filename, final.category, final.confidence,
            final.pages_with_components, final.pages_with_jobs, final.pages_with_spares,
        )
        return final

    # Fallback: keyword matching + programmatic page scan
    kw = _keyword_classify(pages_text, filename, total_pages)
    resolved = _resolve_pages(pages_text)
    components, jobs, spares, comp_phys, jobs_phys, spares_phys, reasons = _scan_pages(pages_text, resolved, kw.category)
    kw.pages_with_components = components
    kw.pages_with_jobs = jobs
    kw.pages_with_spares = spares
    kw.pages_with_components_printed = components
    kw.pages_with_jobs_printed = jobs
    kw.pages_with_spares_printed = spares
    kw.pages_with_components_physical = comp_phys
    kw.pages_with_jobs_physical = jobs_phys
    kw.pages_with_spares_physical = spares_phys
    kw.page_explanations = reasons
    return _sanitise_result(kw)


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
        pages_with_components_printed=pages_components,
        pages_with_jobs_printed=pages_jobs,
        pages_with_spares_printed=pages_spares,
        pages_with_components_physical=pages_components,
        pages_with_jobs_physical=pages_jobs,
        pages_with_spares_physical=pages_spares,
        page_explanations="",
        page_count=total_pages,
    )
