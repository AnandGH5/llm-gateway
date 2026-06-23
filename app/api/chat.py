from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, StreamingResponse

from ..auth import require_api_key
from ..cache.embeddings import get_embedder
from ..cache.exact import ExactCache
from ..cache.keys import (
    is_cacheable,
    make_cache_key,
    make_params_hash,
    normalized_prompt_text,
)
from ..cache.semantic import SemanticCache
from ..config import settings
from ..db import get_db_pool
from ..deps import get_redis
from .. import metrics as M
from ..metering.cost import compute_cost
from ..metering.usage import Metering
from ..models import ChatCompletionRequest
from ..providers.base import ProviderBadRequest
from ..providers.router import AllProvidersFailed, get_router
from ..ratelimit.limiter import RateLimiter

router = APIRouter()


def _usage_tokens(response: dict) -> tuple[int, int]:
    usage = response.get("usage") or {}
    return int(usage.get("prompt_tokens", 0)), int(usage.get("completion_tokens", 0))


@router.post("/v1/chat/completions")
async def chat_completions(
    request: Request,
    api_key: str = Depends(require_api_key),
    redis=Depends(get_redis),
    pool=Depends(get_db_pool),
    embedder=Depends(get_embedder),
):
    request.state.redis = redis  # let the metrics middleware reuse this client

    # --- rate limit first (cheapest rejection; applies to streaming too) ---
    if settings.rate_limit_enabled:
        limiter = RateLimiter(redis, settings.rate_limit_capacity, settings.rate_limit_refill_per_sec)
        rl = await limiter.check(api_key)
        if not rl.allowed:
            M.record_rate_limited()
            return JSONResponse(
                status_code=429,
                content={"error": {"message": "Rate limit exceeded", "type": "rate_limit_error"}},
                headers={"Retry-After": str(rl.retry_after), "X-RateLimit-Remaining": str(rl.remaining)},
            )

    raw = await request.json()
    parsed = ChatCompletionRequest.model_validate(raw)
    payload = parsed.model_dump(exclude_none=True)

    provider_router = get_router()
    metering = Metering(redis)
    model = payload.get("model", "")

    # --- streaming: passthrough with start-of-stream failover, no caching ---
    if parsed.stream:
        await metering.record_passthrough()
        try:
            provider_name, stream_iter = await provider_router.stream(payload)
        except AllProvidersFailed as e:
            return JSONResponse(status_code=502, content={"error": {"message": str(e), "type": "provider_error"}})
        except ProviderBadRequest as e:
            return JSONResponse(status_code=400, content={"error": {"message": str(e), "type": "invalid_request_error"}})

        async def event_stream():
            async for chunk in stream_iter:
                yield chunk

        return StreamingResponse(
            event_stream(),
            media_type="text/event-stream",
            headers={"X-Cache": "MISS", "X-Provider": provider_name, "Cache-Control": "no-cache"},
        )

    cacheable = settings.cache_enabled and is_cacheable(payload, settings.cache_max_temperature)
    exact = ExactCache(redis, settings.cache_ttl_seconds)
    key = make_cache_key(payload) if cacheable else None

    semantic_on = cacheable and settings.semantic_cache_enabled
    params_hash = make_params_hash(payload)
    prompt_text = normalized_prompt_text(payload)
    semantic = (
        SemanticCache(pool, embedder, settings.similarity_threshold) if semantic_on else None
    )

    # --- tier 1: exact cache (O(1), no embedding) ---
    if cacheable:
        hit = await exact.get(key)
        if hit is not None:
            in_tok, out_tok = _usage_tokens(hit)
            saved = compute_cost(model, in_tok, out_tok)
            await metering.record_hit(total_tokens=in_tok + out_tok, saved_usd=saved, cache_type="exact")
            M.record_hit("exact", saved)
            return JSONResponse(
                hit,
                headers={"X-Cache": "HIT-EXACT", "X-Provider": "cache", "X-Cost-Saved-USD": f"{saved:.6f}"},
            )

    # --- tier 2: semantic cache ---
    if semantic_on:
        shit = await semantic.lookup(prompt_text=prompt_text, model=model, params_hash=params_hash)
        if shit is not None:
            in_tok, out_tok = _usage_tokens(shit.response)
            saved = compute_cost(model, in_tok, out_tok)
            await metering.record_hit(total_tokens=in_tok + out_tok, saved_usd=saved, cache_type="semantic")
            M.record_hit("semantic", saved)
            return JSONResponse(
                shit.response,
                headers={
                    "X-Cache": "HIT-SEMANTIC",
                    "X-Provider": "cache",
                    "X-Cache-Similarity": f"{shit.similarity:.4f}",
                    "X-Cost-Saved-USD": f"{saved:.6f}",
                },
            )

    # --- miss: route to a provider (with retry + failover), then write through ---
    try:
        result = await provider_router.complete(payload)
    except AllProvidersFailed as e:
        return JSONResponse(status_code=502, content={"error": {"message": str(e), "type": "provider_error"}})
    except ProviderBadRequest as e:
        return JSONResponse(status_code=400, content={"error": {"message": str(e), "type": "invalid_request_error"}})

    response = result.response
    if cacheable:
        await exact.set(key, response)
    if semantic_on:
        await semantic.store(prompt_text=prompt_text, model=model, params_hash=params_hash, response=response)

    if result.provider != settings.primary_provider:
        M.record_failover()

    in_tok, out_tok = _usage_tokens(response)
    cost = compute_cost(model, in_tok, out_tok)
    await metering.record_miss(total_tokens=in_tok + out_tok, cost_usd=cost)
    M.record_miss(cost)

    return JSONResponse(
        response,
        headers={"X-Cache": "MISS", "X-Provider": result.provider, "X-Cost-USD": f"{cost:.6f}"},
    )
