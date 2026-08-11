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
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from forgeguard.api.routes.admin import router as admin_router
from forgeguard.api.routes.auth import router as auth_router
from forgeguard.api.routes.demo import router as demo_router
from forgeguard.api.routes.platform import router as platform_router
from forgeguard.api.routes.system import router as system_router
from forgeguard.core.config import Settings, get_settings
from forgeguard.core.error_handlers import register_error_handlers
from forgeguard.core.logging import configure_logging
from forgeguard.middleware.audit import AuditWriterMiddleware
from forgeguard.middleware.audit_prehook import AuditPreHookMiddleware
from forgeguard.middleware.logging import RequestLoggingMiddleware
from forgeguard.middleware.metrics import MetricsMiddleware
from forgeguard.middleware.rate_limiter import RateLimiterMiddleware
from forgeguard.middleware.request_id import RequestIDMiddleware
from forgeguard.middleware.security_headers import SecurityHeadersMiddleware

logger = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage asyncpg connection pool lifecycle.

    Initialises the pool on startup and drains it on shutdown so all in-flight
    queries can complete before the process exits.
    """
    from forgeguard.data.database import close_pool, init_pool  # noqa: PLC0415

    await init_pool()
    yield
    await close_pool()


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
        lifespan=lifespan,
    )

    # ------------------------------------------------------------------ #
    # Middleware pipeline
    #
    # FastAPI/Starlette builds the stack in reverse-registration order:
    # the LAST add_middleware call becomes the OUTERMOST layer (runs first).
    #
    # Desired order (outermost → innermost):
    #   1. RequestIDMiddleware       — assigns UUID, clears stale context
    #   2. RequestLoggingMiddleware  — binds actor/resource/operation, logs lifecycle
    #   3. RateLimiterMiddleware     — token bucket per-IP rate limiting
    #   4. CORSMiddleware            — CORS headers, pre-flight handling
    #   5. SecurityHeadersMiddleware — inject 7 security headers on all responses
    #   6. MetricsMiddleware         — records Prometheus counters & histograms
    #   9. AuditPreHookMiddleware    — captures before-state for mutation requests
    #  10. Route handler
    #
    # FastAPI/Starlette builds the stack in reverse-registration order:
    # the LAST add_middleware call becomes the OUTERMOST layer (runs first).
    # Therefore we register them innermost-first.
    # ------------------------------------------------------------------ #
    # ------------------------------------------------------------------ #
    # Exception handlers
    # ------------------------------------------------------------------ #
    register_error_handlers(app)

    # Build the audit service factory for the writer middleware.
    # Uses a lazy import so the pool is resolved at request time (after lifespan).
    async def _audit_service_factory():
        from forgeguard.data.database import get_pool as _get_pool  # noqa: PLC0415
        from forgeguard.data.repositories.audit_logs import AuditLogRepository  # noqa: PLC0415
        from forgeguard.services.audit import AuditService  # noqa: PLC0415

        pool = await _get_pool()
        return AuditService(AuditLogRepository(pool))

    app.add_middleware(AuditPreHookMiddleware)      # registered 1st → innermost (pos 9)
    app.add_middleware(                             # registered 2nd → pos 8
        AuditWriterMiddleware,
        audit_service_factory=_audit_service_factory,
    )
    app.add_middleware(MetricsMiddleware)           # registered 3rd → pos 6
    app.add_middleware(SecurityHeadersMiddleware)   # registered 3rd → pos 5
    app.add_middleware(                             # registered 4th → pos 4
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=True,
        allow_methods=settings.cors_allow_methods,
        allow_headers=settings.cors_allow_headers,
    )
    app.add_middleware(RateLimiterMiddleware)       # registered 5th → pos 3
    app.add_middleware(RequestLoggingMiddleware)    # registered 6th → pos 2
    app.add_middleware(RequestIDMiddleware)         # registered 7th → outermost (pos 1)

    # ------------------------------------------------------------------ #
    # Routers
    # ------------------------------------------------------------------ #

    # System observability endpoints: /health, /ready, /metrics
    # Mounted at root (no prefix) for direct container access.
    app.include_router(system_router)

    # Also accessible at /api/v1/* for Nginx reverse-proxy path (/api/ → backend).
    app.include_router(system_router, prefix="/api/v1", include_in_schema=False)

    # Auth endpoints: user registration (requires Platform Admin role).
    app.include_router(auth_router)

    # Admin endpoints: prompt template CRUD (requires Platform Admin role).
    app.include_router(admin_router)

    # Platform observability endpoints (Operator/Admin role required).
    app.include_router(platform_router)

    # Demo mock Payment Service endpoints.
    app.include_router(demo_router)

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
