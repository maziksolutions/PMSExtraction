"""
Component auto-merge service.

Matches extracted components (source_manual_id IS NOT NULL) against
library-loaded components (source_manual_id IS NULL) in the same vessel
using fuzzy name similarity. Merges matching pairs and deletes the
extracted duplicate so the library component row is enriched in-place.
"""
from __future__ import annotations

import logging
import re
import uuid
from difflib import SequenceMatcher
from typing import Optional

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.component import Component, QCStatus

logger = logging.getLogger(__name__)

MATCH_THRESHOLD = 0.68  # allow stronger manual/library reconciliation while still avoiding unrelated matches


# ---------------------------------------------------------------------------
# Name normalization
# ---------------------------------------------------------------------------

# Common maritime abbreviations: pattern → replacement (all lowercase)
_ABBREV_PATTERNS: list[tuple[str, str]] = [
    # Fluid types
    (r'\bf\.?\s*o\.?\b', 'fuel oil'),
    (r'\bb\.?\s*w\.?\b', 'ballast water'),
    (r'\bf\.?\s*w\.?\b', 'fresh water'),
    (r'\bl\.?\s*o\.?\b', 'lube oil'),
    (r'\bd\.?\s*o\.?\b', 'diesel oil'),
    (r'\bs\.?\s*w\.?\b', 'sea water'),
    (r'\bh\.?\s*f\.?\s*o\.?\b', 'heavy fuel oil'),
    (r'\bm\.?\s*g\.?\s*o\.?\b', 'marine gas oil'),
    (r'\bd\.?\s*w\.?\b', 'drinking water'),
    # Side indicators (parenthesised or standalone)
    (r'\(\s*p\s*\)', 'port'),
    (r'\(\s*s\s*\)', 'starboard'),
    (r'\(\s*c\s*\)', 'centre'),
    (r'\bstbd\b', 'starboard'),
    (r'\bsb\b', 'starboard'),
    (r'\bps\b', 'port starboard'),
    # Position
    (r'\bfwd\b', 'forward'),
    (r'\baft\b', 'after'),
    (r'\bno\.?\s*', 'no '),
    # Tank suffixes
    (r'\btk\b', 'tank'),
    (r'\bsett?\.?\b', 'settling'),
    (r'\bserv\.?\b', 'service'),
    (r'\bdb\b', 'double bottom'),
]

_COMPILED = [(re.compile(pat, re.IGNORECASE), repl) for pat, repl in _ABBREV_PATTERNS]


def _normalize(name: str) -> str:
    """Lowercase, expand abbreviations, strip punctuation."""
    s = name.strip().lower()
    for regex, repl in _COMPILED:
        s = regex.sub(repl, s)
    s = re.sub(r'[^\w\s]', ' ', s)   # strip remaining punctuation
    s = re.sub(r'\s+', ' ', s).strip()
    return s


def _similarity(a: str, b: str) -> float:
    """
    Combined similarity: max of token-Jaccard and character SequenceMatcher,
    both operating on normalized names.
    """
    na, nb = _normalize(a), _normalize(b)
    if not na or not nb:
        return 0.0

    # Token Jaccard — robust to word reordering and abbreviation differences
    tokens_a = set(na.split())
    tokens_b = set(nb.split())
    union = tokens_a | tokens_b
    jaccard = len(tokens_a & tokens_b) / len(union) if union else 0.0

    # Character SequenceMatcher on normalized strings
    char_sim = SequenceMatcher(None, na, nb).ratio()

    return max(jaccard, char_sim)


def _component_similarity(extracted: Component, library: Component) -> float:
    name_score = _similarity(extracted.component_name, library.component_name)
    machinery_score = _similarity(extracted.main_machinery, library.main_machinery)
    cross_score = max(
        _similarity(extracted.component_name, library.main_machinery),
        _similarity(extracted.main_machinery, library.component_name),
    )

    bonus = 0.0
    if extracted.group1 and library.group1 and _normalize(extracted.group1) == _normalize(library.group1):
        bonus += 0.05
    if extracted.group2 and library.group2 and _normalize(extracted.group2) == _normalize(library.group2):
        bonus += 0.07

    ext_tokens = set(_normalize(f"{extracted.component_name} {extracted.main_machinery}").split())
    lib_tokens = set(_normalize(f"{library.component_name} {library.main_machinery}").split())
    if ext_tokens and lib_tokens:
        overlap = len(ext_tokens & lib_tokens) / max(min(len(ext_tokens), len(lib_tokens)), 1)
        if overlap >= 0.75:
            bonus += 0.08

    return max(name_score, machinery_score, cross_score) + bonus


def _is_blankish(value: Optional[str]) -> bool:
    cleaned = (value or "").strip().lower()
    return cleaned in {"", "-", "—", "n/a", "na", "unknown", "not available", "none"}


def _prefer_extracted(current: Optional[str], incoming: Optional[str]) -> Optional[str]:
    if _is_blankish(incoming):
        return current
    if _is_blankish(current):
        return incoming
    if current and incoming and len(incoming.strip()) > len(current.strip()):
        return incoming
    return current


# ---------------------------------------------------------------------------
# Main merge function
# ---------------------------------------------------------------------------

