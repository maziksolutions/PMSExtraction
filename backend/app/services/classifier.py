"""
Automatic manual classifier.

Uses pdfplumber to extract text from uploaded PDFs and keyword matching
to determine category, confidence, and page ranges.
"""
from __future__ import annotations

import io
import re
from dataclasses import dataclass
from typing import Optional

# ---------------------------------------------------------------------------
# Category definitions with keywords
# ---------------------------------------------------------------------------

CATEGORY_RULES: list[tuple[str, list[str], int]] = [
    # (category_name, keywords, base_confidence)
    ("Machinery Particulars", [
        "machinery list", "machinery particulars", "equipment list",
        "maker list", "manufacturer list", "machinery inventory",
        "installed machinery", "main engine", "auxiliary engine",
        "machinery register",
    ], 85),
    ("Instruction Manual", [
        "instruction manual", "operation manual", "operating manual",
        "maintenance manual", "service manual", "user manual",
        "operator manual", "technical manual", "overhaul manual",
        "installation manual",
    ], 85),
    ("General Arrangement", [
        "general arrangement", "g.a. plan", "ga plan",
        "deck arrangement", "layout plan", "accommodation plan",
        "general plan",
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
        "emergency plan",
    ], 80),
    ("Tank Capacity Plan", [
        "tank capacity", "capacity plan", "tank plan", "sounding table",
        "ullage table", "trim and stability", "deadweight",
        "tank arrangement", "cargo plan",
    ], 80),
    ("Electrical Diagrams", [
        "electrical diagram", "wiring diagram", "single line diagram",
        "switchboard", "electrical schematic", "power distribution",
        "load list", "cable list", "electrical plan",
    ], 78),
    ("Yard/Finished Drawings", [
        "yard drawing", "construction drawing", "as-built",
        "finished drawing", "structural drawing", "hull drawing",
        "shipyard", "building specification",
    ], 75),
    ("Class Certificates/Surveys", [
        "class certificate", "survey report", "classification",
        "dnv", "lloyd's register", "bureau veritas", "abs",
        "rina", "certificate of registry", "statutory certificate",
        "safety certificate", "inspection report",
    ], 82),
]

EXTRACTION_KEYWORDS = {
    "components": [
        "component", "equipment", "machinery", "system", "unit",
        "pump", "compressor", "engine", "motor", "valve", "filter",
        "heat exchanger", "separator", "generator", "turbine",
    ],
    "jobs": [
        "maintenance", "overhaul", "inspection", "service", "check",
        "test", "lubrication", "adjustment", "calibration", "cleaning",
        "replacement", "repair", "interval", "running hours",
    ],
    "spares": [
        "spare", "spare part", "part number", "item no", "catalog",
        "consumable", "wear part", "replacement part", "stock",
        "part list", "spare list",
    ],
}


@dataclass
class ClassificationResult:
    category: str
    confidence: int
    useful_for_extraction: str  # "yes", "partial", "no"
    pages_with_components: str
    pages_with_jobs: str
    pages_with_spares: str
    page_count: int


def _score_text(text: str, keywords: list[str]) -> int:
    text_lower = text.lower()
    return sum(1 for kw in keywords if kw in text_lower)


def _find_pages_for_topic(pages_text: list[str], keywords: list[str]) -> str:
    """Return a page range string like '1-10, 25-30' for pages containing keywords."""
    matching: list[int] = []
    for i, text in enumerate(pages_text):
        if _score_text(text, keywords) > 0:
            matching.append(i + 1)  # 1-indexed

    if not matching:
        return ""

    # Compress into ranges
    ranges: list[str] = []
    start = matching[0]
    end = matching[0]
    for page in matching[1:]:
        if page == end + 1:
            end = page
        else:
            ranges.append(f"{start}-{end}" if start != end else str(start))
            start = end = page
    ranges.append(f"{start}-{end}" if start != end else str(start))
    return ", ".join(ranges)


def classify_pdf(content: bytes, filename: str) -> ClassificationResult:
    """
    Classify a PDF manual using pdfplumber text extraction + keyword matching.
    Falls back gracefully if pdfplumber fails.
    """
    try:
        import pdfplumber  # type: ignore
    except ImportError:
        return _fallback_from_filename(filename)

    pages_text: list[str] = []
    try:
        with pdfplumber.open(io.BytesIO(content)) as pdf:
            for page in pdf.pages[:50]:  # Analyse first 50 pages max
                text = page.extract_text() or ""
                pages_text.append(text)
    except Exception:
        return _fallback_from_filename(filename)

    full_text = "\n".join(pages_text[:10])  # First 10 pages for category detection
    combined = (filename + " " + full_text).lower()

    # Score each category
    best_category = "Unknown/Unclassifiable"
    best_score = 0
    best_base_conf = 50

    for category, keywords, base_conf in CATEGORY_RULES:
        score = _score_text(combined, keywords)
        if score > best_score:
            best_score = score
            best_category = category
            best_base_conf = base_conf

    # Compute confidence (capped at 95)
    if best_score == 0:
        confidence = 40
        best_category = "Unknown/Unclassifiable"
    else:
        confidence = min(95, best_base_conf + best_score * 2)

    # Determine usefulness for extraction
    useful_categories = {
        "Instruction Manual", "Machinery Particulars",
        "Pipeline Diagrams/P&ID", "Tank Capacity Plan",
    }
    partial_categories = {
        "General Arrangement", "Electrical Diagrams",
        "Yard/Finished Drawings", "Class Certificates/Surveys",
    }
    if best_category in useful_categories:
        useful = "yes"
    elif best_category in partial_categories:
        useful = "partial"
    else:
        useful = "no"

    # Find pages for each extraction topic
    pages_components = _find_pages_for_topic(pages_text, EXTRACTION_KEYWORDS["components"])
    pages_jobs = _find_pages_for_topic(pages_text, EXTRACTION_KEYWORDS["jobs"])
    pages_spares = _find_pages_for_topic(pages_text, EXTRACTION_KEYWORDS["spares"])

    # Default page ranges if not found
    total = len(pages_text)
    if total > 0:
        if not pages_components:
            pages_components = f"1-{min(total, 20)}"
        if not pages_jobs:
            pages_jobs = f"1-{total}"
        if not pages_spares:
            pages_spares = f"1-{total}"

    return ClassificationResult(
        category=best_category,
        confidence=confidence,
        useful_for_extraction=useful,
        pages_with_components=pages_components,
        pages_with_jobs=pages_jobs,
        pages_with_spares=pages_spares,
        page_count=total,
    )


def _fallback_from_filename(filename: str) -> ClassificationResult:
    """Classify based on filename alone when PDF parsing fails."""
    name_lower = filename.lower()
    category = "Unknown/Unclassifiable"
    confidence = 40

    for cat, keywords, base_conf in CATEGORY_RULES:
        if any(kw in name_lower for kw in keywords):
            category = cat
            confidence = base_conf - 15  # lower confidence for name-only match
            break

    return ClassificationResult(
        category=category,
        confidence=confidence,
        useful_for_extraction="partial",
        pages_with_components="",
        pages_with_jobs="",
        pages_with_spares="",
        page_count=0,
    )
