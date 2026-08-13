"""Audit writer middleware — post-hook DB persistence at pipeline position 8.

After the route handler completes successfully (2xx response), this middleware
reads the :class:`~forgeguard.core.audit_models.AuditContext` attached by
:class:`~forgeguard.middleware.audit_prehook.AuditPreHookMiddleware` (position 9)
and persists an immutable audit record via :class:`~forgeguard.services.audit.AuditService`.

Failure policy:
    Audit write failures are logged at ERROR level but the response is returned
    to the client unchanged.  Audit logging must never block the primary request.

Non-mutation methods (GET, OPTIONS, HEAD) are passed through immediately without
any audit record being written.

Wiring order (register AFTER AuditPreHookMiddleware so it sits outside it):
    app.add_middleware(AuditPreHookMiddleware)  # innermost — sets audit_context
    app.add_middleware(AuditWriterMiddleware)   # pos 8 — reads audit_context, writes record
"""

from __future__ import annotations

import asyncio
from typing import Any, Awaitable, Callable, Optional

import structlog
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

logger = structlog.get_logger(__name__)

# HTTP methods that produce audit records.
_MUTATION_METHODS: frozenset[str] = frozenset({"POST", "PUT", "PATCH", "DELETE"})

# Async service factory type alias (zero-arg coroutine that returns AuditService).
AuditServiceFactory = Callable[[], Awaitable[Any]]


def _derive_action(method: str, resource_type: Optional[str]) -> str:
    """Build a past-tense action slug from the HTTP method and resource type.

    Examples::

        _derive_action("POST", "services")   → "service.created"
        _derive_action("PUT", "policies")    → "policy.updated"
        _derive_action("DELETE", "findings") → "finding.deleted"
    """
    rtype = resource_type.rstrip("s") if resource_type else "resource"
    verbs = {
        "POST": "created",
        "PUT": "updated",
        "PATCH": "updated",
        "DELETE": "deleted",
    }
    return f"{rtype}.{verbs.get(method, method.lower())}"


class AuditWriterMiddleware(BaseHTTPMiddleware):
    """Write an immutable audit record after every successful data mutation.

    Constructor args:
        audit_service_factory: An async zero-argument callable that returns an
            :class:`~forgeguard.services.audit.AuditService` instance. When
            ``None``, the middleware is a transparent pass-through (useful in
            unit tests that do not need real DB writes).
    """

    def __init__(
        self,
        app,
        audit_service_factory: Optional[AuditServiceFactory] = None,
    ) -> None:
        super().__init__(app)
        self._factory = audit_service_factory

    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        response = await call_next(request)

        # Only write audit records for mutations.
        if request.method not in _MUTATION_METHODS:
            return response

        # Only write on successful responses (2xx).
        if not (200 <= response.status_code < 300):
            return response

        # Skip if no factory was provided (test or development mode).
        if self._factory is None:
            return response

        audit_context = getattr(request.state, "audit_context", None)
        if audit_context is None:
            return response

        actor_id = getattr(request.state, "actor_id", None)
        actor_role = getattr(request.state, "user_role", None) or "system"

        try:
            service = await self._factory()
            action = _derive_action(request.method, audit_context.resource_type)
            await asyncio.shield(
                service.log_mutation(
                    actor_id=actor_id,
                    actor_role=actor_role,
                    action=action,
                    resource_type=audit_context.resource_type or "",
                    resource_id=audit_context.resource_id,
                    before_state=audit_context.before_state,
                    after_state=None,
                    ip_address=audit_context.client_ip_masked,
                    correlation_id=audit_context.correlation_id,
                )
            )
        except Exception as exc:
            logger.error(
                "audit_writer.write_failed",
                method=request.method,
                path=request.url.path,
                correlation_id=getattr(audit_context, "correlation_id", None),
                error=str(exc),
                error_type=type(exc).__name__,
            )

        return response
