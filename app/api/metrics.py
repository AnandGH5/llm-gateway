from __future__ import annotations

from fastapi import APIRouter, Response

from ..metrics import render

router = APIRouter()


@router.get("/metrics")
async def metrics_endpoint():
    """Prometheus exposition format."""
    data, content_type = render()
    return Response(content=data, media_type=content_type)
