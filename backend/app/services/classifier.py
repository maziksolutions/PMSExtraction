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


@dataclass(frozen=True)
class PageReference:
    physical: int
    printed: Optional[int]


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


# Matches a standalone page number line: "9", "- 9 -", "â€“ 9 â€“"
_PAGE_NUM_RE = re.compile(r'^[-â€“]?\s*(\d{1,4})\s*[-â€“]?$')
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


def _parse_page_tokens(page_str: str) -> list[int]:
    """Parse references like '1, 3-5, 9' into sorted page numbers."""
    if not page_str:
        return []

    pages: set[int] = set()
    for token in page_str.split(","):
        token = token.strip()
        if not token:
            continue
        if "-" in token:
            start_str, end_str = token.split("-", 1)
            try:
                start = int(start_str.strip())
                end = int(end_str.strip())
            except ValueError:
                continue
            if start > end:
                start, end = end, start
            pages.update(range(start, end + 1))
            continue
        try:
            pages.add(int(token))
        except ValueError:
            continue
    return sorted(p for p in pages if p > 0)


def _format_page_tokens(pages: list[int]) -> str:
    ordered = sorted(set(pages))
    if not ordered:
        return ""

    ranges: list[str] = []
    start = end = ordered[0]
    for page in ordered[1:]:
        if page == end + 1:
            end = page
            continue
        ranges.append(f"{start}-{end}" if start != end else str(start))
        start = end = page
    ranges.append(f"{start}-{end}" if start != end else str(start))
    return ", ".join(ranges)


def _build_page_references(pages_text: list[str]) -> list[PageReference]:
    return [
        PageReference(physical=index, printed=_detect_printed_page_num(text))
        for index, text in enumerate(pages_text, start=1)
    ]


def _refs_from_physical_pages(
    physical_pages: list[int],
    page_refs: list[PageReference],
) -> tuple[str, str]:
    ordered_physical = sorted({p for p in physical_pages if 1 <= p <= len(page_refs)})
    printed_pages = [
        page_refs[p - 1].printed
        for p in ordered_physical
        if page_refs[p - 1].printed is not None
    ]
    return _format_page_tokens([p for p in printed_pages if p is not None]), _format_page_tokens(ordered_physical)


def _upsert_page_reason(
    page_reasons: dict[int, dict[str, object]],
    physical_page: int,
    printed_page: Optional[int],
    section: str,
    reason: str,
) -> None:
    entry = page_reasons.setdefault(
        physical_page,
        {
            "printed_page": printed_page,
            "reference": [],
            "components": [],
            "jobs": [],
            "spares": [],
        },
    )
    entry["printed_page"] = printed_page

    reference_reasons = entry["reference"]
    assert isinstance(reference_reasons, list)
    reference_note = (
        f"Printed page {printed_page} detected in the document footer/header."
        if printed_page is not None
        else "No printed page number detected on this PDF page."
    )
    if reference_note not in reference_reasons:
        reference_reasons.append(reference_note)

    section_reasons = entry[section]
    assert isinstance(section_reasons, list)
    if reason not in section_reasons:
        section_reasons.append(reason)


def _make_marked_text(pages_text: list[str], max_chars: int = 400_000) -> tuple[str, set[int]]:
    """Build [PAGE physical, printed_page=X] markers for AI classification."""
    page_refs = _build_page_references(pages_text)
    if not any(ref.printed is not None for ref in page_refs):
        _log.info("classifier: no printed page numbers detected Ã¢â‚¬â€ using physical page numbers as fallback")

    parts: list[str] = []
    total = 0
    valid_physical_pages = {ref.physical for ref in page_refs}
    for ref, text in zip(page_refs, pages_text):
        truncated = text[:800] if text else ""
        printed_label = ref.printed if ref.printed is not None else "none"
        marker = f"[PAGE {ref.physical}, printed_page={printed_label}]"
        snippet = f"{marker}\n{truncated}" if truncated else marker
        total += len(snippet)
        parts.append(snippet)
        if total >= max_chars:
            _log.warning("classifier: document truncated at page %d (>%d chars)", ref.physical, max_chars)
            break
    return "\n\n".join(parts), valid_physical_pages


