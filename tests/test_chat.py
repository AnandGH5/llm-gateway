from __future__ import annotations

import fakeredis.aioredis
from fastapi.testclient import TestClient

from app.db import get_db_pool
from app.deps import get_redis
from app.main import app

# Swap the real Redis for an in-memory fake so the cache/metering paths are
# exercised deterministically, with no Redis server needed.
_fake = fakeredis.aioredis.FakeRedis(decode_responses=True)


async def _fake_redis():
    return _fake


# No Postgres in unit/e2e tests: returning None makes the semantic tier degrade
# to a no-op (it never loads the embedding model), so these stay Phase-2-scoped.
def _no_pool():
    return None


app.dependency_overrides[get_redis] = _fake_redis
app.dependency_overrides[get_db_pool] = _no_pool

client = TestClient(app)
AUTH = {"Authorization": "Bearer gw_sk_demo123"}


def _body(text="Hello there"):
    return {"model": "gpt-4o-mini", "messages": [{"role": "user", "content": text}]}


def test_health():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_requires_auth():
    r = client.post("/v1/chat/completions", json=_body())
    assert r.status_code == 401


def test_rejects_bad_key():
    r = client.post("/v1/chat/completions", headers={"Authorization": "Bearer nope"}, json=_body())
    assert r.status_code == 401


def test_first_call_misses_second_call_hits():
    body = _body("unique-prompt-for-hit-test")

    first = client.post("/v1/chat/completions", headers=AUTH, json=body)
    assert first.status_code == 200
    assert first.headers["x-cache"] == "MISS"

    second = client.post("/v1/chat/completions", headers=AUTH, json=body)
    assert second.status_code == 200
    assert second.headers["x-cache"] == "HIT-EXACT"
    assert float(second.headers["x-cost-saved-usd"]) > 0
    # Same content served from cache.
    assert first.json()["choices"][0]["message"]["content"] == \
        second.json()["choices"][0]["message"]["content"]


def test_stats_reflect_activity():
    r = client.get("/stats")
    assert r.status_code == 200
    s = r.json()
    assert s["requests_total"] >= 2
    assert s["hits"]["exact"] >= 1
    assert s["cost_saved_usd"] > 0


def test_streaming_still_works():
    with client.stream(
        "POST", "/v1/chat/completions", headers=AUTH,
        json={**_body("stream please"), "stream": True},
    ) as r:
        assert r.status_code == 200
        assert r.headers["x-cache"] == "MISS"
        data = b"".join(r.iter_bytes())
    assert b"[DONE]" in data
