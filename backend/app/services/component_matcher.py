"""
Component auto-merge service.

Matches extracted components (source_manual_id IS NOT NULL) against
library-loaded components (source_manual_id IS NULL) in the same vessel
using fuzzy name similarity. Merges matching pairs and deletes the
extracted duplicate so the library component row is enriched in-place.
"""
from __future__ import annotations

import logging
import uuid
from difflib import SequenceMatcher
from typing import Optional

from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.component import Component, QCStatus
from app.models.ingestion import Manual

logger = logging.getLogger(__name__)

MATCH_THRESHOLD = 0.68  # minimum similarity to consider a match


def _similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, a.strip().lower(), b.strip().lower()).ratio()


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
