from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Optional

import redis.asyncio as aioredis

from app.core.config import settings

logger = logging.getLogger(__name__)
_redis_client: Optional[aioredis.Redis] = None
_redis_unavailable_until: float = 0.0
_REDIS_TIMEOUT_SECONDS = 1.0
_REDIS_RETRY_COOLDOWN_SECONDS = 60.0


async def _get_redis() -> Optional[aioredis.Redis]:
    global _redis_client, _redis_unavailable_until
    if not settings.REDIS_URL:
        return None
    now = time.time()
    if _redis_unavailable_until > now:
        return None
    if _redis_client is None:
        try:
            client = aioredis.from_url(
                settings.REDIS_URL,
                decode_responses=True,
                socket_connect_timeout=_REDIS_TIMEOUT_SECONDS,
                socket_timeout=_REDIS_TIMEOUT_SECONDS,
                retry_on_timeout=False,
                health_check_interval=30,
            )
            await asyncio.wait_for(client.ping(), timeout=_REDIS_TIMEOUT_SECONDS)
            _redis_client = client
            _redis_unavailable_until = 0.0
        except Exception as exc:
            logger.warning("Failed to initialize Redis token store: %s", exc)
            _redis_client = None
            _redis_unavailable_until = time.time() + _REDIS_RETRY_COOLDOWN_SECONDS
            return None
    return _redis_client


def _token_key(jti: str) -> str:
    return f"auth:blocklist:{jti}"


async def is_token_revoked(payload: dict[str, Any]) -> bool:
    global _redis_client, _redis_unavailable_until
    jti = payload.get("jti")
    if not jti:
        return False
    redis_client = await _get_redis()
    if redis_client is None:
        return False
    try:
        return await asyncio.wait_for(
            redis_client.exists(_token_key(str(jti))),
            timeout=_REDIS_TIMEOUT_SECONDS,
        ) > 0
    except Exception as exc:
        logger.warning("Redis blocklist read failed: %s", exc)
        _redis_client = None
        _redis_unavailable_until = time.time() + _REDIS_RETRY_COOLDOWN_SECONDS
        return False


async def revoke_token_payload(payload: dict[str, Any]) -> None:
    global _redis_client, _redis_unavailable_until
    jti = payload.get("jti")
    exp = payload.get("exp")
    if not jti or not exp:
        return
    redis_client = await _get_redis()
    if redis_client is None:
        return

    try:
        ttl_seconds = max(1, int(exp) - int(time.time()))
        await asyncio.wait_for(
            redis_client.setex(_token_key(str(jti)), ttl_seconds, "1"),
            timeout=_REDIS_TIMEOUT_SECONDS,
        )
    except Exception as exc:
        logger.warning("Redis blocklist write failed: %s", exc)
        _redis_client = None
        _redis_unavailable_until = time.time() + _REDIS_RETRY_COOLDOWN_SECONDS
