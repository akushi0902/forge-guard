"""Request ID middleware — middleware stage #1 (outermost).

Assigns a UUID v4 correlation ID to every incoming HTTP request and
propagates it through the async context so it appears in every log entry
emitted during that request's lifecycle.

Correlation ID resolution order:
    1. If the incoming ``X-Request-ID`` header contains a valid UUID v4,
       that value is used as the correlation ID.  This supports distributed
       tracing across services that forward the same ID.
    2. If the header is absent, empty, or contains a non-UUID-v4 value,
       a fresh ``uuid.uuid4()`` is generated.

The resolved ID is stored on:
    - ``request.state.correlation_id``  — canonical attribute name (WO-015)
    - ``request.state.request_id``      — backward-compat alias used by the
                                          error handler and rate limiter

Contextvars isolation:
    Python's asyncio copies the current context for each new task, so each
    concurrent request automatically gets its own isolated context.  The
    explicit :func:`structlog.contextvars.clear_contextvars` call at the
    start of each dispatch ensures no stale values survive a connection
    keep-alive reuse on the same worker.
"""

from __future__ import annotations

import logging
import uuid

import structlog
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

_stdlib_logger = logging.getLogger(__name__)
logger = structlog.get_logger(__name__)

_UUID4_VARIANT_BITS = 0x8  # variant bits: 10xx


def _parse_uuid4(value: str) -> str | None:
    """Return *value* unchanged if it is a valid UUID v4; otherwise None."""
    try:
        parsed = uuid.UUID(value, version=4)
        # uuid.UUID(..., version=4) does NOT raise for other versions — it
        # silently resets the version bits.  Compare back to the original to
        # be certain the caller actually sent a v4.
        if str(parsed) == value.strip().lower():
            return value.strip().lower()
    except (ValueError, AttributeError):
        pass
    return None


class RequestIDMiddleware(BaseHTTPMiddleware):
    """Assign a UUID v4 correlation ID and propagate via request.state."""

    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        # Clear any stale structlog context from a previous request on this
        # same asyncio worker (keep-alive connection reuse).
        structlog.contextvars.clear_contextvars()

        # Resolve correlation ID: prefer a valid incoming UUID v4, otherwise
        # generate a fresh one.
        incoming = request.headers.get("x-request-id") or ""
        correlation_id: str = _parse_uuid4(incoming) or str(uuid.uuid4())

        # Bind to structlog context for automatic inclusion in all log entries.
        structlog.contextvars.bind_contextvars(request_id=correlation_id)

        try:
            # Both attribute names are set so existing consumers keep working:
            #   • request.state.correlation_id — canonical (WO-015, audit logs)
            #   • request.state.request_id     — compat alias (error handlers)
            request.state.correlation_id = correlation_id
            request.state.request_id = correlation_id
        except Exception:  # pragma: no cover
            _stdlib_logger.warning(
                "RequestIDMiddleware: failed to set request.state; continuing",
                exc_info=True,
            )

        response = await call_next(request)

        # Propagate the ID back to the caller for end-to-end tracing.
        response.headers["X-Request-ID"] = correlation_id

        return response
