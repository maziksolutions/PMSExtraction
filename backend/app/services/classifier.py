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

def _extract_pdf_text(content: bytes, max_pages: int = 30) -> tuple[list[str], int]:
    """Extract text per page from PDF bytes. Returns (pages_text, total_pages)."""
    try:
        import pdfplumber  # type: ignore
        pages_text: list[str] = []
        with pdfplumber.open(io.BytesIO(content)) as pdf:
            total = len(pdf.pages)
            for page in pdf.pages[:max_pages]:
                pages_text.append(page.extract_text() or "")
        return pages_text, total
    except Exception:
        return [], 0


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

def _classify_with_claude(text_sample: str, filename: str, page_count: int) -> Optional[dict]:
    """Call Claude API to classify the manual. Returns parsed JSON or None on failure."""
    try:
        import anthropic
        from app.core.config import settings

        if not settings.ANTHROPIC_API_KEY:
            return None

        client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)

        prompt = f"""You are a maritime document classifier. Analyse the following vessel manual and return a JSON classification.

Filename: {filename}
Page count: {page_count}
Text sample (first pages):
---
{text_sample[:4000]}
---

Classify this document and return ONLY valid JSON in this exact format:
{{
  "category": "<one of: Instruction Manual | Machinery Particulars | General Arrangement | Pipeline Diagrams/P&ID | LSA/FFA Plans | Tank Capacity Plan | Yard/Finished Drawings | Electrical Diagrams | Class Certificates/Surveys | Unknown/Unclassifiable>",
  "confidence": <integer 0-100>,
  "useful_for_extraction": "<yes | partial | no>",
  "pages_with_components": "<page range like '1-20, 35-40' or empty string>",
  "pages_with_jobs": "<page range like '21-50' or empty string>",
  "pages_with_spares": "<page range like '51-80' or empty string>",
  "reasoning": "<one sentence explanation>"
}}

Rules:
- useful_for_extraction = "yes" if the document contains machinery components, maintenance jobs, or spare parts data
- useful_for_extraction = "partial" if it has some relevant data mixed with other content
- useful_for_extraction = "no" if it is certificates, drawings, or general plans with no extractable PMS data
- Page ranges should be based on where relevant content appears in the document
- confidence should reflect how certain you are about the category (80-95 for clear matches, 40-65 for uncertain)"""

        message = client.messages.create(
            model="claude-opus-4-6",
            max_tokens=512,
            messages=[{"role": "user", "content": prompt}],
        )

        raw = message.content[0].text.strip()
        # Extract JSON from response (handles markdown code blocks)
        if "```" in raw:
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        return json.loads(raw.strip())

    except Exception:
        return None


# ---------------------------------------------------------------------------
# Public interface
# ---------------------------------------------------------------------------

def classify_pdf(content: bytes, filename: str) -> ClassificationResult:
    """
    Classify a PDF manual.
    Uses Claude AI if ANTHROPIC_API_KEY is set, otherwise falls back to keyword matching.
    """
    pages_text, total_pages = _extract_pdf_text(content, max_pages=30)
    text_sample = "\n\n".join(pages_text[:10])

    # Try Claude first
    ai_result = _classify_with_claude(text_sample, filename, total_pages)
    if ai_result:
        category = ai_result.get("category", "Unknown/Unclassifiable")
        if category not in VALID_CATEGORIES:
            category = "Unknown/Unclassifiable"
        return ClassificationResult(
            category=category,
            confidence=max(0, min(100, int(ai_result.get("confidence", 60)))),
            useful_for_extraction=ai_result.get("useful_for_extraction", "partial"),
            pages_with_components=ai_result.get("pages_with_components", ""),
            pages_with_jobs=ai_result.get("pages_with_jobs", ""),
            pages_with_spares=ai_result.get("pages_with_spares", ""),
            page_count=total_pages,
        )

    # Fallback: keyword matching
    return _keyword_classify(pages_text, filename, total_pages)


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
