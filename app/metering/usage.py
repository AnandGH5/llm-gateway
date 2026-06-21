from __future__ import annotations

import logging

log = logging.getLogger("metering.usage")

# Redis counter keys.
REQUESTS = "stat:requests_total"
HITS_EXACT = "stat:hits_exact"
HITS_SEMANTIC = "stat:hits_semantic"   # populated from Phase 3
MISSES = "stat:misses_total"
COST_SAVED = "stat:cost_saved_usd"
COST_SPENT = "stat:cost_spent_usd"
TOKENS = "stat:tokens_total"


class Metering:
    """Live counters in Redis. Like the cache, this is best-effort: a metering
    failure must never break a request, so every method swallows Redis errors."""

    def __init__(self, redis) -> None:
        self._redis = redis

    async def record_hit(self, *, total_tokens: int, saved_usd: float, cache_type: str = "exact") -> None:
        try:
            pipe = self._redis.pipeline(transaction=False)
            pipe.incr(REQUESTS)
            pipe.incr(HITS_EXACT if cache_type == "exact" else HITS_SEMANTIC)
            pipe.incrbyfloat(COST_SAVED, saved_usd)
            pipe.incrby(TOKENS, total_tokens)
            await pipe.execute()
        except Exception as e:
            log.warning("record_hit failed: %s", e)

    async def record_miss(self, *, total_tokens: int, cost_usd: float) -> None:
        try:
            pipe = self._redis.pipeline(transaction=False)
            pipe.incr(REQUESTS)
            pipe.incr(MISSES)
            pipe.incrbyfloat(COST_SPENT, cost_usd)
            pipe.incrby(TOKENS, total_tokens)
            await pipe.execute()
        except Exception as e:
            log.warning("record_miss failed: %s", e)

    async def record_passthrough(self) -> None:
        """For streamed requests: counted as served, but cost is unknown in v1."""
        try:
            pipe = self._redis.pipeline(transaction=False)
            pipe.incr(REQUESTS)
            pipe.incr(MISSES)
            await pipe.execute()
        except Exception as e:
            log.warning("record_passthrough failed: %s", e)

    async def stats(self) -> dict:
        keys = [REQUESTS, HITS_EXACT, HITS_SEMANTIC, MISSES, COST_SAVED, COST_SPENT, TOKENS]
        try:
            vals = await self._redis.mget(keys)
        except Exception as e:
            log.warning("stats read failed: %s", e)
            vals = [None] * len(keys)

        requests = int(vals[0] or 0)
        hits_exact = int(vals[1] or 0)
        hits_semantic = int(vals[2] or 0)
        misses = int(vals[3] or 0)
        cost_saved = float(vals[4] or 0.0)
        cost_spent = float(vals[5] or 0.0)
        tokens = int(vals[6] or 0)

        hits = hits_exact + hits_semantic
        hit_rate = hits / requests if requests else 0.0
        denom = cost_saved + cost_spent
        cost_reduction = (cost_saved / denom) if denom else 0.0

        return {
            "requests_total": requests,
            "hits": {"exact": hits_exact, "semantic": hits_semantic, "total": hits},
            "misses_total": misses,
            "hit_rate": round(hit_rate, 4),
            "cost_saved_usd": round(cost_saved, 6),
            "cost_spent_usd": round(cost_spent, 6),
            "cost_reduction_pct": round(cost_reduction * 100, 2),
            "tokens_total": tokens,
        }
