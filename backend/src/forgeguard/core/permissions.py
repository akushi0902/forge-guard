"""Role definitions and permission mappings for the ForgeGuard RBAC model."""

from __future__ import annotations

from enum import Enum


class UserRole(str, Enum):
    """The six ForgeGuard personas.

    Values match the CHECK constraint in the USERS table and the VALID_ROLES
    tuple in data/models/identity.py.  Using ``str`` as a mixin allows the
    enum values to be serialised directly as JSON strings.
    """

    developer = "developer"
    tech_lead = "tech_lead"
    security_reviewer = "security_reviewer"
    platform_admin = "platform_admin"
    engineering_manager = "engineering_manager"
    operator = "operator"


# Permission slug → set of roles that hold it.
# Kept here so the data layer (UserRepository.check_permissions) and the API
# layer both read from the same authoritative source in the absence of a
# live role-permissions join table.
ROLE_PERMISSIONS: dict[UserRole, frozenset[str]] = {
    UserRole.developer: frozenset({
        "release.view",
        "policy.view",
        "service.view",
        "service.create",
        "service.update",
    }),
    UserRole.tech_lead: frozenset({
        "release.view",
        "release.approve",
        "policy.view",
        "service.view",
        "service.create",
        "service.update",
        "service.delete",
        "team.manage",
    }),
    UserRole.security_reviewer: frozenset({
        "release.view",
        "release.block",
        "policy.view",
        "policy.review",
        "service.view",
        "vulnerability.view",
        "vulnerability.manage",
    }),
    UserRole.platform_admin: frozenset({
        "release.view",
        "release.approve",
        "release.block",
        "policy.view",
        "policy.manage",
        "policy.review",
        "service.view",
        "service.create",
        "service.update",
        "service.delete",
        "team.manage",
        "user.manage",
        "vulnerability.view",
        "vulnerability.manage",
        "admin.full_access",
    }),
    UserRole.engineering_manager: frozenset({
        "release.view",
        "release.approve",
        "policy.view",
        "service.view",
        "service.create",
        "service.update",
        "team.manage",
        "team.view",
    }),
    UserRole.operator: frozenset({
        "release.view",
        "service.view",
        "policy.view",
        "platform.monitor",
        "platform.operate",
    }),
}
