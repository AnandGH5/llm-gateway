from __future__ import annotations

import logging

from ..config import settings

log = logging.getLogger("cache.embeddings")


class LocalEmbedder:
    """Wraps a local sentence-transformers model (default all-MiniLM-L6-v2, 384-dim).

    Local embedding makes the cache lookup *free* and avoids a provider round-trip
    on every request — the cost-optimized choice. The model is loaded lazily on
    first use (it's heavy), and the import is deferred so the gateway can start
    even if the ML deps aren't installed (semantic cache simply stays off).
    """

    def __init__(self, model_name: str, dim: int) -> None:
        self.model_name = model_name
        self.dim = dim
        self._model = None

    def _ensure(self):
        if self._model is None:
            from sentence_transformers import SentenceTransformer  # heavy, lazy
            log.info("loading embedding model %s", self.model_name)
            self._model = SentenceTransformer(self.model_name)
        return self._model

    def embed(self, text: str) -> list[float]:
        # normalize_embeddings=True → unit vectors, so cosine similarity is clean.
        vec = self._ensure().encode(text, normalize_embeddings=True)
        return vec.tolist()


_embedder: LocalEmbedder | None = None


def get_embedder() -> LocalEmbedder:
    """FastAPI dependency returning the shared embedder (overridable in tests)."""
    global _embedder
    if _embedder is None:
        _embedder = LocalEmbedder(settings.embedding_model, settings.embedding_dim)
    return _embedder
