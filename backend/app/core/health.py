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

    # Check Redis
    try:
        import redis.asyncio as aioredis

        r = await aioredis.from_url(settings.REDIS_URL, decode_responses=True)
        await r.ping()
        await r.aclose()
        status["components"]["redis"] = "healthy"
    except Exception as exc:
        status["components"]["redis"] = f"unhealthy: {str(exc)[:100]}"
        status["status"] = "degraded"

    # Check blob storage (MinIO / Azure Blob)
    try:
        import boto3
        from botocore.exceptions import ClientError

        s3 = boto3.client(
            "s3",
            endpoint_url=settings.BLOB_ENDPOINT_URL,
            aws_access_key_id=settings.BLOB_ACCESS_KEY,
            aws_secret_access_key=settings.BLOB_SECRET_KEY,
        )
        s3.list_buckets()
        status["components"]["blob_storage"] = "healthy"
    except Exception as exc:
        status["components"]["blob_storage"] = f"unhealthy: {str(exc)[:100]}"
        # Don't degrade status for blob storage — not critical for read operations

    return status