async def auto_merge_extracted_components(
    db: AsyncSession,
    vessel_id: uuid.UUID,
    tenant_id: uuid.UUID,
) -> tuple[int, int]:
    """
    Merge extracted components into their matching library components.
    Returns (merged_count, unmatched_count).
    """
    # Load library components (no source manual — loaded from standard library)
    lib_result = await db.execute(
        select(Component).where(
            Component.vessel_id == vessel_id,
            Component.tenant_id == tenant_id,
            Component.is_deleted == False,
            Component.is_unmapped == False,
            or_(
                Component.source_manual_id == None,
                Component.qc_status != QCStatus.pending,
            ),
        )
    )
    library_components = list(lib_result.scalars().all())

    # Load extracted components (have a source manual)
    ext_result = await db.execute(
        select(Component).where(
            Component.vessel_id == vessel_id,
            Component.tenant_id == tenant_id,
            Component.is_deleted == False,
            Component.source_manual_id != None,
            Component.qc_status == QCStatus.pending,
        )
    )
    extracted_components = list(ext_result.scalars().all())

    if not extracted_components:
        return 0, 0

    if not library_components:
        # No library to merge into — mark everything as unmapped so they appear in the UI
        for ext_comp in extracted_components:
            ext_comp.is_unmapped = True
            db.add(ext_comp)
        await db.commit()
        logger.info(
            "auto_merge: vessel=%s no library components — marked %d as unmapped",
            vessel_id,
            len(extracted_components),
        )
        return 0, len(extracted_components)

    merged = 0
    unmatched = 0
    to_delete: list[uuid.UUID] = []

    for ext_comp in extracted_components:
        best_match: Optional[Component] = None
        best_score = 0.0

        for lib_comp in library_components:
            score = _component_similarity(ext_comp, lib_comp)
            if score > best_score:
                best_score = score
                best_match = lib_comp

        if best_match and best_score >= MATCH_THRESHOLD:
            # Merge: only fill nulls — never overwrite data already on the library component
            best_match.maker = _prefer_extracted(best_match.maker, ext_comp.maker)
            best_match.model = _prefer_extracted(best_match.model, ext_comp.model)
            best_match.specification = _prefer_extracted(best_match.specification, ext_comp.specification)
            best_match.serial_number = _prefer_extracted(best_match.serial_number, ext_comp.serial_number)
            best_match.location = _prefer_extracted(best_match.location, ext_comp.location)
            best_match.machinery_particulars = _prefer_extracted(best_match.machinery_particulars, ext_comp.machinery_particulars)
            # Keep the standing vessel component as the canonical row.
            if not best_match.page_reference and ext_comp.page_reference:
                best_match.page_reference = ext_comp.page_reference
            # pdf_reference: if different file, append "File1.pdf (pp.X-Y); File2.pdf (pp.A-B)"
            if ext_comp.pdf_reference:
                if not best_match.pdf_reference:
                    ref = ext_comp.pdf_reference
                    if ext_comp.page_reference:
                        ref = f"{ref} (p.{ext_comp.page_reference})"
                    best_match.pdf_reference = ref
                elif ext_comp.pdf_reference not in best_match.pdf_reference:
                    # Append new source
                    ref = ext_comp.pdf_reference
                    if ext_comp.page_reference:
                        ref = f"{ref} (p.{ext_comp.page_reference})"
                    best_match.pdf_reference = f"{best_match.pdf_reference}; {ref}"
            # job_pages / spare_pages: append ranges from different manuals
            if ext_comp.job_pages:
                if _is_blankish(best_match.job_pages):
                    best_match.job_pages = ext_comp.job_pages
                elif ext_comp.job_pages not in best_match.job_pages:
                    best_match.job_pages = f"{best_match.job_pages}; {ext_comp.job_pages}"
            if ext_comp.spare_pages:
                if _is_blankish(best_match.spare_pages):
                    best_match.spare_pages = ext_comp.spare_pages
                elif ext_comp.spare_pages not in best_match.spare_pages:
                    best_match.spare_pages = f"{best_match.spare_pages}; {ext_comp.spare_pages}"
            if not best_match.confidence_score and ext_comp.confidence_score:
                best_match.confidence_score = ext_comp.confidence_score
            best_match.qc_status = QCStatus.modified
            best_match.is_unmapped = False
            if ext_comp.is_critical and not best_match.is_critical:
                best_match.is_critical = True

            db.add(best_match)
            to_delete.append(ext_comp.id)
            merged += 1

            logger.info(
                "auto_merge: matched '%s' → '%s' (score=%.2f)",
                ext_comp.component_name,
                best_match.component_name,
                best_score,
            )
        else:
            # No match — keep as unmapped extracted component
            ext_comp.is_unmapped = True
            db.add(ext_comp)
            unmatched += 1

            logger.info(
                "auto_merge: NO MATCH for '%s' (best='%s' score=%.2f)",
                ext_comp.component_name,
                best_match.component_name if best_match else "—",
                best_score,
            )

    # Soft-delete the extracted duplicates that were merged
    for comp_id in to_delete:
        result = await db.execute(select(Component).where(Component.id == comp_id))
        comp = result.scalar_one_or_none()
        if comp:
            comp.is_deleted = True
            db.add(comp)

    await db.commit()
    logger.info("auto_merge: vessel=%s merged=%d unmatched=%d", vessel_id, merged, unmatched)
    return merged, unmatched
