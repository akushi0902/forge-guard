"""RBACService: authoritative permission checking for ForgeGuard.

All authorization decisions flow through this service.  Route handlers should
never call :func:`~forgeguard.core.permissions.has_permission` directly — they
use the FastAPI dependencies in ``api/dependencies/rbac.py``, which delegate
to this service.
"""

from __future__ import annotations

import base64
import uuid
from typing import TYPE_CHECKING, Any

import structlog

from forgeguard.core.exceptions import ConflictError, NotFoundError, PermissionDeniedError
from forgeguard.core.permissions import (
    ROLE_PERMISSIONS,
    Permissions,
    UserRole,
    get_permissions,
    get_roles_with_permission,
    has_permission,
)

if TYPE_CHECKING:
    from forgeguard.data.repositories.refresh_tokens import RefreshTokenRepository
    from forgeguard.data.repositories.users import UserRepository
    from forgeguard.services.audit import AuditService

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


# ---------------------------------------------------------------------------
# RBAC Administration Service (WO-028)
# ---------------------------------------------------------------------------

def _encode_cursor(created_at: Any, user_id: Any) -> str:
    """Encode (created_at, id) composite into an opaque base64 cursor."""
    ts = created_at.isoformat() if hasattr(created_at, "isoformat") else str(created_at)
    raw = f"{ts}|{user_id}"
    return base64.b64encode(raw.encode()).decode()


def _build_name(user_row: dict[str, Any]) -> str:
    """Decode name_encrypted (bytes) to string for API responses."""
    raw = user_row.get("name_encrypted") or user_row.get("name") or ""
    if isinstance(raw, (bytes, bytearray)):
        try:
            return raw.decode("utf-8")
        except Exception:
            return "[encrypted]"
    return str(raw) if raw else ""


