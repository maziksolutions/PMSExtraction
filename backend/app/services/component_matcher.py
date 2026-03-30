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

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.component import Component, QCStatus
from app.models.ingestion import Manual

logger = logging.getLogger(__name__)

MATCH_THRESHOLD = 0.55  # lowered — normalization handles most variation now


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
            Component.source_manual_id == None,
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

    # Build name index for library components
    lib_names = [(c, c.component_name) for c in library_components]

    merged = 0
    unmatched = 0
    to_delete: list[uuid.UUID] = []

    for ext_comp in extracted_components:
        best_match: Optional[Component] = None
        best_score = 0.0

        for lib_comp, lib_name in lib_names:
            score = _similarity(ext_comp.component_name, lib_name)
            if score > best_score:
                best_score = score
                best_match = lib_comp

        if best_match and best_score >= MATCH_THRESHOLD:
            # Merge: enrich library component with extracted data (only fill nulls)
            if not best_match.maker and ext_comp.maker:
                best_match.maker = ext_comp.maker
            if not best_match.model and ext_comp.model:
                best_match.model = ext_comp.model
            if not best_match.specification and ext_comp.specification:
                best_match.specification = ext_comp.specification
            if not best_match.serial_number and ext_comp.serial_number:
                best_match.serial_number = ext_comp.serial_number
            # Always update reference fields from the extracted component
            if ext_comp.source_manual_id:
                best_match.source_manual_id = ext_comp.source_manual_id
            if ext_comp.page_reference:
                best_match.page_reference = ext_comp.page_reference
            if ext_comp.pdf_reference:
                best_match.pdf_reference = ext_comp.pdf_reference
            if ext_comp.job_pages:
                best_match.job_pages = ext_comp.job_pages
            if ext_comp.spare_pages:
                best_match.spare_pages = ext_comp.spare_pages
            if ext_comp.confidence_score:
                best_match.confidence_score = ext_comp.confidence_score
            best_match.qc_status = QCStatus.modified

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
