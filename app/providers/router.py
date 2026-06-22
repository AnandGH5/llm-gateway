from __future__ import annotations

import asyncio
import logging
import random
from dataclasses import dataclass
from typing import AsyncIterator

from ..config import settings
from .anthropic import AnthropicProvider
from .base import Provider, ProviderBadRequest, ProviderError
from .failing import AlwaysFailProvider
from .mock import MockProvider
from .openai import OpenAIProvider

log = logging.getLogger("providers.router")

_REGISTRY: dict[str, type[Provider]] = {
    "mock": MockProvider,
    "openai": OpenAIProvider,
    "anthropic": AnthropicProvider,
    "always_fail": AlwaysFailProvider,
}


class AllProvidersFailed(Exception):
    """Every provider in the chain exhausted its retries."""


@dataclass
class CompletionResult:
    response: dict
    provider: str


def _build(name: str) -> Provider:
    key = (name or "").lower()
    if key not in _REGISTRY:
        raise ValueError(f"Unknown provider '{name}'. Available: {', '.join(_REGISTRY)}")
    return _REGISTRY[key]()


def get_provider() -> Provider:
    """Single primary provider (kept for callers that don't need failover)."""
    return _build(settings.primary_provider)


def _backoff(attempt: int) -> float:
    """Exponential backoff with jitter: base * 2^attempt, capped, plus a random
    fraction to avoid synchronized retry storms (thundering herd)."""
    base = settings.retry_backoff_base_seconds
    cap = settings.retry_backoff_max_seconds
    return min(cap, base * (2 ** attempt)) + random.uniform(0, base)


async def _prepend(first: bytes, agen: AsyncIterator[bytes]) -> AsyncIterator[bytes]:
    yield first
    async for chunk in agen:
        yield chunk


async def _empty() -> AsyncIterator[bytes]:
    return
    yield b""  # pragma: no cover — makes this an async generator


class ProviderRouter:
    """Routes a request to the primary provider, retrying with backoff, and
    failing over to the fallback provider on retryable errors. A 4xx
    (ProviderBadRequest) is never retried — it's the caller's fault."""

    def __init__(self) -> None:
        self._chain = self._build_chain()

    @staticmethod
    def _build_chain() -> list[str]:
        names = [settings.primary_provider]
        fb = settings.fallback_provider
        if fb and fb.lower() != settings.primary_provider.lower():
            names.append(fb)
        return names

    async def complete(self, payload: dict) -> CompletionResult:
        retries = max(1, settings.max_retries)
        last: Exception | None = None
        for name in self._chain:
            provider = _build(name)
            for attempt in range(retries):
                try:
                    resp = await provider.chat_completion(payload)
                    return CompletionResult(response=resp, provider=name)
                except ProviderBadRequest:
                    raise  # don't retry or fail over on a bad request
                except ProviderError as e:
                    last = e
                    log.warning("provider %s attempt %d/%d failed: %s", name, attempt + 1, retries, e)
                    if attempt < retries - 1:
                        await asyncio.sleep(_backoff(attempt))
            log.warning("provider %s exhausted, failing over", name)
        raise AllProvidersFailed(str(last) if last else "all providers failed")

    async def stream(self, payload: dict) -> tuple[str, AsyncIterator[bytes]]:
        """Pick a provider that can start streaming, failing over if the first
        chunk errors. Once bytes have been sent we can't fail over, so failover
        only applies at the start of the stream."""
        last: Exception | None = None
        for name in self._chain:
            provider = _build(name)
            agen = provider.stream_chat_completion(payload)
            try:
                first = await agen.__anext__()
            except StopAsyncIteration:
                return name, _empty()
            except ProviderBadRequest:
                raise
            except ProviderError as e:
                last = e
                log.warning("stream provider %s failed at start: %s", name, e)
                continue
            return name, _prepend(first, agen)
        raise AllProvidersFailed(str(last) if last else "all providers failed (stream)")


def get_router() -> ProviderRouter:
    """FastAPI dependency-style factory; reads current settings each call."""
    return ProviderRouter()
