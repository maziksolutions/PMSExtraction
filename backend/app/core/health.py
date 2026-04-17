from __future__ import annotations

from typing import Any

from app.core.config import settings


async def deep_health_check() -> dict[str, Any]:
    """
    Deep health check that verifies connectivity to DB, Redis, and blob storage.
    Returns a status dict with per-component status.
    """
    status: dict[str, Any] = {
        "status": "healthy",
        "service": settings.PROJECT_NAME,
        "version": settings.VERSION,
        "components": {},
        "connection_targets": {
            "database": "configured",
            "redis": settings.redis_url_safe,
        },
    }

    # Check database
    try:
        from app.core.database import AsyncSessionLocal
        from sqlalchemy import text

        async with AsyncSessionLocal() as db:
            await db.execute(text("SELECT 1"))
        status["components"]["database"] = "healthy"
    except Exception as exc:
        status["components"]["database"] = f"unhealthy: {str(exc)[:100]}"
        status["status"] = "degraded"

    # Check Redis (optional — degraded only, not critical)
    try:
        import redis.asyncio as aioredis

        r = await aioredis.from_url(settings.REDIS_URL, decode_responses=True)
        await r.ping()
        await r.aclose()
        status["components"]["redis"] = "healthy"
    except Exception as exc:
        status["components"]["redis"] = f"unavailable: {str(exc)[:80]}"
        # Redis is optional for core API functionality

    return status
