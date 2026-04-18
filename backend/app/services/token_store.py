from __future__ import annotations

import logging
import time
from typing import Any, Optional

import redis.asyncio as aioredis

from app.core.config import settings

logger = logging.getLogger(__name__)
_redis_client: Optional[aioredis.Redis] = None


async def _get_redis() -> Optional[aioredis.Redis]:
    global _redis_client
    if not settings.REDIS_URL:
        return None
    if _redis_client is None:
        try:
            _redis_client = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
        except Exception as exc:
            logger.warning("Failed to initialize Redis token store: %s", exc)
            return None
    return _redis_client


def _token_key(jti: str) -> str:
    return f"auth:blocklist:{jti}"


async def is_token_revoked(payload: dict[str, Any]) -> bool:
    jti = payload.get("jti")
    if not jti:
        return False
    redis_client = await _get_redis()
    if redis_client is None:
        return False
    try:
        return await redis_client.exists(_token_key(str(jti))) > 0
    except Exception as exc:
        logger.warning("Redis blocklist read failed: %s", exc)
        return False


async def revoke_token_payload(payload: dict[str, Any]) -> None:
    jti = payload.get("jti")
    exp = payload.get("exp")
    if not jti or not exp:
        return
    redis_client = await _get_redis()
    if redis_client is None:
        return

    try:
        ttl_seconds = max(1, int(exp) - int(time.time()))
        await redis_client.setex(_token_key(str(jti)), ttl_seconds, "1")
    except Exception as exc:
        logger.warning("Redis blocklist write failed: %s", exc)