class RBACAdminService:
    """Async admin operations for user-role management.

    Args:
        user_repo:    Injected :class:`~forgeguard.data.repositories.users.UserRepository`.
        token_repo:   Injected :class:`~forgeguard.data.repositories.refresh_tokens.RefreshTokenRepository`.
        audit_service: Injected :class:`~forgeguard.services.audit.AuditService`.
    """

    def __init__(
        self,
        user_repo: "UserRepository",
        token_repo: "RefreshTokenRepository",
        audit_service: "AuditService",
    ) -> None:
        self._users = user_repo
        self._tokens = token_repo
        self._audit = audit_service

    async def list_users(
        self,
        *,
        cursor: str | None = None,
        limit: int = 50,
    ) -> dict[str, Any]:
        """Return a paginated user list.

        Returns:
            Dict with ``users`` (list), ``next_cursor`` (str | None),
            and ``total_count`` (int).
        """
        limit = min(max(1, limit), 100)
        rows = await self._users.list_all(cursor=cursor, limit=limit + 1)
        has_more = len(rows) > limit
        page = rows[:limit]
        next_cursor: str | None = None
        if has_more:
            last = page[-1]
            next_cursor = _encode_cursor(last["created_at"], last["id"])
        total = await self._users.count_all()
        users = [
            {
                "id": r["id"],
                "email": r["email"],
                "name": _build_name(r),
                "role": r["role"],
                "is_active": r["is_active"],
                "created_at": r["created_at"],
            }
            for r in page
        ]
        return {"users": users, "next_cursor": next_cursor, "total_count": total}

    async def get_user_detail(self, user_id: str | uuid.UUID) -> dict[str, Any]:
        """Return a single user's profile with resolved permissions.

        Raises:
            NotFoundError: If the user does not exist.
        """
        row = await self._users.get_by_id(user_id)
        if row is None:
            raise NotFoundError(f"User {user_id!r} not found.")
        role_str: str = row.get("role", "")
        resolved_perms = sorted(get_permissions(role_str))
        return {
            "id": row["id"],
            "email": row["email"],
            "name": _build_name(row),
            "role": role_str,
            "is_active": row["is_active"],
            "permissions": list(resolved_perms),
            "created_at": row["created_at"],
            "updated_at": row.get("updated_at"),
        }

    async def change_user_role(
        self,
        *,
        admin_id: uuid.UUID,
        admin_role: str,
        user_id: uuid.UUID,
        new_role: str,
        correlation_id: str | None = None,
    ) -> dict[str, Any]:
        """Change a user's role and write an audit record.

        Idempotent: if the new role equals the current role, returns the
        unchanged user with no audit record (edge case per AC).

        Args:
            admin_id:       UUID of the acting Platform Admin.
            admin_role:     Role string of the actor (must be ``platform_admin``).
            user_id:        UUID of the user whose role is changing.
            new_role:       Target role value (must be a valid :class:`UserRole`).
            correlation_id: Optional request correlation ID for the audit record.

        Returns:
            Updated user detail dict (same shape as :meth:`get_user_detail`).

        Raises:
            NotFoundError:  If the target user does not exist.
            ConflictError:  If this would remove the last Platform Admin.
        """
        row = await self._users.get_by_id(user_id)
        if row is None:
            raise NotFoundError(f"User {user_id!r} not found.")

        old_role: str = row.get("role", "")

        # Idempotent: no-op if role unchanged.
        if old_role == new_role:
            return await self.get_user_detail(user_id)

        # Last-admin protection: refuse to demote the final platform_admin.
        if old_role == UserRole.platform_admin.value and new_role != UserRole.platform_admin.value:
            count = await self._users.count_by_role(UserRole.platform_admin.value)
            if count <= 1:
                raise ConflictError(
                    "Cannot remove the last Platform Admin. "
                    "Assign another Platform Admin first."
                )

        updated = await self._users.update_role(user_id, new_role)
        if updated is None:
            raise NotFoundError(f"User {user_id!r} not found after update.")

        try:
            await self._audit.log_event(
                actor_id=admin_id,
                actor_role=admin_role,
                action="role_change",
                resource_type="user",
                resource_id=user_id,
                before_state={"role": old_role},
                after_state={"role": new_role},
                correlation_id=correlation_id,
            )
        except Exception:
            logger.warning(
                "rbac_admin.role_change.audit_failed",
                user_id=str(user_id),
                new_role=new_role,
            )

        logger.info(
            "rbac_admin.role_changed",
            admin_id=str(admin_id),
            user_id=str(user_id),
            old_role=old_role,
            new_role=new_role,
        )

        resolved_perms = sorted(get_permissions(new_role))
        return {
            "id": updated["id"],
            "email": updated["email"],
            "name": _build_name(updated),
            "role": updated["role"],
            "is_active": updated["is_active"],
            "permissions": list(resolved_perms),
            "created_at": updated["created_at"],
            "updated_at": updated.get("updated_at"),
        }

    async def toggle_user_status(
        self,
        *,
        admin_id: uuid.UUID,
        admin_role: str,
        user_id: uuid.UUID,
        is_active: bool,
        correlation_id: str | None = None,
    ) -> dict[str, Any]:
        """Activate or deactivate a user.

        On deactivation, all refresh tokens are immediately revoked.
        Idempotent: no audit record is written if the status is unchanged.

        Args:
            admin_id:       UUID of the acting Platform Admin.
            admin_role:     Role string of the actor.
            user_id:        UUID of the target user.
            is_active:      ``True`` to reactivate, ``False`` to deactivate.
            correlation_id: Optional request correlation ID.

        Returns:
            Updated user dict (compact: id, email, name, role, is_active).

        Raises:
            NotFoundError: If the user does not exist.
        """
        row = await self._users.get_by_id(user_id)
        if row is None:
            raise NotFoundError(f"User {user_id!r} not found.")

        old_active: bool = bool(row.get("is_active", True))

        updated = await self._users.update_status(user_id, is_active)
        if updated is None:
            raise NotFoundError(f"User {user_id!r} not found after update.")

        # Idempotent: skip audit record if status did not change.
        if old_active == is_active:
            return {
                "id": updated["id"],
                "email": updated["email"],
                "name": _build_name(updated),
                "role": updated["role"],
                "is_active": updated["is_active"],
            }

        # Revoke all sessions on deactivation.
        if not is_active:
            try:
                revoked = await self._tokens.revoke_all_for_user(uuid.UUID(str(user_id)))
                logger.info(
                    "rbac_admin.deactivation.tokens_revoked",
                    user_id=str(user_id),
                    count=revoked,
                )
            except Exception:
                logger.warning(
                    "rbac_admin.deactivation.token_revocation_failed",
                    user_id=str(user_id),
                )

        try:
            await self._audit.log_event(
                actor_id=admin_id,
                actor_role=admin_role,
                action="status_change",
                resource_type="user",
                resource_id=user_id,
                before_state={"is_active": old_active},
                after_state={"is_active": is_active},
                correlation_id=correlation_id,
            )
        except Exception:
            logger.warning(
                "rbac_admin.status_change.audit_failed",
                user_id=str(user_id),
                is_active=is_active,
            )

        logger.info(
            "rbac_admin.status_changed",
            admin_id=str(admin_id),
            user_id=str(user_id),
            is_active=is_active,
        )

        return {
            "id": updated["id"],
            "email": updated["email"],
            "name": _build_name(updated),
            "role": updated["role"],
            "is_active": updated["is_active"],
        }

    @staticmethod
    def list_roles() -> list[dict[str, Any]]:
        """Return all six ForgeGuard roles with their permission sets.

        This is a static operation — no I/O needed.
        """
        return [
            {
                "name": role.value,
                "permissions": sorted(ROLE_PERMISSIONS.get(role, frozenset())),
            }
            for role in UserRole
        ]
