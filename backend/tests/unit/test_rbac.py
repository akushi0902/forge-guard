"""Unit tests for RBAC module (WO-026).

Coverage:
  - All 60 cells of the 6-role × 10-permission matrix
  - has_permission edge cases (unknown role, unknown permission, empty string)
  - get_permissions returns correct frozenset per role
  - get_roles_with_permission inverse lookup
  - RBACService.check_permission raises PermissionDeniedError with correct fields
  - RBACService.check_conditional_permission for exception.approve routing
  - require_permission and require_any_permission dependency behaviour
"""

from __future__ import annotations

import pytest

from forgeguard.core.exceptions import PermissionDeniedError
from forgeguard.core.permissions import (
    ALL_PERMISSIONS,
    Permissions,
    UserRole,
    get_permissions,
    get_roles_with_permission,
    has_permission,
)
from forgeguard.services.rbac import RBACService
from tests.fixtures.rbac import make_mock_request


# ---------------------------------------------------------------------------
# Exhaustive role-permission matrix (6 roles × 10 permissions = 60 cells)
# ---------------------------------------------------------------------------

# Expected truth table: (role, permission) -> True/False
_MATRIX: list[tuple[str, str, bool]] = [
    # Developer
    ("developer", Permissions.SERVICE_VIEW,       True),
    ("developer", Permissions.ASSESSMENT_REQUEST, True),
    ("developer", Permissions.RELEASE_APPROVE,    False),
    ("developer", Permissions.RELEASE_BLOCK,      False),
    ("developer", Permissions.EXCEPTION_REQUEST,  True),
    ("developer", Permissions.EXCEPTION_APPROVE,  False),
    ("developer", Permissions.POLICY_MANAGE,      False),
    ("developer", Permissions.RBAC_MANAGE,        False),
    ("developer", Permissions.HEALTH_MONITOR,     False),
    ("developer", Permissions.TRENDS_VIEW,        False),

    # Tech Lead
    ("tech_lead", Permissions.SERVICE_VIEW,       True),
    ("tech_lead", Permissions.ASSESSMENT_REQUEST, True),
    ("tech_lead", Permissions.RELEASE_APPROVE,    True),
    ("tech_lead", Permissions.RELEASE_BLOCK,      False),
    ("tech_lead", Permissions.EXCEPTION_REQUEST,  True),
    ("tech_lead", Permissions.EXCEPTION_APPROVE,  False),  # conditional only
    ("tech_lead", Permissions.POLICY_MANAGE,      False),
    ("tech_lead", Permissions.RBAC_MANAGE,        False),
    ("tech_lead", Permissions.HEALTH_MONITOR,     False),
    ("tech_lead", Permissions.TRENDS_VIEW,        True),

    # Security Reviewer
    ("security_reviewer", Permissions.SERVICE_VIEW,       True),
    ("security_reviewer", Permissions.ASSESSMENT_REQUEST, False),
    ("security_reviewer", Permissions.RELEASE_APPROVE,    False),
    ("security_reviewer", Permissions.RELEASE_BLOCK,      True),
    ("security_reviewer", Permissions.EXCEPTION_REQUEST,  False),
    ("security_reviewer", Permissions.EXCEPTION_APPROVE,  False),  # conditional only
    ("security_reviewer", Permissions.POLICY_MANAGE,      False),
    ("security_reviewer", Permissions.RBAC_MANAGE,        False),
    ("security_reviewer", Permissions.HEALTH_MONITOR,     False),
    ("security_reviewer", Permissions.TRENDS_VIEW,        False),

    # Platform Admin (all permissions)
    ("platform_admin", Permissions.SERVICE_VIEW,       True),
    ("platform_admin", Permissions.ASSESSMENT_REQUEST, True),
    ("platform_admin", Permissions.RELEASE_APPROVE,    True),
    ("platform_admin", Permissions.RELEASE_BLOCK,      True),
    ("platform_admin", Permissions.EXCEPTION_REQUEST,  True),
    ("platform_admin", Permissions.EXCEPTION_APPROVE,  True),
    ("platform_admin", Permissions.POLICY_MANAGE,      True),
    ("platform_admin", Permissions.RBAC_MANAGE,        True),
    ("platform_admin", Permissions.HEALTH_MONITOR,     True),
    ("platform_admin", Permissions.TRENDS_VIEW,        True),

    # Engineering Manager
    ("engineering_manager", Permissions.SERVICE_VIEW,       True),
    ("engineering_manager", Permissions.ASSESSMENT_REQUEST, False),
    ("engineering_manager", Permissions.RELEASE_APPROVE,    False),
    ("engineering_manager", Permissions.RELEASE_BLOCK,      False),
    ("engineering_manager", Permissions.EXCEPTION_REQUEST,  False),
    ("engineering_manager", Permissions.EXCEPTION_APPROVE,  False),
    ("engineering_manager", Permissions.POLICY_MANAGE,      False),
    ("engineering_manager", Permissions.RBAC_MANAGE,        False),
    ("engineering_manager", Permissions.HEALTH_MONITOR,     False),
    ("engineering_manager", Permissions.TRENDS_VIEW,        True),

    # Operator
    ("operator", Permissions.SERVICE_VIEW,       True),
    ("operator", Permissions.ASSESSMENT_REQUEST, False),
    ("operator", Permissions.RELEASE_APPROVE,    False),
    ("operator", Permissions.RELEASE_BLOCK,      False),
    ("operator", Permissions.EXCEPTION_REQUEST,  False),
    ("operator", Permissions.EXCEPTION_APPROVE,  False),
    ("operator", Permissions.POLICY_MANAGE,      False),
    ("operator", Permissions.RBAC_MANAGE,        False),
    ("operator", Permissions.HEALTH_MONITOR,     True),
    ("operator", Permissions.TRENDS_VIEW,        False),
]


