"""ForgeGuard application factory.

Usage (development)::

    uvicorn forgeguard.main:create_app --factory --reload

Usage (production)::

    gunicorn forgeguard.main:create_app \
        --worker-class uvicorn.workers.UvicornWorker \
        --workers 4

The :func:`create_app` factory pattern ensures the application is fully
configured before any request arrives, and makes it straightforward to create
isolated instances in tests.
"""

from __future__ import annotations

import logging

import structlog
from fastapi import FastAPI
from fastapi.responses import JSONResponse

from forgeguard.api.routes.system import router as system_router
from forgeguard.core.config import Settings, get_settings
from forgeguard.core.logging import configure_logging
from forgeguard.middleware.logging import RequestLoggingMiddleware
from forgeguard.middleware.metrics import MetricsMiddleware
from forgeguard.middleware.rate_limiter import RateLimiterMiddleware
from forgeguard.middleware.request_id import RequestIDMiddleware

logger = structlog.get_logger(__name__)


def create_app() -> FastAPI:
    """Create and configure the ForgeGuard FastAPI application.

    Returns a fully configured :class:`fastapi.FastAPI` instance.  All
    middleware, exception handlers, and routers are registered before the
    instance is returned so it is immediately usable.

    Raises:
        pydantic.ValidationError: If required environment variables are absent
            or have incompatible types.  The error message identifies the
            offending variable and its expected type.
    """
    try:
        settings = get_settings()
    except Exception:
        logging.exception(
            "ForgeGuard failed to load configuration. "
            "Check that all required environment variables are set."
        )
        raise

    configure_logging(log_level=settings.log_level, app_env=settings.app_env)

    app = FastAPI(
        title="ForgeGuard",
        description=(
            "AI-powered Engineering Governance and Release Readiness platform. "
            "Evaluates application compliance against engineering policies and "
            "analyses proposed code changes for release risk."
        ),
        version=settings.app_version,
        docs_url="/api/v1/docs",
        redoc_url="/api/v1/redoc",
        openapi_url="/api/v1/openapi.json",
    )

    # ------------------------------------------------------------------ #
    # Middleware pipeline
    #
    # FastAPI/Starlette builds the stack in reverse-registration order:
    # the LAST add_middleware call becomes the OUTERMOST layer (runs first).
    #
    # Desired order (outermost → innermost):
    #   1. RequestIDMiddleware      — assigns UUID, clears stale context
    #   2. RequestLoggingMiddleware — binds actor/resource/operation, logs lifecycle
    #   3. RateLimiterMiddleware    — token bucket per-IP rate limiting
    #   4. MetricsMiddleware        — records Prometheus counters & histograms
    #   5. Route handler
    #
    # Therefore we register them innermost-first.
    # ------------------------------------------------------------------ #
    app.add_middleware(MetricsMiddleware)           # registered first  → innermost (pos 4)
    app.add_middleware(RateLimiterMiddleware)       # registered second → pos 3
    app.add_middleware(RequestLoggingMiddleware)    # registered third  → pos 2
    app.add_middleware(RequestIDMiddleware)         # registered fourth → outermost (pos 1)

    # ------------------------------------------------------------------ #
    # Routers
    # ------------------------------------------------------------------ #

    # System observability endpoints: /health, /ready, /metrics
    # Mounted at root (no prefix) for direct container access.
    app.include_router(system_router)

    # Also accessible at /api/v1/* for Nginx reverse-proxy path (/api/ → backend).
    app.include_router(system_router, prefix="/api/v1", include_in_schema=False)

    # Root stub retained for backward compatibility.
    @app.get("/", tags=["system"], summary="Root liveness probe")
    async def root_health() -> JSONResponse:
        return JSONResponse(
            content={
                "status": "ok",
                "service": "forgeguard",
                "version": settings.app_version,
            }
        )

    logger.info(
        "ForgeGuard application factory complete",
        version=settings.app_version,
        env=settings.app_env,
        log_level=settings.log_level,
    )

    return app
