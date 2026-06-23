from __future__ import annotations

import logging
import math
import time

log = logging.getLogger("metering.usage")

# Redis counter keys.
REQUESTS = "stat:requests_total"
HITS_EXACT = "stat:hits_exact"
HITS_SEMANTIC = "stat:hits_semantic"   # populated from Phase 3
MISSES = "stat:misses_total"
COST_SAVED = "stat:cost_saved_usd"
COST_SPENT = "stat:cost_spent_usd"
TOKENS = "stat:tokens_total"

# Rolling samples for latency percentiles and RPS (capped lists).
LATENCIES = "stat:latency_ms"
REQ_TS = "stat:req_ts_ms"
_SAMPLE_CAP = 1000


def _percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    k = (len(s) - 1) * (p / 100.0)
    lo = math.floor(k)
    hi = math.ceil(k)
    if lo == hi:
        return float(s[int(k)])
    return float(s[lo] + (s[hi] - s[lo]) * (k - lo))


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

    async def record_latency(self, latency_ms: float) -> None:
        """Push a latency sample (and a timestamp) into capped Redis lists, used
        by /stats for percentiles and a rough RPS."""
        try:
            now_ms = int(time.time() * 1000)
            pipe = self._redis.pipeline(transaction=False)
            pipe.lpush(LATENCIES, latency_ms)
            pipe.ltrim(LATENCIES, 0, _SAMPLE_CAP - 1)
            pipe.lpush(REQ_TS, now_ms)
            pipe.ltrim(REQ_TS, 0, _SAMPLE_CAP - 1)
            await pipe.execute()
        except Exception as e:
            log.warning("record_latency failed: %s", e)

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

        # Latency percentiles + rough RPS from the rolling samples.
        try:
            raw_lat = await self._redis.lrange(LATENCIES, 0, -1)
            raw_ts = await self._redis.lrange(REQ_TS, 0, -1)
        except Exception:
            raw_lat, raw_ts = [], []
        lat_ms = [float(x) for x in raw_lat]
        now_ms = int(time.time() * 1000)
        recent = [t for t in (int(x) for x in raw_ts) if now_ms - t <= 5000]
        rps = round(len(recent) / 5.0, 2)

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
            "latency_ms": {
                "p50": round(_percentile(lat_ms, 50), 2),
                "p95": round(_percentile(lat_ms, 95), 2),
                "p99": round(_percentile(lat_ms, 99), 2),
            },
            "rps": rps,
        }