class TestRolePermissionMatrix:
    """Exhaustive 60-cell matrix test."""

    @pytest.mark.parametrize("role,permission,expected", _MATRIX)
    def test_matrix_cell(self, role: str, permission: str, expected: bool):
        assert has_permission(role, permission) is expected, (
            f"has_permission({role!r}, {permission!r}) should be {expected}"
        )


# ---------------------------------------------------------------------------
# has_permission edge cases
# ---------------------------------------------------------------------------

class TestHasPermissionEdgeCases:
    def test_unknown_role_returns_false(self):
        assert has_permission("superuser", Permissions.SERVICE_VIEW) is False

    def test_empty_role_returns_false(self):
        assert has_permission("", Permissions.SERVICE_VIEW) is False

    def test_unknown_permission_returns_false(self):
        assert has_permission("platform_admin", "nonexistent.permission") is False

    def test_empty_permission_returns_false(self):
        assert has_permission("platform_admin", "") is False

    def test_case_sensitive_role(self):
        assert has_permission("Developer", Permissions.SERVICE_VIEW) is False

    def test_case_sensitive_permission(self):
        assert has_permission("developer", "Service.View") is False

    def test_returns_bool_not_truthy(self):
        result = has_permission("developer", Permissions.SERVICE_VIEW)
        assert result is True
        result2 = has_permission("developer", Permissions.POLICY_MANAGE)
        assert result2 is False


# ---------------------------------------------------------------------------
# get_permissions
# ---------------------------------------------------------------------------

class TestGetPermissions:
    def test_developer_permissions(self):
        perms = get_permissions("developer")
        assert Permissions.SERVICE_VIEW in perms
        assert Permissions.ASSESSMENT_REQUEST in perms
        assert Permissions.EXCEPTION_REQUEST in perms
        assert len(perms) == 3

    def test_platform_admin_has_all_permissions(self):
        perms = get_permissions("platform_admin")
        assert perms == ALL_PERMISSIONS

    def test_engineering_manager_permissions(self):
        perms = get_permissions("engineering_manager")
        assert perms == frozenset({Permissions.SERVICE_VIEW, Permissions.TRENDS_VIEW})

    def test_operator_permissions(self):
        perms = get_permissions("operator")
        assert perms == frozenset({Permissions.SERVICE_VIEW, Permissions.HEALTH_MONITOR})

    def test_unknown_role_returns_empty_frozenset(self):
        perms = get_permissions("unknown")
        assert perms == frozenset()
        assert isinstance(perms, frozenset)

    def test_returns_frozenset(self):
        perms = get_permissions("developer")
        assert isinstance(perms, frozenset)


# ---------------------------------------------------------------------------
# get_roles_with_permission
# ---------------------------------------------------------------------------

