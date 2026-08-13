"""FastAPI dependency factories for RBAC permission enforcement.

Usage in route handlers::

    from forgeguard.core.permissions import Permissions
    from forgeguard.api.dependencies.rbac import require_permission

    @router.post("/services", dependencies=[Depends(require_permission(Permissions.SERVICE_VIEW))])
    async def create_service(...): ...

    # Or as a typed dependency:
    async def create_service(
        _perm: Annotated[None, Depends(require_permission(Permissions.SERVICE_VIEW))],
    ): ...
"""

from __future__ import annotations

from typing import Callable

import structlog
from fastapi import Request

from forgeguard.core.exceptions import PermissionDeniedError
from forgeguard.core.permissions import get_roles_with_permission
from forgeguard.services.rbac import RBACService

logger = structlog.get_logger(__name__)

_rbac = RBACService()


def _get_user_role(request: Request) -> str:
    """Extract the authenticated user's role from request state.

    Reads ``request.state.user_role`` set by the JWT/auth middleware.
    Falls back to an empty string (which will be denied by :func:`has_permission`)
    rather than raising, so the 403 path is always taken consistently.
    """
    return getattr(request.state, "user_role", "") or ""


def require_permission(permission: str) -> Callable:
    """Return a FastAPI dependency callable that enforces *permission*.

    The returned callable reads ``request.state.user_role`` and calls
    :meth:`~forgeguard.services.rbac.RBACService.check_permission`.

    Args:
        permission: A permission slug from :class:`~forgeguard.core.permissions.Permissions`.

    Returns:
        An async callable suitable for use with ``Depends()``.

    Raises:
        PermissionDeniedError (→ HTTP 403): If the role lacks *permission*.
    """
    async def _dependency(request: Request) -> None:
        user_role = _get_user_role(request)
        _rbac.check_permission(user_role, permission)

    return _dependency


def require_any_permission(permissions: list[str]) -> Callable:
    """Return a FastAPI dependency that passes if the user holds ANY of *permissions*.

    Useful for endpoints accessible by multiple distinct permission sets
    (e.g. read endpoints visible to all authenticated users).

    An empty *permissions* list always denies access (fail-closed).

    Args:
        permissions: List of permission slugs from :class:`~forgeguard.core.permissions.Permissions`.

    Returns:
        An async callable suitable for use with ``Depends()``.

    Raises:
        PermissionDeniedError (→ HTTP 403): If the role holds none of the permissions.
    """
    async def _dependency(request: Request) -> None:
        if not permissions:
            all_roles: list[str] = []
            raise PermissionDeniedError(
                "This action requires at least one valid permission. "
                "Contact your Platform Admin for access.",
                required_permission="",
                required_roles=all_roles,
            )

        user_role = _get_user_role(request)
        from forgeguard.core.permissions import has_permission  # noqa: PLC0415

        for perm in permissions:
            if has_permission(user_role, perm):
                return

        # None matched — raise with first permission as the primary.
        primary = permissions[0]
        roles_with_any: list[str] = sorted({
            r
            for p in permissions
            for r in get_roles_with_permission(p)
        })

        raise PermissionDeniedError(
            f"This action requires one of the following permissions: "
            f"{', '.join(permissions)}. Contact your Platform Admin for access.",
            required_permission=primary,
            required_roles=roles_with_any,
        )

    return _dependency
