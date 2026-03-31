"""
Automatic manual classifier.

Primary: Uses Claude AI (Anthropic) for intelligent classification when
ANTHROPIC_API_KEY is configured.

Fallback: Uses pdfplumber + keyword matching when no API key is set.
"""
from __future__ import annotations

import io
import json
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


def _make_marked_text(pages_text: list[str], max_chars: int = 80_000) -> str:
    """Build a single string with [PAGE N] markers, capped at max_chars."""
    parts: list[str] = []
    total = 0
    for i, text in enumerate(pages_text, start=1):
        snippet = f"[PAGE {i}]\n{text}" if text else f"[PAGE {i}]"
        total += len(snippet)
        parts.append(snippet)
        if total >= max_chars:
            break
    return "\n\n".join(parts)


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

        # Build marked text for Claude — include [PAGE N] markers so page ranges are precise
        marked_text = _make_marked_text(pages_text, max_chars=80_000)

        non_empty = sum(1 for p in pages_text if p.strip())
        _log.info(
            "classifier: %s — pages=%d non_empty=%d text_chars=%d",
            filename, page_count, non_empty, len(marked_text),
        )

        prompt = f"""You are an expert maritime document classifier specialising in ship technical documentation and PMS (Planned Maintenance System) data.

Filename: {filename}
Total pages: {page_count}

The document text below includes [PAGE N] markers. Use these exact page numbers when reporting page ranges.

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

- **pages_with_components**: Pages showing equipment specs, general description, name plate data, or component lists.
  Look for: specification tables, "General Description", "Technical Data", maker/model rows, capacity tables.
- **pages_with_jobs**: Pages containing maintenance schedules, service intervals, or inspection procedures.
  Look for: section headings like "Maintenance", "Service Schedule", "Inspection", "Periodic Maintenance",
  tables with columns "Interval | Description", "Every day / Weekly / Monthly" rows.
- **pages_with_spares**: Pages containing spare parts lists or recommended spares.
  Look for: "Spare Parts", "Parts List", "Recommended Spares", "Spare Part Catalogue",
  tables with columns NO. | NAME | PART NUMBER | QTY.

Return ONLY valid JSON in this exact format:
{{
  "category": "<category name exactly as listed above>",
  "confidence": <integer 0-100>,
  "useful_for_extraction": "<yes | partial | no>",
  "pages_with_components": "<comma-separated page numbers from [PAGE N] markers e.g. '1, 2, 3, 15' or empty string if none>",
  "pages_with_jobs": "<comma-separated page numbers from [PAGE N] markers e.g. '40, 41, 42, 55, 56' or empty string if none>",
  "pages_with_spares": "<comma-separated page numbers from [PAGE N] markers e.g. '66, 67, 68' or empty string if none>",
  "reasoning": "<one sentence explanation>"
}}

Rules:
- Use [PAGE N] markers to identify EXACT page numbers — do NOT guess or estimate
- List every individual page number where the content appears — do NOT use ranges or hyphens
- useful_for_extraction = "yes" if Instruction Manual OR Machinery Particulars
- useful_for_extraction = "partial" if spec sheet or drawing with some equipment data (e.g. a spec sheet with maker/model but no maintenance section)
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

        marked_text = _make_marked_text(pages_text, max_chars=80_000)
        non_empty = sum(1 for p in pages_text if p.strip())
        _log.info(
            "classifier[groq]: %s — pages=%d non_empty=%d text_chars=%d",
            filename, page_count, non_empty, len(marked_text),
        )

        prompt = _build_classification_prompt(filename, page_count, marked_text)
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=1024,
            temperature=0,
        )
        raw = response.choices[0].message.content.strip()

        _log.info("classifier[groq]: raw response for %s: %s", filename, raw[:300])
        if "```" in raw:
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        parsed = json.loads(raw.strip())
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

The document text below includes [PAGE N] markers. Use these exact page numbers when reporting pages.

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

- **pages_with_components**: Pages showing equipment specs, general description, name plate data, or component lists.
- **pages_with_jobs**: Pages containing maintenance schedules, service intervals, or inspection procedures.
- **pages_with_spares**: Pages containing spare parts lists or recommended spares.

Return ONLY valid JSON in this exact format:
{{
  "category": "<category name exactly as listed above>",
  "confidence": <integer 0-100>,
  "useful_for_extraction": "<yes | partial | no>",
  "pages_with_components": "<comma-separated page numbers e.g. '1, 2, 3, 15' or empty string if none>",
  "pages_with_jobs": "<comma-separated page numbers e.g. '40, 41, 42, 55, 56' or empty string if none>",
  "pages_with_spares": "<comma-separated page numbers e.g. '66, 67, 68' or empty string if none>",
  "reasoning": "<one sentence explanation>"
}}

Rules:
- Use [PAGE N] markers to identify EXACT page numbers — do NOT guess or estimate
- List every individual page number — do NOT use ranges or hyphens
- useful_for_extraction = "yes" if Instruction Manual OR Machinery Particulars
- useful_for_extraction = "partial" if spec sheet with maker/model but no maintenance section
- useful_for_extraction = "no" if purely drawings, plans, certificates, or P&IDs
- confidence 85-98: very clear; 65-84: probable; 40-64: uncertain; <40: use Unknown/Unclassifiable
- Machinery Particulars vs Instruction Manual: one equipment in depth → Instruction Manual; many equipment rows → Machinery Particulars
- If a section is genuinely absent, return empty string — do NOT invent page numbers"""


def _classify_with_gemini(pages_text: list[str], filename: str, page_count: int) -> Optional[dict]:
    """Call Gemini API (free tier) via HTTP. Returns parsed JSON or None on failure."""
    try:
        import httpx
        from app.core.config import settings

        if not settings.GEMINI_API_KEY:
            return None

        marked_text = _make_marked_text(pages_text, max_chars=80_000)
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


def _sanitise_result(result: ClassificationResult) -> ClassificationResult:
    """Force page ranges to empty string where they cannot logically exist."""
    if result.category in _NO_JOB_SPARE_CATEGORIES:
        result.pages_with_jobs = ""
        result.pages_with_spares = ""
    if result.category not in _HAS_COMPONENTS_CATEGORIES:
        result.pages_with_components = ""
    # Tank Capacity Plan never has jobs or spares
    if result.category == "Tank Capacity Plan":
        result.pages_with_jobs = ""
        result.pages_with_spares = ""
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

        result = ClassificationResult(
            category=category,
            confidence=ai_confidence,
            useful_for_extraction=ai_result.get("useful_for_extraction", "partial"),
            pages_with_components=ai_result.get("pages_with_components", ""),
            pages_with_jobs=ai_result.get("pages_with_jobs", ""),
            pages_with_spares=ai_result.get("pages_with_spares", ""),
            page_count=total_pages,
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
