from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from .api.chat import router as chat_router
from .api.stats import router as stats_router
from .config import settings
from .db import close_db, init_db
from .deps import close_redis


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: ensure the pgvector schema exists (best-effort — if Postgres is
    # down the gateway still starts, just without the semantic cache).
    await init_db()
    yield
    # Shutdown: release connection pools cleanly.
    await close_redis()
    await close_db()


app = FastAPI(title="LLM Gateway", version="0.3.0", lifespan=lifespan)
app.include_router(chat_router)
app.include_router(stats_router)


@app.get("/health")
async def health():
    return {"status": "ok", "primary_provider": settings.primary_provider}


@app.get("/")
async def root():
    return {
        "name": "LLM Gateway",
        "phase": 3,
        "endpoints": ["/v1/chat/completions", "/stats", "/health"],
    }
