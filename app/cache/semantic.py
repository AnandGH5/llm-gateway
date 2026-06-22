from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass

log = logging.getLogger("cache.semantic")


@dataclass
class SemanticHit:
    response: dict
    similarity: float


def passes_threshold(similarity: float | None, threshold: float) -> bool:
    """The precision/recall dial: only count a neighbor as a hit if it's close enough."""
    return similarity is not None and similarity >= threshold


class SemanticCache:
    """Vector cache over pgvector.

    Lookup: embed the prompt, find the nearest stored prompt for the same model
    and params, and return it only if cosine similarity clears the threshold.
    Best-effort: if Postgres or the embedder is unavailable, every operation
    degrades to a miss / no-op so the gateway keeps serving from exact cache or
    the provider.
    """

    def __init__(self, pool, embedder, threshold: float) -> None:
        self._pool = pool
        self._embedder = embedder
        self._threshold = threshold

    async def _embed(self, text: str) -> list[float]:
        # Embedding is CPU-bound; run it off the event loop so it doesn't block
        # other concurrent requests.
        return await asyncio.to_thread(self._embedder.embed, text)

    async def lookup(self, *, prompt_text: str, model: str, params_hash: str) -> SemanticHit | None:
        if self._pool is None:
            return None
        try:
            vec = await self._embed(prompt_text)
        except Exception as e:
            log.warning("embedding failed (semantic skipped for this request): %s", e)
            return None
        try:
            async with self._pool.acquire() as conn:
                row = await conn.fetchrow(
                    "SELECT id, response, 1 - (embedding <=> $1) AS sim "
                    "FROM prompt_cache WHERE model = $2 AND params_hash = $3 "
                    "ORDER BY embedding <=> $1 LIMIT 1",
                    vec, model, params_hash,
                )
                if row is None:
                    return None
                sim = float(row["sim"])
                hit = passes_threshold(sim, self._threshold)
                # Logged on every lookup so you can see the similarity distribution
                # and tune the threshold empirically.
                log.info("semantic lookup model=%s best_sim=%.4f hit=%s", model, sim, hit)
                if hit:
                    await conn.execute(
                        "UPDATE prompt_cache SET hits = hits + 1, last_hit = now() WHERE id = $1",
                        row["id"],
                    )
                    return SemanticHit(response=json.loads(row["response"]), similarity=sim)
        except Exception as e:
            log.warning("semantic lookup failed (treating as miss): %s", e)
        return None

    async def store(self, *, prompt_text: str, model: str, params_hash: str, response: dict) -> None:
        if self._pool is None:
            return
        try:
            vec = await self._embed(prompt_text)
            async with self._pool.acquire() as conn:
                await conn.execute(
                    "INSERT INTO prompt_cache (model, prompt, params_hash, response, embedding) "
                    "VALUES ($1, $2, $3, $4::jsonb, $5)",
                    model, prompt_text, params_hash, json.dumps(response), vec,
                )
        except Exception as e:
            log.warning("semantic store failed (skipping write): %s", e)
