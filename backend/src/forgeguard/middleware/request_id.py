"""Request ID middleware — middleware stage #1.

Assigns a UUID v4 correlation ID to every incoming HTTP request and
propagates it through the async context so it appears in every log entry
emitted during that request's lifecycle.

Security note:
    Any ``X-Request-ID`` header supplied by the caller is logged as
    ``upstream_request_id`` for tracing continuity but is NOT used as the
    server-assigned ID.  This prevents ID-spoofing attacks where an attacker
    injects a predictable request ID to manipulate log correlation.

Contextvars isolation:
    Python's asyncio copies the current context for each new task, so each
    concurrent request automatically gets its own isolated context.  The
    explicit :func:`structlog.contextvars.clear_contextvars` call at the
    start of each dispatch ensures no stale values survive a connection
    keep-alive reuse on the same worker.
"""

from __future__ import annotations

import uuid

import structlog
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

logger = structlog.get_logger(__name__)


class RequestIDMiddleware(BaseHTTPMiddleware):
    """Assign a UUID v4 request ID and bind it to the structlog context."""

    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        # Clear any stale context from a previous request on the same worker.
        structlog.contextvars.clear_contextvars()

        # Generate a new server-side request ID — never trust the client value.
        request_id = str(uuid.uuid4())

        # Expose upstream ID for log correlation without trusting it.
        upstream_id = request.headers.get("x-request-id")
        bind_kwargs: dict[str, str] = {"request_id": request_id}
        if upstream_id:
            bind_kwargs["upstream_request_id"] = upstream_id

        structlog.contextvars.bind_contextvars(**bind_kwargs)

        # Store request_id on request.state so downstream code can read it
        # without importing structlog (e.g. Pydantic validation error handlers).
        request.state.request_id = request_id

        response = await call_next(request)

        # Propagate the ID back to the caller for end-to-end tracing.
        response.headers["X-Request-ID"] = request_id

        return response
