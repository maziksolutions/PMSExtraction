from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Dict, Tuple
from sqlalchemy import text
from app.core.database import AsyncSessionLocal

logger = logging.getLogger(__name__)

_tables_initialized = False


async def ensure_extraction_counter_tables() -> None:
    """Ensures the tables for tracking manual and page extraction run counts exist."""
    global _tables_initialized
    if _tables_initialized:
        return
    try:
        async with AsyncSessionLocal() as session:
            await session.execute(text("""
                CREATE TABLE IF NOT EXISTS manual_extraction_runs (
                    manual_id UUID PRIMARY KEY,
                    run_count INT NOT NULL DEFAULT 1,
                    last_run_at TIMESTAMPTZ DEFAULT NOW()
                );
            """))
            await session.execute(text("""
                CREATE TABLE IF NOT EXISTS manual_page_extractions (
                    manual_id UUID NOT NULL,
                    page_number INT NOT NULL,
                    run_count INT NOT NULL DEFAULT 1,
                    last_extracted_at TIMESTAMPTZ DEFAULT NOW(),
                    PRIMARY KEY (manual_id, page_number)
                );
            """))
            await session.commit()
            _tables_initialized = True
    except Exception as exc:
        logger.warning("Failed to initialize extraction counter tables: %s", exc)


async def _async_record_manual_run(mid: uuid.UUID) -> None:
    try:
        await ensure_extraction_counter_tables()
        async with AsyncSessionLocal() as session:
            await session.execute(text("""
                INSERT INTO manual_extraction_runs (manual_id, run_count, last_run_at)
                VALUES (:mid, 1, NOW())
                ON CONFLICT (manual_id) DO UPDATE
                SET run_count = manual_extraction_runs.run_count + 1,
                    last_run_at = NOW();
            """), {"mid": mid})
            await session.commit()
    except Exception as exc:
        logger.warning("Failed to record manual run for %s: %s", mid, exc)


async def _async_record_page_run(mid: uuid.UUID, page_number: int) -> None:
    try:
        await ensure_extraction_counter_tables()
        async with AsyncSessionLocal() as session:
            await session.execute(text("""
                INSERT INTO manual_page_extractions (manual_id, page_number, run_count, last_extracted_at)
                VALUES (:mid, :page, 1, NOW())
                ON CONFLICT (manual_id, page_number) DO UPDATE
                SET run_count = manual_page_extractions.run_count + 1,
                    last_extracted_at = NOW();
            """), {"mid": mid, "page": page_number})
            await session.commit()
    except Exception as exc:
        logger.warning("Failed to record page run for %s p.%s: %s", mid, page_number, exc)


def record_manual_extraction_run(manual_id_str: str) -> None:
    """Non-blocking call to increment run count for a manual."""
    try:
        mid = uuid.UUID(str(manual_id_str))
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(_async_record_manual_run(mid))
        except RuntimeError:
            import threading
            threading.Thread(target=lambda: asyncio.run(_async_record_manual_run(mid)), daemon=True).start()
    except Exception as exc:
        logger.warning("record_manual_extraction_run error: %s", exc)


def record_page_extraction_run(manual_id_str: str, page_number: int) -> None:
    """Non-blocking call to increment run count for a specific page."""
    try:
        mid = uuid.UUID(str(manual_id_str))
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(_async_record_page_run(mid, int(page_number)))
        except RuntimeError:
            import threading
            threading.Thread(target=lambda: asyncio.run(_async_record_page_run(mid, int(page_number))), daemon=True).start()
    except Exception as exc:
        logger.warning("record_page_extraction_run error: %s", exc)


async def get_extraction_counts(manual_id: uuid.UUID) -> Tuple[int, Dict[int, int]]:
    """
    Returns (manual_run_count, page_run_counts_dict) for a manual.
    """
    await ensure_extraction_counter_tables()
    manual_runs = 0
    page_runs: Dict[int, int] = {}
    try:
        async with AsyncSessionLocal() as session:
            m_res = await session.execute(
                text("SELECT run_count FROM manual_extraction_runs WHERE manual_id = :mid"),
                {"mid": manual_id}
            )
            m_row = m_res.fetchone()
            if m_row:
                manual_runs = int(m_row[0] or 0)

            p_res = await session.execute(
                text("SELECT page_number, run_count FROM manual_page_extractions WHERE manual_id = :mid"),
                {"mid": manual_id}
            )
            for r in p_res.fetchall():
                page_runs[int(r[0])] = int(r[1] or 0)
    except Exception as exc:
        logger.warning("get_extraction_counts failed for %s: %s", manual_id, exc)

    return manual_runs, page_runs
