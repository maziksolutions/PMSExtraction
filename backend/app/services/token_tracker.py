import asyncio
import datetime
import logging
from typing import Any
from sqlalchemy import text
from app.core.database import AsyncSessionLocal

logger = logging.getLogger(__name__)

# Official Anthropic Claude 3.5 Sonnet / Claude Sonnet 4.6 Pricing:
# Standard Input: $3.00 / MTok ($0.000003 per token)
# Cache Write: $3.75 / MTok ($0.00000375 per token)
# Cache Read: $0.30 / MTok ($0.0000003 per token)
# Output: $15.00 / MTok ($0.000015 per token)

INPUT_COST_PER_TOKEN = 3.0 / 1_000_000.0
CACHE_WRITE_COST_PER_TOKEN = 3.75 / 1_000_000.0
CACHE_READ_COST_PER_TOKEN = 0.30 / 1_000_000.0
OUTPUT_COST_PER_TOKEN = 15.0 / 1_000_000.0


async def _persist_usage(dt: datetime.date, in_tokens: int, out_tokens: int, cost: float) -> None:
    try:
        async with AsyncSessionLocal() as session:
            await session.execute(
                text("""
                    INSERT INTO claude_daily_costs (date, input_tokens, output_tokens, cost)
                    VALUES (:dt, :in_tok, :out_tok, :cost)
                    ON CONFLICT (date) DO UPDATE
                    SET input_tokens = claude_daily_costs.input_tokens + EXCLUDED.input_tokens,
                        output_tokens = claude_daily_costs.output_tokens + EXCLUDED.output_tokens,
                        cost = claude_daily_costs.cost + EXCLUDED.cost;
                """),
                {"dt": dt, "in_tok": in_tokens, "out_tok": out_tokens, "cost": cost}
            )
            await session.commit()
    except Exception as exc:
        logger.warning("token_tracker: failed to persist token usage: %s", exc)


def calculate_claude_cost(
    raw_input_tokens: int,
    output_tokens: int,
    cache_creation_input_tokens: int = 0,
    cache_read_input_tokens: int = 0
) -> float:
    """
    Computes exact dollar spend based on official Anthropic Claude pricing:
    - Standard Input: $3.00 / MTok
    - Cache Creation: $3.75 / MTok
    - Cache Read: $0.30 / MTok
    - Output: $15.00 / MTok
    """
    return (
        (raw_input_tokens * INPUT_COST_PER_TOKEN)
        + (cache_creation_input_tokens * CACHE_WRITE_COST_PER_TOKEN)
        + (cache_read_input_tokens * CACHE_READ_COST_PER_TOKEN)
        + (output_tokens * OUTPUT_COST_PER_TOKEN)
    )


def record_claude_usage(usage: Any, model: str = "claude-sonnet-4-6") -> dict | None:
    """
    Records token usage and calculated dollar spend from a Claude API response.
    Correctly accounts for standard input tokens, prompt cache creation,
    prompt cache reads, and output tokens.
    """
    if not usage:
        return None
    try:
        raw_in = int(getattr(usage, "input_tokens", 0) or 0)
        c_create = int(getattr(usage, "cache_creation_input_tokens", 0) or 0)
        c_read = int(getattr(usage, "cache_read_input_tokens", 0) or 0)
        raw_out = int(getattr(usage, "output_tokens", 0) or 0)

        total_in = raw_in + c_create + c_read
        total_out = raw_out

        cost = calculate_claude_cost(raw_in, raw_out, c_create, c_read)

        today = datetime.datetime.utcnow().date()

        try:
            loop = asyncio.get_running_loop()
            loop.create_task(_persist_usage(today, total_in, total_out, cost))
        except RuntimeError:
            import threading
            threading.Thread(
                target=lambda: asyncio.run(_persist_usage(today, total_in, total_out, cost)),
                daemon=True,
            ).start()

        return {
            "total_input_tokens": total_in,
            "output_tokens": total_out,
            "cost_usd": cost,
        }
    except Exception as exc:
        logger.warning("token_tracker: unexpected error in record_claude_usage: %s", exc)
        return None


async def seed_historical_claude_costs_startup() -> None:
    """
    Seeds historical baseline usage from Claude Console if database has fewer than 2 records.
    Ensures dashboard statistics match the Claude Console totals from Day 1.
    """
    try:
        async with AsyncSessionLocal() as session:
            count_res = await session.execute(text("SELECT COUNT(*) FROM claude_daily_costs;"))
            count = count_res.scalar() or 0
            if count >= 2:
                # Already populated
                return

            baseline_records = [
                (datetime.date(2026, 11, 5), 3840000, 383112, 17.2667),
                (datetime.date(2026, 11, 4), 1240000, 123824, 5.5774),
                (datetime.date(2026, 11, 3), 2900000, 285141, 12.9771),
                (datetime.date(2026, 11, 2), 3100, 436, 0.0158),
                (datetime.date(2026, 11, 1), 21362018, 1913394, 92.7870),
            ]

            for dt, in_tok, out_tok, cost in baseline_records:
                await session.execute(
                    text("""
                        INSERT INTO claude_daily_costs (date, input_tokens, output_tokens, cost)
                        VALUES (:dt, :in_tok, :out_tok, :cost)
                        ON CONFLICT (date) DO UPDATE
                        SET input_tokens = EXCLUDED.input_tokens,
                            output_tokens = EXCLUDED.output_tokens,
                            cost = EXCLUDED.cost;
                    """),
                    {"dt": dt, "in_tok": in_tok, "out_tok": out_tok, "cost": cost}
                )
            await session.commit()
            print("[STARTUP TOKEN TRACKER] Successfully initialized historical Claude console usage records!", flush=True)
    except Exception as exc:
        print(f"[STARTUP TOKEN TRACKER ERROR] Failed to seed historical claude costs: {exc}", flush=True)
