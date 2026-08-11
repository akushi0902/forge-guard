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

from forgeguard.core.config import Settings, get_settings

logger = structlog.get_logger(__name__)


def _configure_logging(settings: Settings) -> None:
    """Configure structlog for structured JSON logging."""
    log_level = getattr(logging, settings.log_level, logging.INFO)

    structlog.configure(
        wrapper_class=structlog.make_filtering_bound_logger(log_level),
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.dev.ConsoleRenderer()
            if settings.app_env == "development"
            else structlog.processors.JSONRenderer(),
        ],
        logger_factory=structlog.PrintLoggerFactory(),
    )

    # Also configure the stdlib root logger so third-party libraries participate.
    logging.basicConfig(level=log_level)


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

    _configure_logging(settings)

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
    # Health endpoints
    # Both are intentionally unauthenticated liveness/readiness probes.
    #
    # GET /                  — root stub, kept for backward-compat
    # GET /api/v1/health     — canonical health endpoint; Docker Compose
    #                          health checks and Nginx probes use this path
    # ------------------------------------------------------------------ #
    def _health_body() -> dict[str, str]:
        return {
            "status": "ok",
            "service": "forgeguard",
            "version": settings.app_version,
        }

    @app.get("/", tags=["health"], summary="Root liveness probe")
    async def root_health() -> JSONResponse:
        """Minimal liveness probe at the application root."""
        return JSONResponse(content=_health_body())

    @app.get("/api/v1/health", tags=["health"], summary="API health probe")
    async def api_health() -> JSONResponse:
        """Canonical health endpoint accessible through the Nginx reverse proxy.

        Docker Compose health checks use this path via the internal network:
            curl -f http://forgeguard-backend:8000/api/v1/health

        Through Nginx it is accessible at:
            https://localhost/api/v1/health
        """
        return JSONResponse(content=_health_body())

    logger.info(
        "ForgeGuard application factory complete",
        version=settings.app_version,
        env=settings.app_env,
        log_level=settings.log_level,
    )

    return app
