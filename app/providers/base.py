from __future__ import annotations

from abc import ABC, abstractmethod
from typing import AsyncIterator


class Provider(ABC):
    """A provider forwards a request to an upstream LLM and normalizes the
    response into the OpenAI shape.

    In Phase 1 the response is returned as-is (mock or real OpenAI). Later
    phases add retry/backoff/failover in the router around these calls.
    """

    name: str = "base"

    @abstractmethod
    async def chat_completion(self, payload: dict) -> dict:
        """Return one complete OpenAI-shaped chat completion response."""
        raise NotImplementedError

    @abstractmethod
    def stream_chat_completion(self, payload: dict) -> AsyncIterator[bytes]:
        """Yield raw SSE bytes in OpenAI streaming format (``data: {...}\\n\\n``)."""
        raise NotImplementedError


class ProviderError(Exception):
    """Retryable upstream failure: 5xx, 429, connection error, missing key."""


class ProviderTimeout(ProviderError):
    """Upstream timed out (retryable)."""


class ProviderBadRequest(Exception):
    """Upstream rejected the request (4xx). NOT retryable — propagate to caller,
    since retrying or failing over won't fix a malformed request."""