class TestGetRolesWithPermission:
    def test_service_view_available_to_all_roles(self):
        roles = get_roles_with_permission(Permissions.SERVICE_VIEW)
        all_roles = {r.value for r in UserRole}
        assert set(roles) == all_roles

    def test_policy_manage_only_platform_admin(self):
        roles = get_roles_with_permission(Permissions.POLICY_MANAGE)
        assert roles == ["platform_admin"]

    def test_rbac_manage_only_platform_admin(self):
        roles = get_roles_with_permission(Permissions.RBAC_MANAGE)
        assert roles == ["platform_admin"]

    def test_release_approve_tech_lead_and_admin(self):
        roles = set(get_roles_with_permission(Permissions.RELEASE_APPROVE))
        assert "tech_lead" in roles
        assert "platform_admin" in roles

    def test_trends_view_has_tech_lead_and_em(self):
        roles = set(get_roles_with_permission(Permissions.TRENDS_VIEW))
        assert "tech_lead" in roles
        assert "engineering_manager" in roles
        assert "platform_admin" in roles

    def test_unknown_permission_returns_empty_list(self):
        roles = get_roles_with_permission("no.such.permission")
        assert roles == []

    def test_returns_list(self):
        roles = get_roles_with_permission(Permissions.SERVICE_VIEW)
        assert isinstance(roles, list)


# ---------------------------------------------------------------------------
# RBACService.check_permission
# ---------------------------------------------------------------------------

class TestRBACServiceCheckPermission:
    def setup_method(self):
        self.service = RBACService()

    def test_authorized_role_does_not_raise(self):
        self.service.check_permission("developer", Permissions.SERVICE_VIEW)

    def test_unauthorized_role_raises_permission_denied_error(self):
        with pytest.raises(PermissionDeniedError):
            self.service.check_permission("developer", Permissions.POLICY_MANAGE)

    def test_error_carries_required_permission(self):
        with pytest.raises(PermissionDeniedError) as exc_info:
            self.service.check_permission("operator", Permissions.RELEASE_APPROVE)
        assert exc_info.value.required_permission == Permissions.RELEASE_APPROVE

    def test_error_carries_required_roles(self):
        with pytest.raises(PermissionDeniedError) as exc_info:
            self.service.check_permission("developer", Permissions.RELEASE_APPROVE)
        assert "platform_admin" in exc_info.value.required_roles

    def test_error_message_contains_permission(self):
        with pytest.raises(PermissionDeniedError) as exc_info:
            self.service.check_permission("operator", Permissions.POLICY_MANAGE)
        assert Permissions.POLICY_MANAGE in str(exc_info.value)

    def test_error_message_mentions_platform_admin(self):
        with pytest.raises(PermissionDeniedError) as exc_info:
            self.service.check_permission("operator", Permissions.POLICY_MANAGE)
        assert "Platform Admin" in str(exc_info.value)

    def test_unknown_role_denied(self):
        with pytest.raises(PermissionDeniedError):
            self.service.check_permission("ghost", Permissions.SERVICE_VIEW)

    def test_platform_admin_allowed_all_permissions(self):
        for perm in ALL_PERMISSIONS:
            self.service.check_permission("platform_admin", perm)  # must not raise

    def test_status_code_is_403(self):
        with pytest.raises(PermissionDeniedError) as exc_info:
            self.service.check_permission("developer", Permissions.RBAC_MANAGE)
        assert exc_info.value.status_code == 403


# ---------------------------------------------------------------------------
# RBACService.check_conditional_permission
# ---------------------------------------------------------------------------

