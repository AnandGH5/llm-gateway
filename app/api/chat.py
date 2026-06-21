from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, StreamingResponse

from ..auth import require_api_key
from ..cache.exact import ExactCache
from ..cache.keys import is_cacheable, make_cache_key
from ..config import settings
from ..deps import get_redis
from ..metering.cost import compute_cost
from ..metering.usage import Metering
from ..models import ChatCompletionRequest
from ..providers.router import get_provider

router = APIRouter()


def _usage_tokens(response: dict) -> tuple[int, int]:
    usage = response.get("usage") or {}
    return int(usage.get("prompt_tokens", 0)), int(usage.get("completion_tokens", 0))


@router.post("/v1/chat/completions")
async def chat_completions(
    request: Request,
    api_key: str = Depends(require_api_key),
    redis=Depends(get_redis),
):
    raw = await request.json()
    parsed = ChatCompletionRequest.model_validate(raw)
    payload = parsed.model_dump(exclude_none=True)

    provider = get_provider()
    metering = Metering(redis)
    model = payload.get("model", "")

    # --- streaming: pure passthrough in v1 (we don't cache token streams) ---
    if parsed.stream:
        await metering.record_passthrough()

        async def event_stream():
            async for chunk in provider.stream_chat_completion(payload):
                yield chunk

        return StreamingResponse(
            event_stream(),
            media_type="text/event-stream",
            headers={
                "X-Cache": "MISS",
                "X-Provider": provider.name,
                "Cache-Control": "no-cache",
            },
        )

    cacheable = settings.cache_enabled and is_cacheable(payload, settings.cache_max_temperature)
    cache = ExactCache(redis, settings.cache_ttl_seconds)
    key = make_cache_key(payload) if cacheable else None

    # --- cache lookup (the fast, $0 path) ---
    if cacheable:
        hit = await cache.get(key)
        if hit is not None:
            in_tok, out_tok = _usage_tokens(hit)
            saved = compute_cost(model, in_tok, out_tok)
            await metering.record_hit(
                total_tokens=in_tok + out_tok, saved_usd=saved, cache_type="exact"
            )
            return JSONResponse(
                content=hit,
                headers={
                    "X-Cache": "HIT-EXACT",
                    "X-Provider": provider.name,
                    "X-Cost-Saved-USD": f"{saved:.6f}",
                },
            )

    # --- miss: forward to the provider, then write through to the cache ---
    result = await provider.chat_completion(payload)
    if cacheable:
        await cache.set(key, result)

    in_tok, out_tok = _usage_tokens(result)
    cost = compute_cost(model, in_tok, out_tok)
    await metering.record_miss(total_tokens=in_tok + out_tok, cost_usd=cost)

    return JSONResponse(
        content=result,
        headers={
            "X-Cache": "MISS",
            "X-Provider": provider.name,
            "X-Cost-USD": f"{cost:.6f}",
        },
    )
