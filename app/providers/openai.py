from __future__ import annotations

from typing import AsyncIterator

import httpx

from ..config import settings
from .base import Provider, ProviderBadRequest, ProviderError, ProviderTimeout


class OpenAIProvider(Provider):
    """Forwards requests to the real OpenAI API (or any OpenAI-compatible base
    URL). Upstream failures are mapped to typed errors so the router can decide
    whether to retry, fail over, or propagate."""

    name = "openai"

    def __init__(self) -> None:
        self._base_url = settings.openai_base_url.rstrip("/")
        self._timeout = settings.provider_timeout_seconds

    def _headers(self) -> dict:
        if not settings.openai_api_key:
            raise ProviderError("OPENAI_API_KEY is not set")
        return {
            "Authorization": f"Bearer {settings.openai_api_key}",
            "Content-Type": "application/json",
        }

    @staticmethod
    def _raise_for_status(status: int, text: str) -> None:
        if status >= 500 or status == 429:
            raise ProviderError(f"openai upstream {status}")
        if status >= 400:
            raise ProviderBadRequest(f"openai upstream {status}: {text[:200]}")

    async def chat_completion(self, payload: dict) -> dict:
        url = f"{self._base_url}/chat/completions"
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.post(url, headers=self._headers(), json=payload)
        except httpx.TimeoutException as e:
            raise ProviderTimeout(str(e)) from e
        except httpx.HTTPError as e:
            raise ProviderError(str(e)) from e
        self._raise_for_status(resp.status_code, resp.text)
        return resp.json()

    async def stream_chat_completion(self, payload: dict) -> AsyncIterator[bytes]:
        url = f"{self._base_url}/chat/completions"
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                async with client.stream("POST", url, headers=self._headers(), json=payload) as resp:
                    if resp.status_code >= 400:
                        body = await resp.aread()
                        self._raise_for_status(resp.status_code, body.decode(errors="replace"))
                    async for raw in resp.aiter_raw():
                        yield raw
        except httpx.TimeoutException as e:
            raise ProviderTimeout(str(e)) from e
        except httpx.HTTPError as e:
            raise ProviderError(str(e)) from e
