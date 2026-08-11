"""System observability endpoints: liveness, readiness, and Prometheus metrics."""

from __future__ import annotations

import asyncio
import datetime
import time
from typing import Any

import structlog
from fastapi import APIRouter
from fastapi.responses import Response
from fastapi.responses import JSONResponse
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from forgeguard.core.config import get_settings

router = APIRouter(tags=["system"])
logger = structlog.get_logger(__name__)


@router.get("/health", summary="Liveness probe")
async def health_check() -> JSONResponse:
    """Fast liveness probe — no external calls, must complete in <10ms.

    Used by Docker Compose health checks and container orchestration systems
    to determine whether the process is alive.
    """
    settings = get_settings()
    return JSONResponse(
        content={
            "status": "healthy",
            "timestamp": datetime.datetime.utcnow().isoformat(),
            "version": settings.app_version,
        }
    )


async def _run_select_one(engine: Any) -> None:
    """Execute SELECT 1 against the given engine to verify connectivity."""
    async with engine.connect() as conn:
        await conn.execute(text("SELECT 1"))


async def _check_database(database_url: str) -> dict[str, Any]:
    """Open a transient connection and run SELECT 1, reporting latency."""
    start = time.perf_counter()
    engine = create_async_engine(database_url, pool_pre_ping=False)
    try:
        await asyncio.wait_for(_run_select_one(engine), timeout=5.0)
        latency_ms = round((time.perf_counter() - start) * 1000, 2)
        return {"status": "up", "latency_ms": latency_ms}
    except asyncio.TimeoutError:
        return {
            "status": "down",
            "error": "TimeoutError: check timed out after 5 seconds",
        }
    except Exception as exc:
        return {"status": "down", "error": f"{type(exc).__name__}: {exc}"}
    finally:
        await engine.dispose()


async def _check_migrations(database_url: str) -> dict[str, Any]:
    """Query the alembic_version table to report migration status."""
    engine = create_async_engine(database_url, pool_pre_ping=False)
    try:
        async with engine.connect() as conn:
            result = await conn.execute(text("SELECT version_num FROM alembic_version"))
            row = result.fetchone()
        version = row[0] if row else None
        return {
            "status": "current" if version else "not_initialized",
            "version": version,
        }
    except Exception:
        return {"status": "not_initialized", "version": None}
    finally:
        await engine.dispose()


@router.get("/ready", summary="Readiness probe")
async def readiness_check() -> JSONResponse:
    """Readiness probe — checks live dependencies before admitting traffic.

    Returns 200 when all checks pass, 503 when any critical check fails.
    Each call performs a fresh check; results are never cached.
    """
    settings = get_settings()
    database_url = settings.database_url

    db_result = await _check_database(database_url)
    migration_result = await _check_migrations(database_url)

    all_healthy = db_result["status"] == "up"
    return JSONResponse(
        status_code=200 if all_healthy else 503,
        content={
            "status": "ready" if all_healthy else "not_ready",
            "checks": {
                "database": db_result,
                "migrations": migration_result,
            },
        },
    )


@router.get("/metrics", summary="Prometheus metrics")
async def metrics_endpoint() -> Response:
    """Expose Prometheus-format metrics for scraping."""
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)
