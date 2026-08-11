"""Structured request-logging middleware — middleware stage #2.

Binds per-request context fields to the structlog context so that every
log statement emitted by route handlers and service-layer code automatically
includes:

    actor      — authenticated user ID, or ``'anonymous'``
    resource   — URL path (e.g. ``/api/v1/assessments``)
    operation  — HTTP method (e.g. ``POST``)

Also emits two structured log events per request:

    request_started    — at INFO level, after context is bound
    request_completed  — at INFO level, with status_code and duration_ms

Both events include all context fields bound by this and the Request ID
middleware, so a single ``request_id`` search surfaces the full request
lifecycle in any log aggregation system.
"""

from __future__ import annotations

import time
from typing import Any

import structlog
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

logger = structlog.get_logger(__name__)

# Paths excluded from audit logging — health/metrics probes must not flood logs.
_DEFAULT_EXCLUDE_PATHS: frozenset[str] = frozenset({"/health", "/ready", "/metrics"})


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Bind request context to structlog and log request lifecycle events."""

    def __init__(self, app: Any, exclude_paths: frozenset[str] = _DEFAULT_EXCLUDE_PATHS) -> None:  # type: ignore[override]
        super().__init__(app)
        self.exclude_paths = exclude_paths

    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        if request.url.path in self.exclude_paths:
            return await call_next(request)

        # ---- Extract actor -----------------------------------------------
        # JWT auth middleware (a later stage) stores the decoded token claims
        # on request.state.user.  If that isn't set yet (unauthenticated or
        # called before auth middleware), default to 'anonymous'.
        actor: str = "anonymous"
        user_state = getattr(request.state, "user", None)
        if user_state is not None:
            actor = str(getattr(user_state, "id", "anonymous"))

        # ---- Bind request context to structlog ----------------------------
        structlog.contextvars.bind_contextvars(
            actor=actor,
            resource=request.url.path,
            operation=request.method,
        )

        start_ns = time.perf_counter_ns()
        logger.info("request_started")

        # ---- Process the request -----------------------------------------
        response = await call_next(request)

        # ---- Log completion -----------------------------------------------
        duration_ms = (time.perf_counter_ns() - start_ns) / 1_000_000
        logger.info(
            "request_completed",
            status_code=response.status_code,
            duration_ms=round(duration_ms, 2),
        )

        return response
