from __future__ import annotations

import logging
import math
import time
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger("ratelimit")

_LUA = (Path(__file__).resolve().parent / "token_bucket.lua").read_text()


@dataclass
class RateLimitResult:
    allowed: bool
    remaining: int
    retry_after: int  # seconds; 0 when allowed


class RateLimiter:
    """Per-key token bucket backed by Redis + a Lua script.

    The script is loaded once (`SCRIPT LOAD`) and invoked by hash (`EVALSHA`) to
    avoid resending the body each call. The limiter **fails open**: if Redis is
    unavailable, requests are allowed. Governance shouldn't take the gateway down
    — losing rate limiting briefly is better than refusing all traffic.
    """

    def __init__(self, redis, capacity: int, refill_per_sec: float) -> None:
        self._redis = redis
        self._cap = capacity
        self._refill = refill_per_sec
        self._sha: str | None = None

    async def _ensure_script(self) -> str:
        if self._sha is None:
            self._sha = await self._redis.script_load(_LUA)
        return self._sha

    async def _eval(self, key: str, now_ms: int, need: int):
        sha = await self._ensure_script()
        try:
            return await self._redis.evalsha(sha, 1, key, self._cap, self._refill, now_ms, need)
        except Exception as e:
            # Redis was flushed/restarted and forgot the script → reload once.
            if "NOSCRIPT" in str(e).upper():
                self._sha = None
                sha = await self._ensure_script()
                return await self._redis.evalsha(sha, 1, key, self._cap, self._refill, now_ms, need)
            raise

    async def check(self, api_key: str, need: int = 1) -> RateLimitResult:
        if self._redis is None:
            return RateLimitResult(allowed=True, remaining=self._cap, retry_after=0)
        key = f"rl:{api_key}"
        now_ms = int(time.time() * 1000)
        try:
            res = await self._eval(key, now_ms, need)
        except Exception as e:
            log.warning("rate limiter unavailable, failing open: %s", e)
            return RateLimitResult(allowed=True, remaining=self._cap, retry_after=0)

        allowed = bool(int(res[0]))
        retry_ms = int(res[1])
        remaining = int(res[2])
        retry_after = 0 if allowed else max(1, math.ceil(retry_ms / 1000))
        return RateLimitResult(allowed=allowed, remaining=remaining, retry_after=retry_after)
