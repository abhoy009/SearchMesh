"""Redis cache layer for SearchMesh.

Wraps the redis.asyncio client to store/retrieve cached search queries and URL fetches.
Provides graceful fallback if Redis is unavailable.
"""
from __future__ import annotations

import hashlib
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from redis.asyncio import Redis

logger = logging.getLogger(__name__)


class SearchMeshCache:
    def __init__(self, redis: Redis | None = None) -> None:
        self.redis = redis

    def _search_key(self, query: str) -> str:
        return f"search:{hashlib.sha256(query.strip().lower().encode()).hexdigest()}"

    def _fetch_key(self, url: str) -> str:
        return f"fetch:{hashlib.sha256(url.strip().encode()).hexdigest()}"

    async def get(self, key: str) -> str | None:
        """Retrieve key value from Redis. Fails open (returns None) on Redis errors."""
        if not self.redis:
            return None
        try:
            val = await self.redis.get(key)
            if val is not None:
                return val.decode("utf-8") if isinstance(val, bytes) else str(val)
            return None
        except Exception as exc:
            logger.warning("Redis GET failed for key %s: %s", key, exc)
            return None

    async def set(self, key: str, value: str, ttl: int) -> None:
        """Set key value in Redis with TTL. Fails open on Redis errors."""
        if not self.redis:
            return
        try:
            await self.redis.setex(key, ttl, value)
        except Exception as exc:
            logger.warning("Redis SET failed for key %s: %s", key, exc)

    async def delete_pattern(self, pattern: str) -> int:
        """Delete all keys matching pattern. Returns count of deleted keys. Fails open (returns 0) on Redis errors."""
        if not self.redis:
            return 0
        try:
            keys = await self.redis.keys(pattern)
            if keys:
                res = await self.redis.delete(*keys)
                return int(res)
            return 0
        except Exception as exc:
            logger.warning("Redis delete_pattern failed for pattern %s: %s", pattern, exc)
            return 0
