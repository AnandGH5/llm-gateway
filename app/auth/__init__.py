from __future__ import annotations

from fastapi import Header, HTTPException, status

from ..config import settings


async def require_api_key(authorization: str | None = Header(default=None)) -> str:
    """Validate the gateway key from the Authorization header.

    Phase 1: check against a configured allow-list. Later phases resolve the
    key to a tenant for per-key rate limiting and cost metering.
    """
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or malformed Authorization header. Use 'Bearer <key>'.",
        )
    key = authorization.split(" ", 1)[1].strip()
    if key not in settings.allowed_keys:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key.",
        )
    return key
