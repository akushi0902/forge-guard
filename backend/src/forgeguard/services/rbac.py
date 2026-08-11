"""RBACService: authoritative permission checking for ForgeGuard.

All authorization decisions flow through this service.  Route handlers should
never call :func:`~forgeguard.core.permissions.has_permission` directly — they
use the FastAPI dependencies in ``api/dependencies/rbac.py``, which delegate
to this service.
"""

from __future__ import annotations

import structlog

from forgeguard.core.exceptions import PermissionDeniedError
from forgeguard.core.permissions import (
    Permissions,
    UserRole,
    get_roles_with_permission,
    has_permission,
)

logger = structlog.get_logger(__name__)

# Roles that can approve exception.approve for each dimension.
_EXCEPTION_APPROVE_BY_DIMENSION: dict[str, frozenset[str]] = {
    "security": frozenset({UserRole.security_reviewer.value, UserRole.platform_admin.value}),
    "policy": frozenset({UserRole.tech_lead.value, UserRole.platform_admin.value}),
}


class RBACService:
    """Stateless authorization service.

    All methods are synchronous and perform only in-memory lookups against the
    compiled permission matrix — no I/O.
    """

    def check_permission(self, user_role: str, permission: str) -> None:
        """Assert that *user_role* holds *permission*.

        Logs an INFO entry for every denial (security audit trail).

        Args:
            user_role:  Role string from the authenticated user's token.
            permission: The required permission slug.

        Raises:
            PermissionDeniedError: If the role does not hold the permission.
                The error carries ``required_permission`` and ``required_roles``
                for the 403 response body.
        """
        if has_permission(user_role, permission):
            return

        roles_with_perm = get_roles_with_permission(permission)
        _human_roles = ", ".join(roles_with_perm) if roles_with_perm else "platform_admin"

        logger.info(
            "rbac.permission_denied",
            user_role=user_role,
            required_permission=permission,
            required_roles=roles_with_perm,
        )

        raise PermissionDeniedError(
            f"This action requires the {permission} permission assigned to the "
            f"{_human_roles} role. Contact your Platform Admin for access.",
            required_permission=permission,
            required_roles=roles_with_perm,
        )

    def check_conditional_permission(
        self,
        user_role: str,
        permission: str,
        context: dict,
    ) -> None:
        """Assert permission with context-dependent routing.

        Currently handles the ``exception.approve`` permission which is routed
        to different roles depending on the finding dimension:

        - ``dimension=security`` → :attr:`~UserRole.security_reviewer` or
          :attr:`~UserRole.platform_admin`
        - ``dimension=policy``   → :attr:`~UserRole.tech_lead` or
          :attr:`~UserRole.platform_admin`
        - missing / unknown dimension → denied

        For all other permissions this delegates to :meth:`check_permission`.

        Args:
            user_role:  Role string from the authenticated user's token.
            permission: The required permission slug.
            context:    Dict carrying contextual data; for ``exception.approve``
                        must contain ``"dimension": "security" | "policy"``.

        Raises:
            PermissionDeniedError: If the role is not authorised given the context.
        """
        if permission != Permissions.EXCEPTION_APPROVE:
            self.check_permission(user_role, permission)
            return

        dimension = context.get("dimension", "")
        allowed_roles = _EXCEPTION_APPROVE_BY_DIMENSION.get(dimension)

        if not allowed_roles or user_role not in allowed_roles:
            logger.info(
                "rbac.conditional_permission_denied",
                user_role=user_role,
                required_permission=permission,
                dimension=dimension,
            )
            # Surface the generic required-roles list for the error body.
            all_allowed: list[str] = sorted({
                r
                for roles in _EXCEPTION_APPROVE_BY_DIMENSION.values()
                for r in roles
            })
            raise PermissionDeniedError(
                f"This action requires the {permission} permission. "
                f"For '{dimension}' findings, contact your Platform Admin for access.",
                required_permission=permission,
                required_roles=all_allowed,
            )
