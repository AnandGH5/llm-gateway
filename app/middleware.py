from __future__ import annotations

import time

from . import metrics as M
from .metering.usage import Metering

_CHAT_PATH = "/v1/chat/completions"


class MetricsMiddleware:
    """Pure-ASGI middleware that times each chat request and records it.

    Pure ASGI (not BaseHTTPMiddleware) so it doesn't buffer streaming responses.
    It measures time-to-response, labels the latency histogram by the X-Cache
    outcome (Prometheus), and persists the latency into Redis for /stats — reusing
    the Redis client the handler stashed on the request scope, so it shares the
    same connection (and the same fake in tests).
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope.get("type") != "http" or not scope.get("path", "").startswith(_CHAT_PATH):
            await self.app(scope, receive, send)
            return

        start = time.perf_counter()
        captured: dict = {}

        async def send_wrapper(message):
            if message["type"] == "http.response.start":
                elapsed = time.perf_counter() - start
                headers = dict(message.get("headers") or [])
                xcache = headers.get(b"x-cache", b"MISS").decode()
                label = "hit" if xcache.startswith("HIT") else "miss"
                M.observe_request(elapsed, label)
                captured["ms"] = elapsed * 1000.0
            await send(message)

        await self.app(scope, receive, send_wrapper)

        # Persist latency after the response is sent (never adds to it), using the
        # Redis client the handler placed on the scope state.
        redis = (scope.get("state") or {}).get("redis")
        if redis is not None and "ms" in captured:
            try:
                await Metering(redis).record_latency(captured["ms"])
            except Exception:
                pass