def _filter_to_valid_pages(page_str: str, valid_pages: set[int]) -> str:
    """Keep only page references that actually exist in the document."""
    if not page_str:
        return ""
    if not valid_pages:
        return page_str
    parsed = _parse_page_tokens(page_str)
    kept = [page for page in parsed if page in valid_pages]
    for page in sorted(set(parsed) - set(kept)):
        _log.warning(
            "classifier: dropping page %d Ã¢â‚¬â€ not a validated page reference (valid: %s)",
            page,
            sorted(valid_pages)[:15],
        )
    return _format_page_tokens(kept)


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


_COMPONENT_SPEC_RE = re.compile(
    r"\b(?:specification|technical data|principal particulars|type|model|maker|manufacturer|capacity|quantity|set/ship)\b",
    re.IGNORECASE,
)

_JOB_SECTION_RE = re.compile(
    r"\b(?:maintenance(?:\s+schedule)?|service(?:\s+interval)?|inspection(?:\s+schedule)?|overhaul|periodic maintenance|routine maintenance|lubrication)\b",
    re.IGNORECASE,
)

_JOB_CONTINUATION_RE = re.compile(
    r"\b(?:procedure|step|check|clean|replace|inspect|adjust|tighten|drain|grease|lubricate|remove|install|assemble|disassemble|running hours?)\b",
    re.IGNORECASE,
)

_SPARE_SECTION_RE = re.compile(
    r"\b(?:spare parts?|parts list|recommended spares?|spare part catalogue|bill of materials?|bom)\b",
    re.IGNORECASE,
)

_SPARE_CONTINUATION_RE = re.compile(
    r"\b(?:part|item|description|qty|quantity|material|drawing no|catalog|remarks?|position)\b",
    re.IGNORECASE,
)

_PROCEDURE_STEP_RE = re.compile(
    r"(?:^\s*\d+[.)]\s+\w+|\bstep\s+\d+\b|\bprocedure\b|\bwork\s+sequence\b)",
    re.IGNORECASE | re.MULTILINE,
)

_PARTS_TABLE_RE = re.compile(
    r"\b(?:item\s+no\.?|part\s+no\.?|description|qty|quantity|material|remarks?|catalog(?:ue)?|drawing\s+no\.?)\b",
    re.IGNORECASE,
)

_TANK_NAME_TERMS = (
    "tank",
    "ballast tank",
    "fuel oil tank",
    "diesel oil tank",
    "fresh water tank",
    "freshwater tank",
    "sludge tank",
    "bilge tank",
    "lube oil tank",
    "lubricating oil tank",
    "settling tank",
    "service tank",
    "cargo tank",
    "dirty oil tank",
    "overflow tank",
)

_TANK_CAPACITY_TERMS = (
    "capacity",
    "sounding",
    "ullage",
    "volume",
    "m3",
    "m^3",
    "cu.m",
    "cubic metre",
    "cubic meter",
    "litre",
    "liter",
    "ltr",
    "tonne",
    "tonnes",
    "tons",
)


def _keyword_hit_count(lower_text: str, keywords: tuple[str, ...] | list[str]) -> int:
    return sum(1 for keyword in keywords if keyword in lower_text)


def _is_table_like_page(text: str) -> bool:
    lower = text.lower()
    return text.count("|") >= 4 or "[table]" in lower


def _looks_like_instruction_component_page(text: str, physical_num: int) -> bool:
    lower = text.lower()
    title_hits = _keyword_hit_count(
        lower,
        (
            "instruction manual",
            "operation manual",
            "service manual",
            "technical data",
            "specification",
            "equipment",
            "machinery",
            "model",
            "maker",
            "manufacturer",
        ),
    )
    return (
        (_MAKER_RE.search(text) and _MODEL_CODE_RE.search(text))
        or (physical_num <= 4 and title_hits >= 2)
        or (physical_num <= 2 and _is_table_like_page(text) and _COMPONENT_SPEC_RE.search(text))
    )


