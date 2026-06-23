from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from .api.chat import router as chat_router
from .api.metrics import router as metrics_router
from .api.stats import router as stats_router
from .config import settings
from .db import close_db, init_db
from .deps import close_redis
from .middleware import MetricsMiddleware


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: ensure the pgvector schema exists (best-effort).
    await init_db()
    yield
    # Shutdown: release connection pools cleanly.
    await close_redis()
    await close_db()


app = FastAPI(title="LLM Gateway", version="0.5.0", lifespan=lifespan)
app.add_middleware(MetricsMiddleware)

app.include_router(chat_router)
app.include_router(stats_router)
app.include_router(metrics_router)

# Serve the live dashboard at /dashboard/ if present.
_DASH = Path(__file__).resolve().parent.parent / "dashboard"
if _DASH.is_dir():
    app.mount("/dashboard", StaticFiles(directory=str(_DASH), html=True), name="dashboard")


@app.get("/health")
async def health():
    return {"status": "ok", "primary_provider": settings.primary_provider}


@app.get("/")
async def root():
    return {
        "name": "LLM Gateway",
        "phase": 5,
        "endpoints": ["/v1/chat/completions", "/stats", "/metrics", "/dashboard", "/health"],
    }
