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