class TestRBACServiceConditionalPermission:
    def setup_method(self):
        self.service = RBACService()

    def test_security_reviewer_approved_for_security_dimension(self):
        self.service.check_conditional_permission(
            "security_reviewer", Permissions.EXCEPTION_APPROVE, {"dimension": "security"}
        )  # must not raise

    def test_tech_lead_approved_for_policy_dimension(self):
        self.service.check_conditional_permission(
            "tech_lead", Permissions.EXCEPTION_APPROVE, {"dimension": "policy"}
        )  # must not raise

    def test_platform_admin_approved_for_security_dimension(self):
        self.service.check_conditional_permission(
            "platform_admin", Permissions.EXCEPTION_APPROVE, {"dimension": "security"}
        )

    def test_platform_admin_approved_for_policy_dimension(self):
        self.service.check_conditional_permission(
            "platform_admin", Permissions.EXCEPTION_APPROVE, {"dimension": "policy"}
        )

    def test_security_reviewer_denied_for_policy_dimension(self):
        with pytest.raises(PermissionDeniedError):
            self.service.check_conditional_permission(
                "security_reviewer", Permissions.EXCEPTION_APPROVE, {"dimension": "policy"}
            )

    def test_tech_lead_denied_for_security_dimension(self):
        with pytest.raises(PermissionDeniedError):
            self.service.check_conditional_permission(
                "tech_lead", Permissions.EXCEPTION_APPROVE, {"dimension": "security"}
            )

    def test_missing_dimension_is_denied(self):
        with pytest.raises(PermissionDeniedError):
            self.service.check_conditional_permission(
                "security_reviewer", Permissions.EXCEPTION_APPROVE, {}
            )

    def test_unknown_dimension_is_denied(self):
        with pytest.raises(PermissionDeniedError):
            self.service.check_conditional_permission(
                "platform_admin", Permissions.EXCEPTION_APPROVE, {"dimension": "compliance"}
            )

    def test_developer_denied_exception_approve_any_dimension(self):
        with pytest.raises(PermissionDeniedError):
            self.service.check_conditional_permission(
                "developer", Permissions.EXCEPTION_APPROVE, {"dimension": "security"}
            )

    def test_non_conditional_permission_delegates_to_check_permission(self):
        # service.view is not conditional — should pass for developer
        self.service.check_conditional_permission(
            "developer", Permissions.SERVICE_VIEW, {}
        )

    def test_non_conditional_denied_permission_still_raises(self):
        with pytest.raises(PermissionDeniedError):
            self.service.check_conditional_permission(
                "developer", Permissions.RBAC_MANAGE, {}
            )


# ---------------------------------------------------------------------------
# require_permission dependency
# ---------------------------------------------------------------------------

class TestRequirePermissionDependency:
    async def test_authorized_role_passes(self):
        from forgeguard.api.dependencies.rbac import require_permission  # noqa: PLC0415

        dep = require_permission(Permissions.SERVICE_VIEW)
        req = make_mock_request("developer")
        await dep(req)  # must not raise

    async def test_unauthorized_role_raises_permission_denied(self):
        from forgeguard.api.dependencies.rbac import require_permission  # noqa: PLC0415

        dep = require_permission(Permissions.POLICY_MANAGE)
        req = make_mock_request("developer")
        with pytest.raises(PermissionDeniedError):
            await dep(req)

    async def test_missing_user_role_is_denied(self):
        from forgeguard.api.dependencies.rbac import require_permission  # noqa: PLC0415
        from unittest.mock import MagicMock  # noqa: PLC0415

        dep = require_permission(Permissions.SERVICE_VIEW)
        req = MagicMock()
        req.state = MagicMock(spec=[])  # no user_role attribute
        with pytest.raises(PermissionDeniedError):
            await dep(req)

    async def test_platform_admin_passes_any_permission(self):
        from forgeguard.api.dependencies.rbac import require_permission  # noqa: PLC0415

        req = make_mock_request("platform_admin")
        for perm in ALL_PERMISSIONS:
            dep = require_permission(perm)
            await dep(req)  # must not raise


# ---------------------------------------------------------------------------
# require_any_permission dependency
# ---------------------------------------------------------------------------

class TestRequireAnyPermissionDependency:
    async def test_role_with_first_permission_passes(self):
        from forgeguard.api.dependencies.rbac import require_any_permission  # noqa: PLC0415

        dep = require_any_permission([Permissions.SERVICE_VIEW, Permissions.POLICY_MANAGE])
        req = make_mock_request("developer")
        await dep(req)  # developer has service.view

    async def test_role_with_second_permission_passes(self):
        from forgeguard.api.dependencies.rbac import require_any_permission  # noqa: PLC0415

        dep = require_any_permission([Permissions.RBAC_MANAGE, Permissions.TRENDS_VIEW])
        req = make_mock_request("tech_lead")
        await dep(req)  # tech_lead has trends.view

    async def test_role_without_any_permission_is_denied(self):
        from forgeguard.api.dependencies.rbac import require_any_permission  # noqa: PLC0415

        dep = require_any_permission([Permissions.POLICY_MANAGE, Permissions.RBAC_MANAGE])
        req = make_mock_request("developer")
        with pytest.raises(PermissionDeniedError):
            await dep(req)

    async def test_empty_list_always_denies(self):
        from forgeguard.api.dependencies.rbac import require_any_permission  # noqa: PLC0415

        dep = require_any_permission([])
        req = make_mock_request("platform_admin")
        with pytest.raises(PermissionDeniedError):
            await dep(req)
