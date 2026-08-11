"""Audit pre-hook middleware — mutation capture at position 9 (innermost).

Intercepts POST, PUT, PATCH, and DELETE requests to capture the before-state
of the resource being mutated and attach an :class:`AuditContext` to
``request.state.audit_context`` before the route handler executes.

GET and OPTIONS requests bypass this middleware entirely (no-op pass-through).

Failure policy:
    Before-state capture is best-effort.  Any failure — database unavailable,
    query timeout, unexpected exception — is logged as a structured warning and
    the request proceeds with ``before_state=None`` in the context.  This
    ensures the middleware can **never** block a request.

Thread / concurrency safety:
    Before-state lookup is wrapped in :func:`asyncio.wait_for` with a 500 ms
    timeout so a slow database cannot impact request latency.

Wiring:
    Register this middleware *before* all others in ``create_app()`` so that
    it becomes the innermost layer (runs last, just before the route handler).
    The ``RequestIDMiddleware`` (outermost) must be registered after this one
    so that ``request.state.correlation_id`` is already set when this
    middleware runs.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Callable, Optional

import structlog
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from forgeguard.core.audit_models import AuditContext, BeforeStateRepository
from forgeguard.core.ip_masking import mask_ip_address

logger = structlog.get_logger(__name__)
_stdlib_logger = logging.getLogger(__name__)

# HTTP methods that require before-state capture.
_MUTATION_METHODS: frozenset[str] = frozenset({"POST", "PUT", "PATCH", "DELETE"})

# Timeout for the before-state repository lookup (seconds).
_BEFORE_STATE_TIMEOUT: float = 0.5

# Common API path prefix used for resource type / ID extraction.
_API_V1_PREFIX: str = "/api/v1/"


# ---------------------------------------------------------------------------
# No-op repository (default when no factory is provided)
# ---------------------------------------------------------------------------

class _NoopBeforeStateRepository:
    async def get_before_state(
        self, resource_type: str, resource_id: str
    ) -> None:
        return None


def _noop_factory() -> _NoopBeforeStateRepository:
    return _NoopBeforeStateRepository()


# ---------------------------------------------------------------------------
# URL path parser
# ---------------------------------------------------------------------------

def _parse_url_path(path: str) -> tuple[Optional[str], Optional[str]]:
    """Extract ``(resource_type, resource_id)`` from a URL path.

    Splits on ``/api/v1/`` (or ``/api/`` as fallback) and returns the first
    two non-empty path segments.  Returns ``(None, None)`` for paths that
    cannot be parsed.

    Examples::

        _parse_url_path("/api/v1/services/abc-123")
        # → ("services", "abc-123")

        _parse_url_path("/api/v1/services")
        # → ("services", None)

        _parse_url_path("/health")
        # → ("health", None)
    """
    suffix: str

    if _API_V1_PREFIX in path:
        idx = path.index(_API_V1_PREFIX)
        suffix = path[idx + len(_API_V1_PREFIX):]
    elif "/api/" in path:
        idx = path.index("/api/")
        suffix = path[idx + len("/api/"):]
    else:
        suffix = path.lstrip("/")

    parts = [p for p in suffix.split("/") if p]
    if not parts:
        return None, None

    resource_type: Optional[str] = parts[0] if parts else None
    resource_id: Optional[str] = parts[1] if len(parts) > 1 else None
    return resource_type, resource_id


# ---------------------------------------------------------------------------
# IP extraction helper
# ---------------------------------------------------------------------------

def _extract_client_ip(request: Request) -> str:
    """Extract the original client IP from the request.

    Prefers the leftmost value in ``X-Forwarded-For`` (RFC 7239 original
    client), then falls back to the ASGI scope ``client`` tuple.
    """
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        # Multiple IPs in X-Forwarded-For: client, proxy1, proxy2, ...
        return forwarded.split(",")[0].strip()

    client = request.scope.get("client")
    if client and client[0]:
        return client[0]

    return ""


# ---------------------------------------------------------------------------
# Middleware
# ---------------------------------------------------------------------------

class AuditPreHookMiddleware(BaseHTTPMiddleware):
    """Capture mutation before-state and attach an AuditContext to request.state.

    Constructor args:
        before_state_repo_factory: A zero-argument callable returning a
            :class:`~forgeguard.core.audit_models.BeforeStateRepository`
            instance.  If omitted, a no-op repository is used (suitable for
            development / routes where before-state is not required).
    """

    def __init__(
        self,
        app,
        before_state_repo_factory: Optional[Callable[[], BeforeStateRepository]] = None,
    ) -> None:
        super().__init__(app)
        self._repo_factory: Callable[[], BeforeStateRepository] = (
            before_state_repo_factory if before_state_repo_factory is not None
            else _noop_factory
        )

    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        # GET and OPTIONS bypass the pre-hook entirely.
        if request.method not in _MUTATION_METHODS:
            return await call_next(request)

        # Resolve correlation ID from upstream RequestIDMiddleware (or generate
        # a fallback so audit_context is always consistent).
        correlation_id: str = (
            getattr(request.state, "correlation_id", None)
            or str(uuid.uuid4())
        )

        # Mask client IP before storing it in the audit context.
        raw_ip = _extract_client_ip(request)
        masked_ip = mask_ip_address(raw_ip)

        # Extract resource type and ID from the URL path.
        resource_type, resource_id = _parse_url_path(request.url.path)

        # Fetch before-state:
        #   - POST always has before_state=None (resource does not exist yet).
        #   - Other mutations attempt a timed DB lookup; failures are non-fatal.
        before_state: Optional[dict] = None
        if request.method != "POST" and resource_id is not None:
            try:
                repo = self._repo_factory()
                before_state = await asyncio.wait_for(
                    repo.get_before_state(resource_type or "", resource_id),
                    timeout=_BEFORE_STATE_TIMEOUT,
                )
            except Exception as exc:
                logger.warning(
                    "audit_prehook.before_state_lookup_failed",
                    correlation_id=correlation_id,
                    resource_type=resource_type,
                    resource_id=resource_id,
                    error=str(exc),
                    error_type=type(exc).__name__,
                )
                before_state = None

        audit_context = AuditContext(
            correlation_id=correlation_id,
            client_ip_masked=masked_ip,
            http_method=request.method,
            request_path=request.url.path,
            resource_type=resource_type,
            resource_id=resource_id,
            before_state=before_state,
        )

        try:
            request.state.audit_context = audit_context
        except Exception:
            _stdlib_logger.warning(
                "AuditPreHookMiddleware: could not attach audit_context to "
                "request.state — continuing without it",
                exc_info=True,
            )

        return await call_next(request)
