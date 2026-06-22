from __future__ import annotations

import logging
from pathlib import Path

import asyncpg
from pgvector.asyncpg import register_vector

from .config import settings

log = logging.getLogger("db")

_pool: asyncpg.Pool | None = None
_INIT_SQL = Path(__file__).resolve().parent.parent / "db" / "init.sql"


async def _register(conn: asyncpg.Connection) -> None:
    # Teach asyncpg the pgvector type so we can pass/receive Python lists.
    await register_vector(conn)


async def init_db() -> None:
    """Best-effort startup migration: create the extension + tables if missing.

    If Postgres is unreachable, we log and carry on — the semantic cache just
    stays off until the database is available. The gateway must still start.
    """
    try:
        sql = _INIT_SQL.read_text()
    except OSError as e:
        log.warning("init.sql not found, skipping migration: %s", e)
        return
    try:
        conn = await asyncpg.connect(settings.database_url, timeout=3)
    except Exception as e:
        log.warning("Postgres unavailable at startup (semantic cache off until it's up): %s", e)
        return
    try:
        await conn.execute(sql)  # multi-statement DDL via the simple-query protocol
        log.info("Postgres schema ready")
    except Exception as e:
        log.warning("schema migration failed: %s", e)
    finally:
        await conn.close()


async def _get_pool() -> asyncpg.Pool:
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(
            settings.database_url, min_size=1, max_size=5, timeout=3, init=_register
        )
    return _pool


async def get_db_pool():
    """FastAPI dependency. Returns the pool, or None if Postgres is unavailable,
    so callers degrade to 'no semantic cache' rather than failing the request."""
    try:
        return await _get_pool()
    except Exception as e:
        log.warning("Postgres pool unavailable (semantic cache off): %s", e)
        return None


async def close_db() -> None:
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None
