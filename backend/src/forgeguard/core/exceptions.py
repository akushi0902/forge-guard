"""Custom exception hierarchy for the ForgeGuard application.

All domain exceptions inherit from :class:`ForgeGuardError` so the global
exception handler can catch them in a single ``except`` clause and translate
them to structured HTTP responses without any case analysis in the routing layer.

Usage::

    from forgeguard.core.exceptions import NotFoundError, ForbiddenError

    raise NotFoundError(f"Service {service_id!r} was not found")

    raise ForbiddenError(
        "You cannot delete another team's service",
        required_permission="service:delete",
        contact_role="platform admin",
    )
"""

from __future__ import annotations


class ForgeGuardError(Exception):
    """Base exception for all ForgeGuard application-layer errors.

    Class-level attributes define the default HTTP status code and error
    type slug; subclasses override them.  Instance attributes carry the
    request-specific message and optional details dict.

    Args:
        message: Human-readable error description, safe to return to API consumers.
        details: Optional dict with structured context (must never contain secrets).
    """

    status_code: int = 500
    error_type: str = "internal_error"

    def __init__(
        self,
        message: str = "An unexpected error occurred",
        *,
        details: dict | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.details = details


class NotFoundError(ForgeGuardError):
    """HTTP 404 — the requested resource does not exist."""

    status_code = 404
    error_type = "not_found"

    def __init__(
        self,
        message: str = "Resource not found",
        *,
        details: dict | None = None,
    ) -> None:
        super().__init__(message, details=details)


class UnauthorizedError(ForgeGuardError):
    """HTTP 401 — authentication is required or the credentials are invalid/expired."""

    status_code = 401
    error_type = "unauthorized"

    def __init__(
        self,
        message: str = "Authentication required",
        *,
        details: dict | None = None,
    ) -> None:
        super().__init__(message, details=details)


class ForbiddenError(ForgeGuardError):
    """HTTP 403 — the authenticated user lacks the required permission.

    Carries actionable guidance: which permission is needed and who to contact.
    The error handler surfaces ``required_permission`` and a suggested
    ``action`` string in the JSON response body.

    Args:
        message: Human-readable reason for the denial.
        required_permission: The permission slug the caller is missing
            (e.g. ``"service:delete"``).
        contact_role: The role name to contact for the missing permission
            (e.g. ``"platform admin"``).
        details: Optional extra context dict.
    """

    status_code = 403
    error_type = "forbidden"

    def __init__(
        self,
        message: str = "You do not have permission to perform this action",
        *,
        required_permission: str = "",
        contact_role: str = "your administrator",
        details: dict | None = None,
    ) -> None:
        super().__init__(message, details=details)
        self.required_permission = required_permission
        self.contact_role = contact_role


class BadRequestError(ForgeGuardError):
    """HTTP 400 — the request is malformed or violates a business rule."""

    status_code = 400
    error_type = "bad_request"

    def __init__(
        self,
        message: str = "Bad request",
        *,
        details: dict | None = None,
    ) -> None:
        super().__init__(message, details=details)


class ConflictError(ForgeGuardError):
    """HTTP 409 — the request conflicts with the current state of the resource."""

    status_code = 409
    error_type = "conflict"

    def __init__(
        self,
        message: str = "Resource conflict",
        *,
        details: dict | None = None,
    ) -> None:
        super().__init__(message, details=details)


class RateLimitError(ForgeGuardError):
    """HTTP 429 — the client has exceeded its configured rate limit."""

    status_code = 429
    error_type = "rate_limit_exceeded"

    def __init__(
        self,
        message: str = "Rate limit exceeded. Please slow down.",
        *,
        details: dict | None = None,
    ) -> None:
        super().__init__(message, details=details)


class PermissionDeniedError(ForbiddenError):
    """HTTP 403 — raised by the RBAC module when a permission check fails.

    Extends :class:`ForbiddenError` with a ``required_roles`` list so the
    error handler can surface which roles carry the needed permission.

    Args:
        message:             Human-readable denial reason (safe for API consumers).
        required_permission: The permission slug the caller is missing.
        required_roles:      Roles that hold ``required_permission``.
        contact_role:        Who to contact for access.
        details:             Optional extra context dict.
    """

    def __init__(
        self,
        message: str = "You do not have permission to perform this action",
        *,
        required_permission: str = "",
        required_roles: list[str] | None = None,
        contact_role: str = "Platform Admin",
        details: dict | None = None,
    ) -> None:
        super().__init__(
            message,
            required_permission=required_permission,
            contact_role=contact_role,
            details=details,
        )
        self.required_roles: list[str] = required_roles or []