def _looks_like_tank_component_page(text: str, physical_num: int) -> bool:
    lower = text.lower()
    tank_hits = _keyword_hit_count(lower, _TANK_NAME_TERMS)
    capacity_hits = _keyword_hit_count(lower, _TANK_CAPACITY_TERMS)
    title_hits = _keyword_hit_count(lower, ("tank capacity", "capacity plan", "sounding table", "ullage table"))
    return (
        (tank_hits >= 1 and capacity_hits >= 2)
        or (_is_table_like_page(text) and tank_hits >= 1 and capacity_hits >= 1)
        or (physical_num <= 2 and title_hits >= 1 and tank_hits >= 1)
    )


def _looks_like_spare_seed_page(text: str) -> bool:
    lower = text.lower()
    table_keyword_hits = _keyword_hit_count(
        lower,
        ("item no", "part no", "description", "qty", "quantity", "material", "catalog", "remarks"),
    )
    return bool(_SPARE_RE.search(text) or _SPARE_SECTION_RE.search(text)) or (
        _is_table_like_page(text) and table_keyword_hits >= 3
    )


def _looks_like_job_continuation(text: str) -> bool:
    lower = text.lower()
    keyword_hits = sum(
        1 for kw in ("maintenance", "service", "inspection", "procedure", "step", "running hour", "lubrication")
        if kw in lower
    )
    return keyword_hits >= 1 or bool(_JOB_CONTINUATION_RE.search(text)) or bool(_PROCEDURE_STEP_RE.search(text))


def _looks_like_spare_continuation(text: str) -> bool:
    lower = text.lower()
    keyword_hits = sum(
        1 for kw in ("spare", "part", "item", "qty", "quantity", "material", "catalog")
        if kw in lower
    )
    table_keyword_hits = _keyword_hit_count(
        lower,
        ("item no", "part no", "description", "qty", "quantity", "material", "catalog", "remarks"),
    )
    return (
        keyword_hits >= 2
        or bool(_SPARE_CONTINUATION_RE.search(text))
        or (_is_table_like_page(text) and table_keyword_hits >= 2)
    )


def _selected_physical_pages_from_ai(ai_result: Optional[dict], key: str, page_count: int) -> list[int]:
    if not ai_result:
        return []
    raw_pages = str(ai_result.get(key, "") or "").strip()
    filtered = _filter_to_valid_pages(raw_pages, set(range(1, page_count + 1)))
    return _parse_page_tokens(filtered)


def _merge_page_explanations(
    scanned_reasons: str,
    page_refs: list[PageReference],
    ai_pages_by_section: dict[str, list[int]],
) -> str:
    try:
        merged: dict[int, dict[str, object]] = {
            int(key): value
            for key, value in (json.loads(scanned_reasons or "{}") or {}).items()
            if str(key).isdigit()
        }
    except Exception:
        merged = {}

    for section, selected_pages in ai_pages_by_section.items():
        if not selected_pages:
            continue
        for physical_page in selected_pages:
            if physical_page < 1 or physical_page > len(page_refs):
                continue
            ref = page_refs[physical_page - 1]
            _upsert_page_reason(
                merged,
                physical_page,
                ref.printed,
                section,
                "AI screening selected this page from the document context and page markers.",
            )

    return json.dumps({str(key): value for key, value in sorted(merged.items())}, ensure_ascii=False)


def _expand_contiguous_section(
    seed_pages: set[int],
    pages_text: list[str],
    detector,
) -> set[int]:
    if not seed_pages:
        return set()

    expanded = set(seed_pages)
    for seed in sorted(seed_pages):
        idx = seed - 2
        while idx >= 0 and detector(pages_text[idx]):
            expanded.add(idx + 1)
            idx -= 1

        idx = seed
        while idx < len(pages_text) and detector(pages_text[idx]):
            expanded.add(idx + 1)
            idx += 1
    return expanded


