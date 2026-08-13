"""RBAC enforcement middleware — pipeline position 6.

Defense-in-depth authorization layer that runs after authentication (position 5).
Enforces the route-permission mapping defined in
:mod:`~forgeguard.middleware.route_permissions` before the request reaches any
route handler.

Rationale:
    Even when every route handler uses ``require_permission`` dependencies, a
    developer who creates a new endpoint without adding the dependency would
    leave it accessible to any authenticated user.  This middleware provides
    deny-by-default coverage: unmapped routes are blocked at the middleware
    layer before the handler is ever invoked.

Pipeline placement:
    Position 6 — AFTER AuthenticationMiddleware (pos 5) so that
    ``request.state.user_role`` is already populated, BEFORE CSRFMiddleware
    (pos 7) so that CSRF validation only fires for authorized requests.

Bypass rules:
    - Public paths (same frozenset as :mod:`~forgeguard.middleware.authentication`)
    - OPTIONS preflight requests (CORS negotiation)

Error responses:
    - ``user_role`` not set on request.state  → 401 {"detail": "Authentication required"}
    - Permission denied (mapped route)         → 403 structured body matching WO-026 format
    - Unmapped protected route                 → 403 {"detail": "Access denied. ..."}
"""

from __future__ import annotations

from typing import Any

import structlog
from starlette.requests import Request
from starlette.responses import JSONResponse

from forgeguard.core.permissions import get_roles_with_permission
from forgeguard.middleware.authentication import PUBLIC_PATHS
from forgeguard.middleware.route_permissions import ROUTE_PERMISSION_MAP, RoutePermission

logger = structlog.get_logger(__name__)


def _forbidden_unmapped(method: str, path: str) -> JSONResponse:
    """403 for routes not present in the route-permission map."""
    return JSONResponse(
        status_code=403,
        content={"detail": "Access denied. This endpoint has not been configured for access."},
    )


def _forbidden_permission(
    user_role: str,
    primary_permission: str,
    path: str,
    method: str,
) -> JSONResponse:
    """403 matching the structured format from WO-026 PermissionDeniedError."""
    required_roles = get_roles_with_permission(primary_permission)
    human_roles = ", ".join(required_roles) if required_roles else "platform_admin"
    logger.info(
        "rbac.middleware.permission_denied",
        user_role=user_role,
        required_permission=primary_permission,
        required_roles=required_roles,
        method=method,
        path=path,
    )
    return JSONResponse(
        status_code=403,
        content={
            "detail": (
                f"This action requires the {primary_permission} permission assigned to the "
                f"{human_roles} role. Contact your Platform Admin for access."
            ),
            "required_permission": primary_permission,
            "required_roles": required_roles,
        },
    )


def _resolve_route(method: str, path: str) -> RoutePermission | None:
    """Return the first :class:`RoutePermission` that matches *method* and *path*.

    HEAD requests inherit GET permissions per HTTP semantics.
    """
    effective_method = "GET" if method == "HEAD" else method
    for entry in ROUTE_PERMISSION_MAP:
        if entry.matches(effective_method, path):
            return entry
    return None


class RBACMiddleware:
    """Pure ASGI RBAC enforcement middleware.

    Sits at pipeline position 6 — after AuthenticationMiddleware (sets
    ``request.state.user_role``), before CSRFMiddleware.

    Constructor args:
        app: The next ASGI application in the stack.
    """

    def __init__(self, app: Any) -> None:
        self._app = app

    async def __call__(
        self, scope: dict[str, Any], receive: Any, send: Any
    ) -> None:
        if scope["type"] not in ("http", "websocket"):
            await self._app(scope, receive, send)
            return

        request = Request(scope, receive)
        path: str = request.url.path
        method: str = request.method

        # Public endpoints and CORS preflight bypass RBAC enforcement.
        if path in PUBLIC_PATHS or method == "OPTIONS":
            await self._app(scope, receive, send)
            return

        # Auth middleware must have run first — check user_role is populated.
        user_role: str = getattr(request.state, "user_role", None) or ""
        if not user_role:
            response = JSONResponse(
                status_code=401,
                content={"detail": "Authentication required"},
                headers={"WWW-Authenticate": "Bearer"},
            )
            await response(scope, receive, send)
            return

        # Resolve the route permission entry.
        route_perm = _resolve_route(method, path)

        if route_perm is None:
            # Deny-by-default: warn developers about unmapped routes.
            logger.warning(
                "rbac.middleware.unmapped_route",
                method=method,
                path=path,
                user_role=user_role,
            )
            response = _forbidden_unmapped(method, path)
            await response(scope, receive, send)
            return

        # Check the required permission(s).
        if not route_perm.has_permission(user_role):
            primary = route_perm.permissions[0]
            response = _forbidden_permission(user_role, primary, path, method)
            await response(scope, receive, send)
            return

        await self._app(scope, receive, send)
