from __future__ import annotations

from typing import AsyncIterator

import httpx

from ..config import settings
from .base import Provider


class OpenAIProvider(Provider):
    """Forwards requests to the real OpenAI API (or any OpenAI-compatible base
    URL). Only used when ``PRIMARY_PROVIDER=openai`` and a key is configured."""

    name = "openai"

    def __init__(self) -> None:
        self._base_url = settings.openai_base_url.rstrip("/")
        self._timeout = settings.provider_timeout_seconds

    def _headers(self) -> dict:
        if not settings.openai_api_key:
            raise RuntimeError(
                "OPENAI_API_KEY is not set; cannot use the openai provider. "
                "Set it in .env, or use PRIMARY_PROVIDER=mock."
            )
        return {
            "Authorization": f"Bearer {settings.openai_api_key}",
            "Content-Type": "application/json",
        }

    async def chat_completion(self, payload: dict) -> dict:
        url = f"{self._base_url}/chat/completions"
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.post(url, headers=self._headers(), json=payload)
            resp.raise_for_status()
            return resp.json()

    async def stream_chat_completion(self, payload: dict) -> AsyncIterator[bytes]:
        url = f"{self._base_url}/chat/completions"
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            async with client.stream(
                "POST", url, headers=self._headers(), json=payload
            ) as resp:
                resp.raise_for_status()
                async for raw in resp.aiter_raw():
                    yield raw