def _scan_pages(
    pages_text: list[str], page_refs: list[PageReference], category: str
) -> tuple[str, str, str, str, str, str, str]:
    """Detect component/job/spare sections using physical PDF pages first."""
    comp_phys_pages: set[int] = set()
    job_phys_pages: set[int] = set()
    spare_phys_pages: set[int] = set()
    page_reasons: dict[int, dict[str, object]] = {}

    for ref, text in zip(page_refs, pages_text):
        if not text:
            continue

        physical_num = ref.physical
        printed_page = ref.printed
        lower_text = text.lower()

        if category in ("Instruction Manual", "Machinery Particulars"):
            if _looks_like_instruction_component_page(text, physical_num):
                comp_phys_pages.add(physical_num)
                _upsert_page_reason(page_reasons, physical_num, printed_page, "components", "Equipment identification, maker/model, or front-section specification details detected.")
        elif category == "Yard/Finished Drawings" and _YARD_PARTS_RE.search(text):
            comp_phys_pages.add(physical_num)
            _upsert_page_reason(page_reasons, physical_num, printed_page, "components", "Drawing parts table or bill-of-materials layout detected.")
        elif category == "Tank Capacity Plan":
            if _looks_like_tank_component_page(text, physical_num):
                comp_phys_pages.add(physical_num)
                _upsert_page_reason(page_reasons, physical_num, printed_page, "components", "Tank table, sounding, ullage, or capacity terminology detected.")

        if category == "Instruction Manual" and (
            _JOB_RE.search(text)
            or _JOB_SECTION_RE.search(text)
            or (_PROCEDURE_STEP_RE.search(text) and physical_num > 1)
        ):
            job_phys_pages.add(physical_num)
            _upsert_page_reason(page_reasons, physical_num, printed_page, "jobs", "Maintenance schedule, inspection, service, or overhaul text detected.")

        if category in ("Instruction Manual", "Yard/Finished Drawings") and _looks_like_spare_seed_page(text):
            spare_phys_pages.add(physical_num)
            _upsert_page_reason(page_reasons, physical_num, printed_page, "spares", "Spare-parts heading, parts list, or bill-of-materials text detected.")

    job_phys_pages = _expand_contiguous_section(job_phys_pages, pages_text, _looks_like_job_continuation)
    for physical_num in job_phys_pages:
        ref = page_refs[physical_num - 1]
        _upsert_page_reason(page_reasons, physical_num, ref.printed, "jobs", "Adjacent page kept inside the same maintenance/procedure section.")

    spare_phys_pages = _expand_contiguous_section(spare_phys_pages, pages_text, _looks_like_spare_continuation)
    for physical_num in spare_phys_pages:
        ref = page_refs[physical_num - 1]
        _upsert_page_reason(page_reasons, physical_num, ref.printed, "spares", "Adjacent page kept inside the same spare-parts/table section.")

    if not comp_phys_pages and category in ("Instruction Manual", "Machinery Particulars", "Tank Capacity Plan", "Yard/Finished Drawings"):
        for physical_num in _find_pages_for_topic(
            pages_text,
            EXTRACTION_KEYWORDS["components"] + ["specification", "table", "parts", "item no", "model", "type"],
        ):
            comp_phys_pages.add(physical_num)
            ref = page_refs[physical_num - 1]
            _upsert_page_reason(page_reasons, physical_num, ref.printed, "components", "Fallback component keyword match.")

    if category == "Instruction Manual" and not job_phys_pages:
        for physical_num in _find_pages_for_topic(
            pages_text,
            EXTRACTION_KEYWORDS["jobs"] + ["schedule", "interval", "inspection", "maintenance", "service"],
        ):
            job_phys_pages.add(physical_num)
            ref = page_refs[physical_num - 1]
            _upsert_page_reason(page_reasons, physical_num, ref.printed, "jobs", "Fallback job keyword match.")

    if category in ("Instruction Manual", "Yard/Finished Drawings") and not spare_phys_pages:
        for physical_num in _find_pages_for_topic(
            pages_text,
            EXTRACTION_KEYWORDS["spares"] + ["parts list", "bom", "bill of materials", "catalog", "recommended spares"],
        ):
            spare_phys_pages.add(physical_num)
            ref = page_refs[physical_num - 1]
            _upsert_page_reason(page_reasons, physical_num, ref.printed, "spares", "Fallback spare keyword match.")

    comp_pages_str, comp_phys_str = _refs_from_physical_pages(sorted(comp_phys_pages), page_refs)
    job_pages_str, job_phys_str = _refs_from_physical_pages(sorted(job_phys_pages), page_refs)
    spare_pages_str, spare_phys_str = _refs_from_physical_pages(sorted(spare_phys_pages), page_refs)

    _log.info(
        "classifier[scan]: category=%s comp_printed=%s job_printed=%s spare_printed=%s comp_phys=%s jobs_phys=%s spares_phys=%s",
        category,
        comp_pages_str,
        job_pages_str,
        spare_pages_str,
        comp_phys_str,
        job_phys_str,
        spare_phys_str,
    )

    reasons_json = json.dumps({str(k): v for k, v in sorted(page_reasons.items())}, ensure_ascii=False)
    return (
        comp_pages_str,
        job_pages_str,
        spare_pages_str,
        comp_phys_str,
        job_phys_str,
        spare_phys_str,
        reasons_json,
    )

    for ref, text in zip(page_refs, pages_text):
        if not text:
            continue

        physical_num = ref.physical
        printed_page = ref.printed
        lower_text = text.lower()

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
            if "tank" in tl and any(kw in tl for kw in ("capacity", "sounding", "ullage", "volume", "mÂ³", "m3", "liters", "ltr", "tonnes", "tons")):
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


