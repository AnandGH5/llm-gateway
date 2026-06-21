from __future__ import annotations

import hashlib
import json
from typing import Any

EXACT_PREFIX = "cache:exact:"


def _normalize_text(text: str) -> str:
    """Lowercase, strip, and collapse internal whitespace.

    So "  What's   the Capital of France? " and "what's the capital of france?"
    map to the same string, and therefore the same cache key.
    """
    return " ".join(text.lower().split())


def _extract_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):  # vision-style multi-part content
        return " ".join(p.get("text", "") for p in content if isinstance(p, dict))
    return ""


def _messages_signature(messages: list[dict]) -> list[dict]:
    return [
        {"role": m.get("role", ""), "content": _normalize_text(_extract_text(m.get("content")))}
        for m in messages
    ]


def make_cache_key(payload: dict) -> str:
    """Build a deterministic exact-match key.

    The key is scoped by everything that can change the answer: the model, the
    sampling params, and the (normalized) conversation. A gpt-4o answer must not
    serve a gpt-3.5 request; a temperature=0 answer must not serve temperature=1.
    """
    fingerprint = {
        "model": payload.get("model"),
        "temperature": payload.get("temperature"),
        "max_tokens": payload.get("max_tokens"),
        "top_p": payload.get("top_p"),
        "messages": _messages_signature(payload.get("messages", [])),
    }
    blob = json.dumps(fingerprint, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(blob.encode("utf-8")).hexdigest()
    return EXACT_PREFIX + digest


def is_cacheable(payload: dict, max_temperature: float = 1.0) -> bool:
    """Whether this request may be served from / written to the cache.

    We skip caching when the caller clearly wants fresh/varied output:
    an explicit no_cache flag, multiple completions (n>1), or a high temperature.
    Correctness over hit rate.
    """
    if payload.get("no_cache") is True:
        return False
    if (payload.get("n") or 1) > 1:
        return False
    temp = payload.get("temperature")
    if temp is not None and temp > max_temperature:
        return False
    return True
