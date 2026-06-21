from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from .api.chat import router as chat_router
from .api.stats import router as stats_router
from .config import settings
from .deps import close_redis


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: nothing eager — the Redis client connects lazily on first use.
    yield
    # Shutdown: release the Redis connection pool cleanly.
    await close_redis()


app = FastAPI(title="LLM Gateway", version="0.2.0", lifespan=lifespan)
app.include_router(chat_router)
app.include_router(stats_router)


@app.get("/health")
async def health():
    return {"status": "ok", "primary_provider": settings.primary_provider}


@app.get("/")
async def root():
    return {
        "name": "LLM Gateway",
        "phase": 2,
        "endpoints": ["/v1/chat/completions", "/stats", "/health"],
    }
