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
                    no_extraction_reason TEXT,
                    last_extracted_at TIMESTAMPTZ DEFAULT NOW(),
                    PRIMARY KEY (manual_id, page_number)
                );
            """))
            # Ensure column exists if table was created earlier without it
            try:
                await session.execute(text("""
                    ALTER TABLE manual_page_extractions 
                    ADD COLUMN IF NOT EXISTS no_extraction_reason TEXT;
                """))
            except Exception:
                pass
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


async def _async_record_page_run(mid: uuid.UUID, page_number: int, reason: str | None = None) -> None:
    try:
        await ensure_extraction_counter_tables()
        async with AsyncSessionLocal() as session:
            await session.execute(text("""
                INSERT INTO manual_page_extractions (manual_id, page_number, run_count, no_extraction_reason, last_extracted_at)
                VALUES (:mid, :page, 1, :reason, NOW())
                ON CONFLICT (manual_id, page_number) DO UPDATE
                SET run_count = manual_page_extractions.run_count + 1,
                    no_extraction_reason = COALESCE(:reason, manual_page_extractions.no_extraction_reason),
                    last_extracted_at = NOW();
            """), {"mid": mid, "page": page_number, "reason": reason})
            await session.commit()
    except Exception as exc:
        logger.warning("Failed to record page run for %s p.%s: %s", mid, page_number, exc)


async def _async_record_page_reason(mid: uuid.UUID, page_number: int, reason: str | None) -> None:
    try:
        await ensure_extraction_counter_tables()
        async with AsyncSessionLocal() as session:
            await session.execute(text("""
                INSERT INTO manual_page_extractions (manual_id, page_number, run_count, no_extraction_reason, last_extracted_at)
                VALUES (:mid, :page, 1, :reason, NOW())
                ON CONFLICT (manual_id, page_number) DO UPDATE
                SET no_extraction_reason = :reason,
                    last_extracted_at = NOW();
            """), {"mid": mid, "page": page_number, "reason": reason})
            await session.commit()
    except Exception as exc:
        logger.warning("Failed to record page reason for %s p.%s: %s", mid, page_number, exc)


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


def record_page_extraction_run(manual_id_str: str, page_number: int, reason: str | None = None) -> None:
    """Non-blocking call to increment run count for a specific page."""
    try:
        mid = uuid.UUID(str(manual_id_str))
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(_async_record_page_run(mid, int(page_number), reason))
        except RuntimeError:
            import threading
            threading.Thread(target=lambda: asyncio.run(_async_record_page_run(mid, int(page_number), reason)), daemon=True).start()
    except Exception as exc:
        logger.warning("record_page_extraction_run error: %s", exc)


def record_page_extraction_reason(manual_id_str: str, page_number: int, reason: str | None) -> None:
    """Non-blocking call to set the zero-extraction reason for a specific page."""
    try:
        mid = uuid.UUID(str(manual_id_str))
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(_async_record_page_reason(mid, int(page_number), reason))
        except RuntimeError:
            import threading
            threading.Thread(target=lambda: asyncio.run(_async_record_page_reason(mid, int(page_number), reason)), daemon=True).start()
    except Exception as exc:
        logger.warning("record_page_extraction_reason error: %s", exc)


async def get_extraction_counts(manual_id: uuid.UUID) -> Tuple[int, Dict[int, int], Dict[int, str]]:
    """
    Returns (manual_run_count, page_run_counts_dict, page_reasons_dict) for a manual.
    """
    await ensure_extraction_counter_tables()
    manual_runs = 0
    page_runs: Dict[int, int] = {}
    page_reasons: Dict[int, str] = {}
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
                text("SELECT page_number, run_count, no_extraction_reason FROM manual_page_extractions WHERE manual_id = :mid"),
                {"mid": manual_id}
            )
            for r in p_res.fetchall():
                pno = int(r[0])
                page_runs[pno] = int(r[1] or 0)
                if r[2]:
                    page_reasons[pno] = str(r[2]).strip()
    except Exception as exc:
        logger.warning("get_extraction_counts failed for %s: %s", manual_id, exc)

    return manual_runs, page_runs, page_reasons