def _find_pages_for_topic(pages_text: list[str], keywords: list[str]) -> list[int]:
    matching: list[int] = []
    for i, text in enumerate(pages_text):
        if any(kw in text.lower() for kw in keywords):
            matching.append(i + 1)
    return matching


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
            _log.warning("classifier: ANTHROPIC_API_KEY not set â€” falling back to keyword classifier")
            return None

        client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)

        # Build marked text for Claude (category classification only â€” pages handled programmatically)
        marked_text, _ = _make_marked_text(pages_text, max_chars=80_000)

        non_empty = sum(1 for p in pages_text if p.strip())
        _log.info(
            "classifier[claude]: %s â€” pages=%d non_empty=%d text_chars=%d",
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
            "classifier[claude]: %s â†’ category=%s confidence=%s",
            filename, parsed.get("category"), parsed.get("confidence"),
        )
        return parsed

    except Exception as exc:
        _log.warning("classifier: Claude call failed for %s: %s", filename, exc)
        return None


# ---------------------------------------------------------------------------
# Groq AI classifier (free tier â€” 30 RPM, uses llama-3.3-70b)
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
            "classifier[groq]: %s â€” pages=%d non_empty=%d text_chars=%d",
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
            "classifier[groq]: %s â†’ category=%s confidence=%s",
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

- **Instruction Manual**: OEM manufacturer's manual for a SINGLE piece of equipment â€” sequential written chapters covering operation, maintenance, troubleshooting, overhaul. Written by the equipment maker (e.g. TAIKO KIKAI, MAN, WÃ¤rtsilÃ¤). Contains prose/paragraph text.
- **Machinery Particulars**: Vessel-level tabular register of ALL equipment â€” many rows with columns: Equipment Name | Maker | Model | Serial No. | Capacity. Not focused on one machine.
- **General Arrangement**: Deck plans and layout drawings showing spatial arrangement of the vessel.
- **Pipeline Diagrams/P&ID**: Piping & Instrumentation Diagrams, system flow diagrams, hydraulic schematics.
- **LSA/FFA Plans**: Life Saving Appliance plans, Fire Fighting Appliance plans, fire safety plans, muster lists.
- **Tank Capacity Plan**: Tank tables, sounding tables, ullage tables, stability booklets, capacity plans.
- **Electrical Diagrams**: Single-line diagrams, wiring diagrams, cable lists, switchboard schematics.
- **Yard/Finished Drawings**: Shipyard delivery package â€” assembly drawings, outfit drawings, final construction drawings. Signs: engineering drawing format (title block, drawing number, revision table), item-numbered parts tables (Item No. | Description | Qty | Material), multiple equipment types bundled, hull/vessel name reference, spare parts lists attached to drawings. Keywords: "yard drawing", "final drawing", "construction drawing", "as-built", "outfit drawing", "spare per". Does NOT require written operational procedures. If the document is a "final drawing" or "yard drawing" for equipment like sewage treatment plant, classify here even if it has equipment details.
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
  "pages_with_components": "<comma-separated list of physical PDF page numbers, e.g. '1,3,5-7'>",
  "pages_with_jobs": "<comma-separated list of physical PDF page numbers>",
  "pages_with_spares": "<comma-separated list of physical PDF page numbers>",
  "reasoning": "<one sentence explanation>"
}}

