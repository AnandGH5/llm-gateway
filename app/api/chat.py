from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, StreamingResponse

from ..auth import require_api_key
from ..models import ChatCompletionRequest
from ..providers.router import get_provider

router = APIRouter()


@router.post("/v1/chat/completions")
async def chat_completions(
    request: Request,
    api_key: str = Depends(require_api_key),
):
    raw = await request.json()
    # Validate against the OpenAI schema; unknown fields are preserved.
    parsed = ChatCompletionRequest.model_validate(raw)
    payload = parsed.model_dump(exclude_none=True)

    provider = get_provider()

    # X-Cache is always MISS in Phase 1 (no cache yet); the header is here so
    # clients and demos can rely on it from day one. Phase 2 fills in real hits.
    if parsed.stream:

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

    result = await provider.chat_completion(payload)
    return JSONResponse(
        content=result,
        headers={"X-Cache": "MISS", "X-Provider": provider.name},
    )
