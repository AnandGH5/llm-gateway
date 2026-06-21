from __future__ import annotations

import json
import logging
from typing import Any

log = logging.getLogger("cache.exact")


class ExactCache:
    """Exact-match response cache backed by Redis.

    Best-effort by design: if Redis is unavailable, every operation degrades to
    a miss / no-op rather than raising. The cache is a performance optimization,
    not a correctness dependency — the gateway must still proxy if Redis is down.
    """

    def __init__(self, redis, ttl_seconds: int) -> None:
        self._redis = redis
        self._ttl = ttl_seconds

    async def get(self, key: str) -> dict[str, Any] | None:
        try:
            raw = await self._redis.get(key)
        except Exception as e:
            log.warning("exact cache get failed (treating as miss): %s", e)
            return None
        if not raw:
            return None
        try:
            return json.loads(raw)
        except (ValueError, TypeError):
            return None

    async def set(self, key: str, response: dict) -> None:
        try:
            await self._redis.set(key, json.dumps(response), ex=self._ttl)
        except Exception as e:
            log.warning("exact cache set failed (skipping write): %s", e)