Rules:
- confidence 85-98: very clear; 65-84: probable; 40-64: uncertain; <40 â†’ Unknown/Unclassifiable
- useful_for_extraction = "yes" if Instruction Manual, Machinery Particulars, or Tank Capacity Plan
- useful_for_extraction = "partial" if spec sheet or drawing with some equipment data
- useful_for_extraction = "no" if purely drawings, certificates, P&IDs, or LSA/FFA plans
- Machinery Particulars vs Instruction Manual: one equipment in depth â†’ Instruction Manual; many equipment rows â†’ Machinery Particulars
- Yard/Finished Drawings: assembly/outfit drawings with parts tables from shipyard delivery â€” even if equipment names are present. Prioritize if filename contains "final drawing", "yard", "construction", or "as-built".. Prioritize if filename contains "final drawing", "yard", "construction", or "as-built".
- For pages: use the PHYSICAL PDF page numbers from the [PAGE N, printed_page=X] markers. N is the real PDF page position. Do not return the printed footer page number.
- Example: if the marker says [PAGE 10, printed_page=9], return page 10, not 9.
- For Tank Capacity Plans, include tank title and table pages when they identify tank names, sounding, ullage, or capacities, even if no printed footer page is present.
- For Instruction Manuals, include the equipment identification/specification page as a component page when it identifies the machinery, and include contiguous job or spare pages only when the section content clearly continues.
- Only include pages that actually exist in the document. If no such pages, use empty string "".
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
            "classifier[gemini]: %s â€” pages=%d non_empty=%d text_chars=%d",
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
                wait = 5 * (2 ** attempt)  # 5s, 10s, 20s
                _log.warning(“classifier[gemini]: 429 rate limit for %s – retrying in %ds”, filename, wait)
                time.sleep(wait)
                continue
            response.raise_for_status()
            break
        else:
            _log.warning(“classifier[gemini]: exhausted retries for %s – giving up”, filename)
            return None
        data = response.json()
        raw = data["candidates"][0]["content"]["parts"][0]["text"].strip()

        _log.info("classifier[gemini]: raw response for %s: %s", filename, raw[:300])
        if "```" in raw:
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        parsed = json.loads(raw.strip())
        _log.info(
            "classifier[gemini]: %s â†’ category=%s confidence=%s",
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

# supply_type is rule-based â€” not AI-determined
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
    valid_pages = set(range(1, max_page + 1))
    return _filter_to_valid_pages(page_str, valid_pages)


def _sanitise_result(result: ClassificationResult) -> ClassificationResult:
    """Apply category-based rules to page fields and supply_type."""
    # Jobs exist only in Instruction Manuals
    if result.category not in _HAS_JOBS_CATEGORIES:
        result.pages_with_jobs = ""
        result.pages_with_jobs_printed = ""
        result.pages_with_jobs_physical = ""

    # Spares exist only in Instruction Manuals and Yard/Finished Drawings
    if result.category not in _HAS_SPARES_CATEGORIES:
        result.pages_with_spares = ""
        result.pages_with_spares_printed = ""
        result.pages_with_spares_physical = ""

    # Components only in relevant categories
    if result.category not in _HAS_COMPONENTS_CATEGORIES:
        result.pages_with_components = ""
        result.pages_with_components_printed = ""
        result.pages_with_components_physical = ""

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


def classify_pages_text(
    pages_text: list[str],
    filename: str,
    total_pages: Optional[int] = None,
) -> ClassificationResult:
    total_pages = total_pages or len(pages_text)
    page_refs = _build_page_references(pages_text)

    ai_result = _classify_with_groq(pages_text, filename, total_pages)
    if not ai_result:
        ai_result = _classify_with_gemini(pages_text, filename, total_pages)
    if not ai_result:
        ai_result = _classify_with_claude(pages_text, filename, total_pages)

    category = ai_result.get("category", "Unknown/Unclassifiable") if ai_result else "Unknown/Unclassifiable"
    if category not in VALID_CATEGORIES:
        category = "Unknown/Unclassifiable"
    confidence = max(0, min(100, int(ai_result.get("confidence", 60)))) if ai_result else 0
    useful_for_extraction = ai_result.get("useful_for_extraction", "partial") if ai_result else "partial"

    if category == "Unknown/Unclassifiable" or confidence < 50:
        kw = _keyword_classify(pages_text, filename, total_pages)
        if kw.category != "Unknown/Unclassifiable" and kw.confidence >= confidence:
            category = kw.category
            confidence = kw.confidence
            useful_for_extraction = kw.useful_for_extraction

    scanned_comp_printed, scanned_job_printed, scanned_spare_printed, scanned_comp_phys, scanned_job_phys, scanned_spare_phys, scanned_reasons = _scan_pages(
        pages_text,
        page_refs,
        category,
    )

    ai_comp_phys = _selected_physical_pages_from_ai(ai_result, "pages_with_components", total_pages)
    ai_job_phys = _selected_physical_pages_from_ai(ai_result, "pages_with_jobs", total_pages)
    ai_spare_phys = _selected_physical_pages_from_ai(ai_result, "pages_with_spares", total_pages)

    selected_comp_phys = ai_comp_phys or _parse_page_tokens(scanned_comp_phys)
    selected_job_phys = ai_job_phys or _parse_page_tokens(scanned_job_phys)
    selected_spare_phys = ai_spare_phys or _parse_page_tokens(scanned_spare_phys)

    final_comp_printed, final_comp_phys = _refs_from_physical_pages(selected_comp_phys, page_refs)
    final_job_printed, final_job_phys = _refs_from_physical_pages(selected_job_phys, page_refs)
    final_spare_printed, final_spare_phys = _refs_from_physical_pages(selected_spare_phys, page_refs)

    merged_reasons = _merge_page_explanations(
        scanned_reasons,
        page_refs,
        {
            "components": ai_comp_phys,
            "jobs": ai_job_phys,
            "spares": ai_spare_phys,
        },
    )

    result = ClassificationResult(
        category=category,
        confidence=confidence,
        useful_for_extraction=useful_for_extraction,
        pages_with_components=final_comp_printed or final_comp_phys,
        pages_with_jobs=final_job_printed or final_job_phys,
        pages_with_spares=final_spare_printed or final_spare_phys,
        pages_with_components_printed=final_comp_printed,
        pages_with_jobs_printed=final_job_printed,
        pages_with_spares_printed=final_spare_printed,
        pages_with_components_physical=final_comp_phys,
        pages_with_jobs_physical=final_job_phys,
        pages_with_spares_physical=final_spare_phys,
        page_explanations=merged_reasons,
        page_count=total_pages,
    )
    return _sanitise_result(result)


def classify_pdf(content: bytes, filename: str) -> ClassificationResult:
    “””
    Classify a PDF manual.
    Priority: Groq (free) → Gemini (free fallback) → Claude (paid fallback) → keyword.
    “””
    pages_text, total_pages = _extract_pdf_text(content)
    _log.info(“classifier: extracted %d pages from %s (%d bytes)”, total_pages, filename, len(content))
    return classify_pages_text(pages_text, filename, total_pages)


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

    pages_components = _format_page_tokens(_find_pages_for_topic(pages_text, EXTRACTION_KEYWORDS["components"]))
    pages_jobs = _format_page_tokens(_find_pages_for_topic(pages_text, EXTRACTION_KEYWORDS["jobs"]))
    pages_spares = _format_page_tokens(_find_pages_for_topic(pages_text, EXTRACTION_KEYWORDS["spares"]))

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
