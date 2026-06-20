from __future__ import annotations

from fastapi import FastAPI

from .api.chat import router as chat_router
from .config import settings

app = FastAPI(title="LLM Gateway", version="0.1.0")
app.include_router(chat_router)


@app.get("/health")
async def health():
    return {"status": "ok", "primary_provider": settings.primary_provider}


@app.get("/")
async def root():
    return {
        "name": "LLM Gateway",
        "phase": 1,
        "endpoints": ["/v1/chat/completions", "/health"],
    }
