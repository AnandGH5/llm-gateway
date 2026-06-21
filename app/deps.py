from __future__ import annotations

from redis.asyncio import Redis, from_url

from .config import settings

# One shared client for the whole process. Redis-py manages an internal
# connection pool, so a single client is the right shape here.
_redis_client: Redis | None = None


def get_redis_client() -> Redis:
    global _redis_client
    if _redis_client is None:
        # Short timeouts so that if Redis is down we fail fast and degrade to a
        # cache miss, instead of hanging the request.
        _redis_client = from_url(
            settings.redis_url,
            decode_responses=True,
            socket_connect_timeout=2,
            socket_timeout=2,
        )
    return _redis_client


async def get_redis() -> Redis:
    """FastAPI dependency that hands the request the shared Redis client."""
    return get_redis_client()


async def close_redis() -> None:
    global _redis_client
    if _redis_client is not None:
        await _redis_client.aclose()
        _redis_client = None
