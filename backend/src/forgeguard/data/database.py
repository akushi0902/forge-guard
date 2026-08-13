"""Async connection pool management for ForgeGuard using asyncpg.

Pool lifecycle:
    init_pool()  — called once at application startup (FastAPI lifespan)
    close_pool() — called once at application shutdown (FastAPI lifespan)
    get_pool()   — returns the running pool for repository injection

Pool parameters come from Settings; changing environment variables after
startup has no effect until a restart.
"""

from __future__ import annotations

import asyncpg
import structlog

from forgeguard.core.config import get_settings

logger = structlog.get_logger(__name__)

_pool: asyncpg.Pool | None = None


def _to_asyncpg_dsn(url: str) -> str:
    """Strip the SQLAlchemy driver prefix so asyncpg can use the DSN directly."""
    if url.startswith("postgresql+asyncpg://"):
        return "postgresql://" + url[len("postgresql+asyncpg://"):]
    return url


async def init_pool() -> asyncpg.Pool:
    """Create the asyncpg connection pool and store it as a module singleton.

    Raises asyncpg.InvalidCatalogNameError / asyncpg.PostgresConnectionError
    when the database is unreachable — callers should let this propagate so
    the application fails fast at startup.
    """
    global _pool
    settings = get_settings()
    dsn = _to_asyncpg_dsn(settings.database_url)

    _pool = await asyncpg.create_pool(
        dsn=dsn,
        min_size=settings.db_pool_min_size,
        max_size=settings.db_pool_max_size,
        max_inactive_connection_lifetime=settings.db_pool_max_inactive_connection_lifetime,
        command_timeout=settings.db_command_timeout,
        statement_cache_size=settings.db_statement_cache_size,
    )
    logger.info(
        "asyncpg connection pool initialised",
        min_size=settings.db_pool_min_size,
        max_size=settings.db_pool_max_size,
        command_timeout=settings.db_command_timeout,
    )
    return _pool


async def close_pool() -> None:
    """Drain and close the connection pool gracefully."""
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None
        logger.info("asyncpg connection pool closed")


async def get_pool() -> asyncpg.Pool:
    """Return the running pool, initialising it on first call if needed.

    In production the pool is always pre-initialised by the FastAPI lifespan.
    This fallback exists for tests and CLI utilities that bypass lifespan.
    """
    global _pool
    if _pool is None:
        await init_pool()
    return _pool


async def health_check() -> bool:
    """Execute SELECT 1. Returns True when the database is reachable."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        result = await conn.fetchval("SELECT 1")
        return result == 1
