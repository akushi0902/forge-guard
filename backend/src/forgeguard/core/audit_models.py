"""Audit domain models and protocols for the ForgeGuard audit pipeline.

This module defines:

``AuditContext``
    A Pydantic model attached to ``request.state.audit_context`` by the
    :class:`~forgeguard.middleware.audit_prehook.AuditPreHookMiddleware`.
    Route handlers and the audit log writer read it to build immutable,
    complete before/after audit records.

``BeforeStateRepository``
    A :pep:`544` structural protocol that domain modules implement to
    supply the before-state of a resource being mutated.  The middleware
    receives a factory callable that produces an instance of this protocol
    per request, enabling clean dependency injection without coupling the
    middleware to a concrete repository.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel, Field


class AuditContext(BaseModel):
    """Immutable snapshot of audit metadata captured before a mutation runs.

    Attached to ``request.state.audit_context`` by
    :class:`~forgeguard.middleware.audit_prehook.AuditPreHookMiddleware`.
    All string fields are non-nullable once set; optional fields default to
    ``None`` for create operations (POST) and failed lookups.
    """

    correlation_id: str
    client_ip_masked: str
    http_method: str
    request_path: str
    resource_type: Optional[str] = None
    resource_id: Optional[str] = None
    before_state: Optional[dict] = None
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    model_config = {"frozen": True}


from typing import Protocol, runtime_checkable  # noqa: E402


@runtime_checkable
class BeforeStateRepository(Protocol):
    """Structural protocol for before-state lookups.

    Domain modules that need to supply pre-mutation resource state implement
    this protocol and register a factory with
    :class:`~forgeguard.middleware.audit_prehook.AuditPreHookMiddleware`.

    The factory signature is ``() -> BeforeStateRepository``.  A new instance
    may be created per request or a singleton returned; the choice is left to
    the concrete implementation.
    """

    async def get_before_state(
        self, resource_type: str, resource_id: str
    ) -> Optional[dict]:
        """Fetch the current state of a resource before it is mutated.

        Args:
            resource_type: The resource collection name extracted from the URL
                (e.g. ``'services'``, ``'policies'``).
            resource_id:   The resource identifier extracted from the URL.

        Returns:
            A JSON-serialisable dict representing the current resource state,
            or ``None`` if the resource does not exist or is not tracked.

        Raises:
            Any exception is caught by the middleware; the implementation
            should not swallow errors — let the middleware handle them.
        """
        ...
