from __future__ import annotations

import asyncio
import json
import time
import uuid
from typing import AsyncIterator

from ..config import settings
from .base import Provider


def _completion_id() -> str:
    return "chatcmpl-" + uuid.uuid4().hex[:24]


def _last_user_message(payload: dict) -> str:
    for msg in reversed(payload.get("messages") or []):
        if msg.get("role") == "user":
            content = msg.get("content")
            if isinstance(content, str):
                return content
            if isinstance(content, list):  # vision-style multi-part content
                parts = [p.get("text", "") for p in content if isinstance(p, dict)]
                return " ".join(parts).strip()
    return ""


def _mock_answer(payload: dict) -> str:
    prompt = _last_user_message(payload)
    return f"[mock] You said: {prompt}" if prompt else "Hello from the mock provider."


class MockProvider(Provider):
    """Returns deterministic OpenAI-shaped responses so the gateway runs with
    zero credentials. Perfect for Phase 1 and for fast tests."""

    name = "mock"

    async def chat_completion(self, payload: dict) -> dict:
        if settings.mock_latency_ms:
            await asyncio.sleep(settings.mock_latency_ms / 1000.0)
        answer = _mock_answer(payload)
        prompt_tokens = max(1, len(_last_user_message(payload).split()))
        completion_tokens = max(1, len(answer.split()))
        return {
            "id": _completion_id(),
            "object": "chat.completion",
            "created": int(time.time()),
            "model": payload.get("model", "mock-model"),
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": answer},
                    "finish_reason": "stop",
                }
            ],
            "usage": {
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": prompt_tokens + completion_tokens,
            },
        }

    async def stream_chat_completion(self, payload: dict) -> AsyncIterator[bytes]:
        if settings.mock_latency_ms:
            await asyncio.sleep(settings.mock_latency_ms / 1000.0)
        cid = _completion_id()
        created = int(time.time())
        model = payload.get("model", "mock-model")
        answer = _mock_answer(payload)

        def chunk(delta: dict, finish_reason: str | None = None) -> bytes:
            data = {
                "id": cid,
                "object": "chat.completion.chunk",
                "created": created,
                "model": model,
                "choices": [
                    {"index": 0, "delta": delta, "finish_reason": finish_reason}
                ],
            }
            return f"data: {json.dumps(data)}\n\n".encode()

        yield chunk({"role": "assistant"})
        for word in answer.split(" "):
            yield chunk({"content": word + " "})
        yield chunk({}, finish_reason="stop")
        yield b"data: [DONE]\n\n"
