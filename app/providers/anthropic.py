from __future__ import annotations

import json
import time
import uuid
from typing import AsyncIterator

import httpx

from ..config import settings
from .base import Provider, ProviderBadRequest, ProviderError, ProviderTimeout

ANTHROPIC_VERSION = "2023-06-01"

# Anthropic stop reasons → OpenAI finish reasons.
_FINISH = {
    "end_turn": "stop",
    "max_tokens": "length",
    "stop_sequence": "stop",
    "tool_use": "tool_calls",
}


def _split_system(messages: list[dict]) -> tuple[str, list[dict]]:
    """Anthropic takes the system prompt as a separate top-level field, not as a
    message with role=system. Pull system text out and keep the rest in order."""
    system_parts, convo = [], []
    for m in messages:
        if m.get("role") == "system":
            c = m.get("content")
            if isinstance(c, str):
                system_parts.append(c)
        else:
            convo.append({"role": m.get("role"), "content": m.get("content")})
    return "\n".join(system_parts), convo


def _to_anthropic_payload(payload: dict) -> dict:
    system, convo = _split_system(payload.get("messages", []))
    body: dict = {
        "model": payload.get("model"),
        "messages": convo,
        "max_tokens": payload.get("max_tokens") or 1024,  # Anthropic requires this
    }
    if system:
        body["system"] = system
    for k in ("temperature", "top_p"):
        if payload.get(k) is not None:
            body[k] = payload[k]
    if payload.get("stop"):
        body["stop_sequences"] = payload["stop"]
    return body


def _to_openai_response(data: dict, model: str) -> dict:
    text = "".join(b.get("text", "") for b in data.get("content", []) if b.get("type") == "text")
    usage = data.get("usage", {})
    in_tok = usage.get("input_tokens", 0)
    out_tok = usage.get("output_tokens", 0)
    return {
        "id": data.get("id", "chatcmpl-" + uuid.uuid4().hex[:24]),
        "object": "chat.completion",
        "created": int(time.time()),
        "model": model,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": text},
                "finish_reason": _FINISH.get(data.get("stop_reason"), "stop"),
            }
        ],
        "usage": {
            "prompt_tokens": in_tok,
            "completion_tokens": out_tok,
            "total_tokens": in_tok + out_tok,
        },
    }


class AnthropicProvider(Provider):
    """Calls Anthropic's Messages API and normalizes both the request and the
    response to the OpenAI shape, so callers see a single contract regardless of
    which backend served them."""

    name = "anthropic"

    def __init__(self) -> None:
        self._timeout = settings.provider_timeout_seconds
        self._url = "https://api.anthropic.com/v1/messages"

    def _headers(self) -> dict:
        if not settings.anthropic_api_key:
            raise ProviderError("ANTHROPIC_API_KEY is not set")
        return {
            "x-api-key": settings.anthropic_api_key,
            "anthropic-version": ANTHROPIC_VERSION,
            "content-type": "application/json",
        }

    @staticmethod
    def _raise_for_status(status: int, text: str) -> None:
        if status >= 500 or status == 429:
            raise ProviderError(f"anthropic upstream {status}")
        if status >= 400:
            raise ProviderBadRequest(f"anthropic upstream {status}: {text[:200]}")

    async def chat_completion(self, payload: dict) -> dict:
        body = _to_anthropic_payload(payload)
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.post(self._url, headers=self._headers(), json=body)
        except httpx.TimeoutException as e:
            raise ProviderTimeout(str(e)) from e
        except httpx.HTTPError as e:
            raise ProviderError(str(e)) from e
        self._raise_for_status(resp.status_code, resp.text)
        return _to_openai_response(resp.json(), payload.get("model", "anthropic"))

    async def stream_chat_completion(self, payload: dict) -> AsyncIterator[bytes]:
        body = dict(_to_anthropic_payload(payload))
        body["stream"] = True
        cid = "chatcmpl-" + uuid.uuid4().hex[:24]
        created = int(time.time())
        model = payload.get("model", "anthropic")

        def chunk(delta: dict, finish: str | None = None) -> bytes:
            d = {
                "id": cid,
                "object": "chat.completion.chunk",
                "created": created,
                "model": model,
                "choices": [{"index": 0, "delta": delta, "finish_reason": finish}],
            }
            return f"data: {json.dumps(d)}\n\n".encode()

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                async with client.stream("POST", self._url, headers=self._headers(), json=body) as resp:
                    if resp.status_code >= 400:
                        b = await resp.aread()
                        self._raise_for_status(resp.status_code, b.decode(errors="replace"))
                    # Translate Anthropic's event stream into OpenAI-style chunks.
                    yield chunk({"role": "assistant"})
                    async for line in resp.aiter_lines():
                        if not line.startswith("data:"):
                            continue
                        data = line[len("data:"):].strip()
                        if not data:
                            continue
                        try:
                            evt = json.loads(data)
                        except json.JSONDecodeError:
                            continue
                        etype = evt.get("type")
                        if etype == "content_block_delta":
                            delta = evt.get("delta", {})
                            if delta.get("type") == "text_delta":
                                yield chunk({"content": delta.get("text", "")})
                        elif etype == "message_stop":
                            yield chunk({}, finish="stop")
                            yield b"data: [DONE]\n\n"
                            return
                    yield chunk({}, finish="stop")
                    yield b"data: [DONE]\n\n"
        except httpx.TimeoutException as e:
            raise ProviderTimeout(str(e)) from e
        except httpx.HTTPError as e:
            raise ProviderError(str(e)) from e
