from __future__ import annotations

from fastapi import APIRouter, Depends

from ..deps import get_redis
from ..metering.usage import Metering

router = APIRouter()


@router.get("/stats")
async def stats(redis=Depends(get_redis)):
    """Live gateway metrics: hit rate, cost saved vs spent, tokens."""
    return await Metering(redis).stats()
