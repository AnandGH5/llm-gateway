from __future__ import annotations

from typing import AsyncIterator

from .base import Provider, ProviderError


class AlwaysFailProvider(Provider):
    """A provider that always fails. Not for production — it exists so tests and
    benchmarks can exercise the retry/failover path deterministically (set it as
    the primary with a real fallback)."""

    name = "always_fail"

    async def chat_completion(self, payload: dict) -> dict:
        raise ProviderError("always_fail provider: simulated failure")

    async def stream_chat_completion(self, payload: dict) -> AsyncIterator[bytes]:
        raise ProviderError("always_fail provider: simulated failure")
        yield b""  # unreachable — makes this a valid async generator
