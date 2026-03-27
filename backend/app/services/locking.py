from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Optional

import redis.asyncio as aioredis

from app.core.config import settings

logger = logging.getLogger(__name__)


class RecordLockService:
    """Redis-based optimistic record locking."""

    LOCK_TTL = 300  # 5 minutes

    def __init__(self) -> None:
        self._redis: Optional[aioredis.Redis] = None

    async def _get_redis(self) -> aioredis.Redis:
        if self._redis is None:
            self._redis = await aioredis.from_url(settings.REDIS_URL, decode_responses=True)
        return self._redis

    def _key(self, record_type: str, record_id: str) -> str:
        return f"lock:{record_type}:{record_id}"

    async def acquire_lock(
        self, record_type: str, record_id: str, user_id: str, user_name: str = ""
    ) -> bool:
        """Try to acquire a lock. Returns True if successful, False if already locked."""
        try:
            r = await self._get_redis()
            key = self._key(record_type, record_id)
            value = json.dumps(
                {
                    "user_id": user_id,
                    "user_name": user_name,
                    "acquired_at": datetime.now(timezone.utc).isoformat(),
                }
            )
            # SET NX EX = set if not exists with TTL
            result = await r.set(key, value, nx=True, ex=self.LOCK_TTL)
            return result is True
        except Exception as exc:
            logger.warning("Failed to acquire lock %s/%s: %s", record_type, record_id, exc)
            return True  # Fail open — allow edit if Redis is unavailable

    async def release_lock(
        self, record_type: str, record_id: str, user_id: str
    ) -> bool:
        """Release lock if owned by user_id. Returns True if released."""
        try:
            r = await self._get_redis()
            key = self._key(record_type, record_id)
            raw = await r.get(key)
            if raw is None:
                return True
            info = json.loads(raw)
            if info.get("user_id") == user_id:
                await r.delete(key)
                return True
            return False
        except Exception as exc:
            logger.warning("Failed to release lock %s/%s: %s", record_type, record_id, exc)
            return False

    async def extend_lock(
        self, record_type: str, record_id: str, user_id: str
    ) -> bool:
        """Extend TTL on an existing lock owned by user_id."""
        try:
            r = await self._get_redis()
            key = self._key(record_type, record_id)
            raw = await r.get(key)
            if raw is None:
                return False
            info = json.loads(raw)
            if info.get("user_id") != user_id:
                return False
            await r.expire(key, self.LOCK_TTL)
            return True
        except Exception as exc:
            logger.warning("Failed to extend lock %s/%s: %s", record_type, record_id, exc)
            return False

    async def get_lock_info(
        self, record_type: str, record_id: str
    ) -> Optional[dict]:
        """Get current lock info. Returns None if not locked."""
        try:
            r = await self._get_redis()
            key = self._key(record_type, record_id)
            raw = await r.get(key)
            if raw is None:
                return None
            info = json.loads(raw)
            info["record_type"] = record_type
            info["record_id"] = record_id
            return info
        except Exception as exc:
            logger.warning("Failed to get lock info %s/%s: %s", record_type, record_id, exc)
            return None

    async def get_vessel_locks(self, vessel_id: str) -> list[dict]:
        """Get all active locks for a vessel (by scanning keys)."""
        try:
            r = await self._get_redis()
            pattern = "lock:*"
            keys = []
            async for key in r.scan_iter(pattern):
                keys.append(key)

            locks = []
            for key in keys:
                raw = await r.get(key)
                if raw:
                    info = json.loads(raw)
                    parts = key.split(":", 2)
                    info["record_type"] = parts[1] if len(parts) > 1 else ""
                    info["record_id"] = parts[2] if len(parts) > 2 else ""
                    locks.append(info)
            return locks
        except Exception as exc:
            logger.warning("Failed to get vessel locks for %s: %s", vessel_id, exc)
            return []


lock_service = RecordLockService()
