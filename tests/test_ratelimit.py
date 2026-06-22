from __future__ import annotations

import asyncio

from app.providers.router import _backoff
from app.ratelimit.limiter import RateLimiter


class _FakeRedis:
    """Minimal stand-in: script_load returns a sha; evalsha returns a canned
    Lua result so we can test the limiter's parsing without real Redis/Lua."""

    def __init__(self, result):
        self._result = result
        self.calls = 0

    async def script_load(self, _script):
        return "fakesha"

    async def evalsha(self, *_args):
        self.calls += 1
        return self._result


def test_fail_open_without_redis():
    rl = RateLimiter(None, capacity=60, refill_per_sec=1.0)
    res = asyncio.run(rl.check("k"))
    assert res.allowed is True
    assert res.retry_after == 0


def test_allowed_result_parsing():
    fake = _FakeRedis([1, 0, 59])  # allowed, no retry, 59 left
    rl = RateLimiter(fake, capacity=60, refill_per_sec=1.0)
    res = asyncio.run(rl.check("k"))
    assert res.allowed is True
    assert res.remaining == 59
    assert res.retry_after == 0


def test_denied_result_parsing():
    fake = _FakeRedis([0, 4200, 0])  # denied, retry in 4200ms
    rl = RateLimiter(fake, capacity=60, refill_per_sec=1.0)
    res = asyncio.run(rl.check("k"))
    assert res.allowed is False
    assert res.remaining == 0
    assert res.retry_after == 5  # ceil(4200/1000)


def test_fail_open_on_error():
    class Boom:
        async def script_load(self, _):
            raise RuntimeError("redis down")

    rl = RateLimiter(Boom(), capacity=60, refill_per_sec=1.0)
    res = asyncio.run(rl.check("k"))
    assert res.allowed is True  # fails open


def test_backoff_is_bounded_and_grows():
    # base=0.1, cap=2.0 by default; later attempts are >= earlier (modulo jitter)
    d0 = _backoff(0)
    d5 = _backoff(5)
    assert 0 <= d0 <= 0.1 + 0.1
    assert d5 <= 2.0 + 0.1  # capped + jitter
