from __future__ import annotations

from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest

# In-process metrics. Prometheus scrapes each gateway instance separately, so
# per-process counters are the idiomatic shape (the Redis counters in metering
# remain the cross-instance source of truth for /stats).

REQUESTS = Counter("gateway_requests_total", "Total chat completion requests")
HITS = Counter("gateway_cache_hits_total", "Cache hits", ["type"])
MISSES = Counter("gateway_cache_misses_total", "Cache misses")
RATE_LIMITED = Counter("gateway_rate_limited_total", "Requests rejected by the rate limiter")
FAILOVERS = Counter("gateway_failover_total", "Requests served by the fallback provider")
COST_SAVED = Counter("gateway_cost_saved_usd_total", "Cumulative USD saved by the cache")
COST_SPENT = Counter("gateway_cost_spent_usd_total", "Cumulative USD spent on providers")

# Latency split by cache outcome — this is the histogram that shows the dramatic
# hit-vs-miss contrast in Grafana.
LATENCY = Histogram(
    "gateway_request_latency_seconds",
    "End-to-end request latency",
    ["cache"],  # "hit" | "miss"
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 5.0),
)


def observe_request(seconds: float, cache_label: str) -> None:
    REQUESTS.inc()
    LATENCY.labels(cache=cache_label).observe(seconds)


def record_hit(cache_type: str, saved_usd: float) -> None:
    HITS.labels(type=cache_type).inc()
    COST_SAVED.inc(saved_usd)


def record_miss(cost_usd: float) -> None:
    MISSES.inc()
    COST_SPENT.inc(cost_usd)


def record_rate_limited() -> None:
    RATE_LIMITED.inc()


def record_failover() -> None:
    FAILOVERS.inc()


def render() -> tuple[bytes, str]:
    return generate_latest(), CONTENT_TYPE_LATEST
