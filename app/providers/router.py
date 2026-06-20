from __future__ import annotations

from ..config import settings
from .base import Provider
from .mock import MockProvider
from .openai import OpenAIProvider

_REGISTRY: dict[str, type[Provider]] = {
    "mock": MockProvider,
    "openai": OpenAIProvider,
}


def _build(name: str) -> Provider:
    key = (name or "").lower()
    if key not in _REGISTRY:
        raise ValueError(
            f"Unknown provider '{name}'. Available: {', '.join(_REGISTRY)}"
        )
    return _REGISTRY[key]()


def get_provider() -> Provider:
    """Phase 1: return the configured primary provider.

    Phase 4 will wrap this with retry/backoff and failover to
    ``settings.fallback_provider``.
    """
    return _build(settings.primary_provider)
