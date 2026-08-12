"""Role definitions, permission constants, and the RBAC permission matrix.

Design invariants:
    - The matrix is defined as a frozen data structure in code (not DB) so
      permission checks are O(1) with zero network latency.
    - Permission constants live on :class:`Permissions` — never use raw strings
      in route handlers or service code (prevents typos, enables IDE autocomplete).
    - :func:`has_permission` is deny-by-default: any unmapped role or permission
      returns False rather than raising an exception.
    - Conditional permissions (e.g. ``exception.approve`` routed by finding
      dimension) are handled by :meth:`~forgeguard.services.rbac.RBACService.
      check_conditional_permission`, not by the static matrix.
"""

from __future__ import annotations

from enum import Enum
from typing import List


# ---------------------------------------------------------------------------
# Permission constants
# ---------------------------------------------------------------------------

class Permissions:
    """String constants for the ten ForgeGuard permission slugs.

    Always reference these constants instead of inline strings to prevent typos
    and enable IDE autocomplete / rename refactoring.
    """

    SERVICE_VIEW = "service.view"
    ASSESSMENT_REQUEST = "assessment.request"
    RELEASE_APPROVE = "release.approve"
    RELEASE_BLOCK = "release.block"
    EXCEPTION_REQUEST = "exception.request"
    EXCEPTION_APPROVE = "exception.approve"
    POLICY_MANAGE = "policy.manage"
    RBAC_MANAGE = "rbac.manage"
    HEALTH_MONITOR = "health.monitor"
    TRENDS_VIEW = "trends.view"
    AUDIT_VIEW = "audit.view"


#: Frozenset of every defined permission slug, used by Platform Admin sentinel.
ALL_PERMISSIONS: frozenset[str] = frozenset({
    Permissions.SERVICE_VIEW,
    Permissions.ASSESSMENT_REQUEST,
    Permissions.RELEASE_APPROVE,
    Permissions.RELEASE_BLOCK,
    Permissions.EXCEPTION_REQUEST,
    Permissions.EXCEPTION_APPROVE,
    Permissions.POLICY_MANAGE,
    Permissions.RBAC_MANAGE,
    Permissions.HEALTH_MONITOR,
    Permissions.TRENDS_VIEW,
    Permissions.AUDIT_VIEW,
})


# ---------------------------------------------------------------------------
# Role enum
# ---------------------------------------------------------------------------

class UserRole(str, Enum):
    """The six ForgeGuard personas.

    Values match the CHECK constraint in the USERS table.  Using ``str`` as a
    mixin allows enum values to be serialised directly as JSON strings and
    compared to raw VARCHAR values from the database without conversion.
    """

    developer = "developer"
    tech_lead = "tech_lead"
    security_reviewer = "security_reviewer"
    platform_admin = "platform_admin"
    engineering_manager = "engineering_manager"
    operator = "operator"


# ---------------------------------------------------------------------------
# Role → permission matrix
# ---------------------------------------------------------------------------

# Note: exception.approve for tech_lead (policy dimension) and security_reviewer
# (security dimension) is conditional — those roles are NOT in this static map
# for that permission.  Conditional checks are handled separately by RBACService.
ROLE_PERMISSIONS: dict[UserRole, frozenset[str]] = {
    UserRole.developer: frozenset({
        Permissions.SERVICE_VIEW,
        Permissions.ASSESSMENT_REQUEST,
        Permissions.EXCEPTION_REQUEST,
    }),
    UserRole.tech_lead: frozenset({
        Permissions.SERVICE_VIEW,
        Permissions.ASSESSMENT_REQUEST,
        Permissions.RELEASE_APPROVE,
        Permissions.EXCEPTION_REQUEST,
        Permissions.TRENDS_VIEW,
        # exception.approve is conditional (policy dimension only) — not here
    }),
    UserRole.security_reviewer: frozenset({
        Permissions.SERVICE_VIEW,
        Permissions.RELEASE_BLOCK,
        # exception.approve is conditional (security dimension only) — not here
    }),
    UserRole.platform_admin: ALL_PERMISSIONS,
    UserRole.engineering_manager: frozenset({
        Permissions.SERVICE_VIEW,
        Permissions.TRENDS_VIEW,
    }),
    UserRole.operator: frozenset({
        Permissions.SERVICE_VIEW,
        Permissions.HEALTH_MONITOR,
    }),
}


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------

def has_permission(role: str, permission: str) -> bool:
    """Return True if *role* includes *permission* in the static matrix.

    Deny-by-default: returns False for unknown roles and unknown permissions.
    Conditional permissions (exception.approve routing) are NOT checked here;
    use :func:`~forgeguard.services.rbac.RBACService.check_conditional_permission`
    for those.

    Args:
        role:       Role string (e.g. ``"developer"``).  Must match a
                    :class:`UserRole` value.
        permission: Permission slug (e.g. ``Permissions.SERVICE_VIEW``).

    Returns:
        True iff the role is mapped and the permission is in its frozenset.

    Examples::

        has_permission("platform_admin", Permissions.POLICY_MANAGE)  # True
        has_permission("developer", Permissions.POLICY_MANAGE)        # False
        has_permission("unknown_role", Permissions.SERVICE_VIEW)      # False
    """
    try:
        role_enum = UserRole(role)
    except ValueError:
        return False
    return permission in ROLE_PERMISSIONS.get(role_enum, frozenset())


def get_permissions(role: str) -> frozenset[str]:
    """Return the complete static permission set for *role*.

    Args:
        role: Role string.  Must match a :class:`UserRole` value.

    Returns:
        Frozenset of permission slugs; empty frozenset for unknown roles.
    """
    try:
        role_enum = UserRole(role)
    except ValueError:
        return frozenset()
    return ROLE_PERMISSIONS.get(role_enum, frozenset())


def get_roles_with_permission(permission: str) -> List[str]:
    """Return the list of role strings that hold *permission* in the static matrix.

    Used to build actionable 403 error messages that tell the caller which role
    they need to request.

    Args:
        permission: Permission slug to look up.

    Returns:
        List of role value strings (e.g. ``["tech_lead", "platform_admin"]``).
        Returns an empty list if no role has the permission (or permission is unknown).
    """
    return [
        role.value
        for role, perms in ROLE_PERMISSIONS.items()
        if permission in perms
    ]
