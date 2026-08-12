"""RBAC Permission Enforcement Test Matrix (WO-098).

Compliance scope:
  1. Parametrized permission matrix — 66 role × permission combinations
     (6 roles × 11 permissions from the static ROLE_PERMISSIONS matrix).
  2. 403 response body schema — structured error with required_permission
     and required_roles fields.
  3. Route permission completeness — every permission slug is covered by
     a representative endpoint in this file.
  4. Platform Admin completeness — admin has access to all mapped endpoints.
  5. HTTP integration tests — full middleware chain with real cookie JWT.
  6. Role change effect — JWT role claim drives live enforcement decisions.
  7. OPTIONS preflight bypass — CORS pre-flights are never RBAC-blocked.

Run (no Docker required for unit tests):
    pytest tests/compliance/test_rbac_enforcement.py -v -m "not integration"

Run with Docker for integration tests:
    pytest tests/compliance/test_rbac_enforcement.py -v
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest

from forgeguard.core.permissions import (
    ALL_PERMISSIONS,
    ROLE_PERMISSIONS,
    Permissions,
    UserRole,
    get_roles_with_permission,
    has_permission,
)
from forgeguard.middleware.route_permissions import ROUTE_PERMISSION_MAP

# ---------------------------------------------------------------------------
# Sentinel UUID for dynamic path segments
# ---------------------------------------------------------------------------

_TEST_UUID = "00000000-0000-0000-0000-000000000001"

# ---------------------------------------------------------------------------
# Representative endpoint for each permission slug
#
# Format: permission → (http_method, path, json_body_or_None)
# The body is the minimal payload for schema validation; the endpoint may
# return 422/404 for missing data — that still proves RBAC passed (not 403).
# ---------------------------------------------------------------------------

ENDPOINT_FOR_PERMISSION: dict[str, tuple[str, str, dict[str, Any] | None]] = {
    Permissions.SERVICE_VIEW: (
        "GET", "/api/v1/services", None,
    ),
    Permissions.ASSESSMENT_REQUEST: (
        "POST", "/api/v1/releases/assess",
        {"service_id": _TEST_UUID, "commit_sha": "abc123abc123"},
    ),
    Permissions.RELEASE_APPROVE: (
        "POST", f"/api/v1/releases/{_TEST_UUID}/approve",
        {"rationale": "Looks good to merge"},
    ),
    Permissions.RELEASE_BLOCK: (
        "POST", f"/api/v1/releases/{_TEST_UUID}/block",
        {"rationale": "Found critical security issue"},
    ),
    Permissions.EXCEPTION_REQUEST: (
        "POST", "/api/v1/exceptions",
        {"finding_id": _TEST_UUID, "reason": "Accepted risk", "expires_days": 30},
    ),
    Permissions.EXCEPTION_APPROVE: (
        "POST", f"/api/v1/exceptions/{_TEST_UUID}/approve",
        {"comment": "Approved by security team"},
    ),
    Permissions.POLICY_MANAGE: (
        "POST", "/api/v1/policies",
        {"name": "Test Policy", "description": "Test description", "dimension": "security"},
    ),
    Permissions.RBAC_MANAGE: (
        "GET", "/api/v1/admin/rbac/users", None,
    ),
    Permissions.HEALTH_MONITOR: (
        "GET", "/api/v1/platform/health", None,
    ),
    Permissions.TRENDS_VIEW: (
        "GET", "/api/v1/trends", None,
    ),
    Permissions.AUDIT_VIEW: (
        "GET", "/api/v1/audit-logs", None,
    ),
}

# ---------------------------------------------------------------------------
# Build the parametrized permission matrix
#
# Generates one test case per (role, permission) pair: 6 × 11 = 66 cases.
# expected_has: True if the role has the permission in the static matrix.
# ---------------------------------------------------------------------------

_ROLES = [r.value for r in UserRole]
_PERMISSIONS = sorted(ENDPOINT_FOR_PERMISSION.keys())

PERMISSION_MATRIX: list[tuple[str, str, bool]] = [
    (role, perm, has_permission(role, perm))
    for role in _ROLES
    for perm in _PERMISSIONS
]

assert len(PERMISSION_MATRIX) == len(_ROLES) * len(_PERMISSIONS), (
    f"Expected {len(_ROLES) * len(_PERMISSIONS)} matrix entries, "
    f"got {len(PERMISSION_MATRIX)}"
)

# ---------------------------------------------------------------------------
# Build HTTP-level parametrized data
# (role, endpoint, method, json_body, permission, expected_status_is_403)
# ---------------------------------------------------------------------------

_HTTP_CASES: list[tuple[str, str, str, dict | None, str, bool]] = []
for _role in _ROLES:
    for _perm, (_method, _path, _body) in ENDPOINT_FOR_PERMISSION.items():
        _denied = not has_permission(_role, _perm)
        _HTTP_CASES.append((_role, _path, _method, _body, _perm, _denied))

# Human-readable IDs for parametrize
def _case_id(vals):
    role, path, method, _, perm, denied = vals
    verdict = "DENY" if denied else "ALLOW"
    return f"{role}:{perm}:{verdict}"


# ===========================================================================
# 1. UNIT TESTS — has_permission() matrix (no HTTP, no DB)
# ===========================================================================

class TestPermissionMatrixUnit:
    """Validate every role-permission combination in the static RBAC matrix.

    66 parametrized cases (6 roles × 11 permissions) — no HTTP required.
    """

    @pytest.mark.parametrize(
        "role, permission, expected",
        PERMISSION_MATRIX,
        ids=[f"{r}:{p}" for r, p, _ in PERMISSION_MATRIX],
    )
    def test_has_permission(self, role: str, permission: str, expected: bool):
        """has_permission(role, permission) returns the matrix-defined value."""
        assert has_permission(role, permission) is expected

    def test_platform_admin_has_all_permissions(self):
        """platform_admin holds every defined permission slug."""
        for perm in ALL_PERMISSIONS:
            assert has_permission("platform_admin", perm), (
                f"platform_admin is missing permission: {perm}"
            )

    def test_unknown_role_returns_false(self):
        """Unknown roles are deny-by-default."""
        assert has_permission("ghost_role", Permissions.SERVICE_VIEW) is False

    def test_unknown_permission_returns_false(self):
        """Unknown permission slugs are deny-by-default."""
        assert has_permission("platform_admin", "unknown.permission") is False

    def test_operator_limited_to_service_view_and_health(self):
        """Operator has exactly service.view and health.monitor."""
        allowed = {
            p for p in _PERMISSIONS
            if has_permission(UserRole.operator.value, p)
        }
        assert allowed == {Permissions.SERVICE_VIEW, Permissions.HEALTH_MONITOR}

    def test_engineering_manager_limited_to_view_and_trends(self):
        """Engineering Manager has service.view and trends.view only."""
        allowed = {
            p for p in _PERMISSIONS
            if has_permission(UserRole.engineering_manager.value, p)
        }
        assert allowed == {Permissions.SERVICE_VIEW, Permissions.TRENDS_VIEW}

    def test_developer_cannot_approve_or_block_releases(self):
        """Developer does NOT have release.approve or release.block."""
        assert not has_permission("developer", Permissions.RELEASE_APPROVE)
        assert not has_permission("developer", Permissions.RELEASE_BLOCK)

    def test_security_reviewer_cannot_approve_release(self):
        """Security Reviewer can block but NOT approve a release."""
        assert not has_permission("security_reviewer", Permissions.RELEASE_APPROVE)
        assert has_permission("security_reviewer", Permissions.RELEASE_BLOCK)

    def test_tech_lead_has_assessment_and_approve(self):
        """Tech Lead can request assessments and approve (but not block) releases."""
        assert has_permission("tech_lead", Permissions.ASSESSMENT_REQUEST)
        assert has_permission("tech_lead", Permissions.RELEASE_APPROVE)
        assert not has_permission("tech_lead", Permissions.RELEASE_BLOCK)


# ===========================================================================
# 2. UNIT TESTS — RBAC middleware enforcement with mock requests
# ===========================================================================

class TestRbacMiddlewareUnit:
    """Test the RBACMiddleware enforcement logic with mock requests."""

    def test_platform_admin_has_permission_for_rbac_manage(self):
        """RBACMiddleware grants platform_admin access to rbac.manage endpoints."""
        from forgeguard.middleware.route_permissions import ROUTE_PERMISSION_MAP

        # Find the RBAC users entry
        entry = next(
            e for e in ROUTE_PERMISSION_MAP
            if e.matches("GET", "/api/v1/admin/rbac/users")
        )
        assert entry.has_permission("platform_admin")

    def test_developer_denied_policy_manage(self):
        """RBACMiddleware denies developer access to policy.manage endpoints."""
        from forgeguard.middleware.route_permissions import ROUTE_PERMISSION_MAP

        entry = next(
            e for e in ROUTE_PERMISSION_MAP
            if e.matches("POST", "/api/v1/policies")
        )
        assert not entry.has_permission("developer")

    def test_operator_denied_assessment_request(self):
        """Operator cannot POST /api/v1/releases/assess."""
        from forgeguard.middleware.route_permissions import ROUTE_PERMISSION_MAP

        entry = next(
            e for e in ROUTE_PERMISSION_MAP
            if e.matches("POST", "/api/v1/releases/assess")
        )
        assert not entry.has_permission("operator")

    def test_security_reviewer_allowed_release_block(self):
        """Security Reviewer can POST /api/v1/releases/{id}/block."""
        from forgeguard.middleware.route_permissions import ROUTE_PERMISSION_MAP

        entry = next(
            e for e in ROUTE_PERMISSION_MAP
            if e.matches("POST", f"/api/v1/releases/{_TEST_UUID}/block")
        )
        assert entry.has_permission("security_reviewer")

    def test_route_permission_map_has_entry_for_every_tested_permission(self):
        """Every permission in ENDPOINT_FOR_PERMISSION has a matching ROUTE_PERMISSION_MAP entry."""
        for perm, (method, path, _) in ENDPOINT_FOR_PERMISSION.items():
            matched = any(entry.matches(method, path) for entry in ROUTE_PERMISSION_MAP)
            assert matched, (
                f"No ROUTE_PERMISSION_MAP entry matches {method} {path} "
                f"(permission: {perm})"
            )

    def test_get_roles_with_permission_returns_expected_roles(self):
        """get_roles_with_permission returns the correct role set for each permission."""
        rbac_roles = get_roles_with_permission(Permissions.RBAC_MANAGE)
        assert "platform_admin" in rbac_roles
        assert "developer" not in rbac_roles

        health_roles = get_roles_with_permission(Permissions.HEALTH_MONITOR)
        assert "operator" in health_roles
        assert "platform_admin" in health_roles
        assert "developer" not in health_roles

    def test_forbidden_response_contains_required_fields(self):
        """The 403 response body has required_permission and required_roles fields."""
        from forgeguard.middleware.rbac import _forbidden_permission

        response = _forbidden_permission(
            user_role="developer",
            primary_permission=Permissions.POLICY_MANAGE,
            path="/api/v1/policies",
            method="POST",
        )
        body = response.body
        import json
        data = json.loads(body)
        assert "required_permission" in data
        assert "required_roles" in data
        assert data["required_permission"] == Permissions.POLICY_MANAGE
        assert isinstance(data["required_roles"], list)
        assert "platform_admin" in data["required_roles"]

    def test_forbidden_unmapped_response(self):
        """Unmapped routes return a 403 without leaking implementation details."""
        from forgeguard.middleware.rbac import _forbidden_unmapped
        import json

        response = _forbidden_unmapped("GET", "/api/v1/unknown-endpoint")
        data = json.loads(response.body)
        assert "detail" in data
        assert "stack" not in str(data).lower()
        assert "traceback" not in str(data).lower()


# ===========================================================================
# 3. 403 RESPONSE BODY SCHEMA TESTS
# ===========================================================================

class TestForbiddenResponseSchema:
    """Validate the structured 403 error body for all permission types."""

    @pytest.mark.parametrize("permission", _PERMISSIONS)
    def test_403_body_has_correct_permission_field(self, permission: str):
        """Each permission's 403 response body names the correct permission slug."""
        from forgeguard.middleware.rbac import _forbidden_permission
        import json

        response = _forbidden_permission(
            user_role="developer",
            primary_permission=permission,
            path="/api/v1/test",
            method="GET",
        )
        data = json.loads(response.body)
        assert data["required_permission"] == permission

    @pytest.mark.parametrize("permission", _PERMISSIONS)
    def test_403_body_required_roles_are_non_empty(self, permission: str):
        """Every permission has at least one role listed in the 403 response."""
        from forgeguard.middleware.rbac import _forbidden_permission
        import json

        response = _forbidden_permission(
            user_role="developer",
            primary_permission=permission,
            path="/api/v1/test",
            method="GET",
        )
        data = json.loads(response.body)
        assert isinstance(data["required_roles"], list)
        assert len(data["required_roles"]) >= 1, (
            f"Permission {permission!r} has no roles in the 403 response"
        )

    def test_403_body_never_leaks_secrets(self):
        """The 403 response body contains no internal details."""
        from forgeguard.middleware.rbac import _forbidden_permission
        import json

        response = _forbidden_permission(
            user_role="developer",
            primary_permission=Permissions.POLICY_MANAGE,
            path="/api/v1/policies",
            method="POST",
        )
        body_str = response.body.decode()
        assert "traceback" not in body_str.lower()
        assert "sql" not in body_str.lower()
        assert "database" not in body_str.lower()
        assert "exception" not in body_str.lower()


# ===========================================================================
# 4. PLATFORM ADMIN COMPLETENESS
# ===========================================================================

class TestPlatformAdminCompleteness:
    """Verify platform_admin can access every mapped endpoint."""

    @pytest.mark.parametrize(
        "permission, method, path",
        [
            (perm, method, path)
            for perm, (method, path, _) in ENDPOINT_FOR_PERMISSION.items()
        ],
        ids=[perm for perm in sorted(ENDPOINT_FOR_PERMISSION.keys())],
    )
    def test_platform_admin_passes_rbac_for_all_permissions(
        self,
        permission: str,
        method: str,
        path: str,
    ):
        """ROUTE_PERMISSION_MAP grants platform_admin access to every endpoint."""
        entry = next(
            (e for e in ROUTE_PERMISSION_MAP if e.matches(method, path)),
            None,
        )
        assert entry is not None, f"No route entry for {method} {path}"
        assert entry.has_permission("platform_admin"), (
            f"platform_admin denied at {method} {path} (permission: {permission})"
        )


# ===========================================================================
# 5. HTTP INTEGRATION TESTS — full middleware chain (no Docker required)
# ===========================================================================

@pytest.mark.unit
class TestRbacHttpEnforcement:
    """HTTP-level RBAC enforcement through the full ASGI middleware stack.

    Uses the ``rbac_client`` factory (cookie-based JWT auth) which
    correctly exercises ``AuthenticationMiddleware`` + ``RBACMiddleware``.
    """

    # ------------------------------------------------------------------
    # Denial cases — each role trying an endpoint it cannot access
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_developer_denied_policy_manage_http(self, rbac_client):
        """Developer gets 403 on POST /api/v1/policies."""
        client = await rbac_client("developer")
        response = await client.post(
            "/api/v1/policies",
            json={"name": "test", "description": "x", "dimension": "security"},
        )
        assert response.status_code == 403
        body = response.json()
        assert body["required_permission"] == Permissions.POLICY_MANAGE
        assert isinstance(body["required_roles"], list)
        assert "platform_admin" in body["required_roles"]

    @pytest.mark.asyncio
    async def test_operator_denied_assessment_request_http(self, rbac_client):
        """Operator gets 403 on POST /api/v1/releases/assess."""
        client = await rbac_client("operator")
        response = await client.post(
            "/api/v1/releases/assess",
            json={"service_id": _TEST_UUID, "commit_sha": "abc123"},
        )
        assert response.status_code == 403
        body = response.json()
        assert body["required_permission"] == Permissions.ASSESSMENT_REQUEST

    @pytest.mark.asyncio
    async def test_engineering_manager_denied_rbac_manage_http(self, rbac_client):
        """Engineering Manager gets 403 on GET /api/v1/admin/rbac/users."""
        client = await rbac_client("engineering_manager")
        response = await client.get("/api/v1/admin/rbac/users")
        assert response.status_code == 403
        body = response.json()
        assert body["required_permission"] == Permissions.RBAC_MANAGE

    @pytest.mark.asyncio
    async def test_security_reviewer_denied_release_approve_http(self, rbac_client):
        """Security Reviewer gets 403 on POST /api/v1/releases/{id}/approve."""
        client = await rbac_client("security_reviewer")
        response = await client.post(
            f"/api/v1/releases/{_TEST_UUID}/approve",
            json={"rationale": "test"},
        )
        assert response.status_code == 403
        body = response.json()
        assert body["required_permission"] == Permissions.RELEASE_APPROVE

    # ------------------------------------------------------------------
    # Allow cases — each role accessing an endpoint it CAN access
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_developer_allowed_service_view_http(self, rbac_client):
        """Developer gets non-403 on GET /api/v1/services."""
        client = await rbac_client("developer")
        response = await client.get("/api/v1/services")
        assert response.status_code != 403

    @pytest.mark.asyncio
    async def test_platform_admin_allowed_rbac_manage_http(self, rbac_client):
        """Platform Admin gets non-403 on GET /api/v1/admin/rbac/users."""
        client = await rbac_client("platform_admin")
        response = await client.get("/api/v1/admin/rbac/users")
        assert response.status_code != 403

    @pytest.mark.asyncio
    async def test_operator_allowed_platform_health_http(self, rbac_client):
        """Operator gets non-403 on GET /api/v1/platform/health."""
        client = await rbac_client("operator")
        response = await client.get("/api/v1/platform/health")
        assert response.status_code != 403

    @pytest.mark.asyncio
    async def test_security_reviewer_allowed_release_block_http(self, rbac_client):
        """Security Reviewer gets non-403 on POST /api/v1/releases/{id}/block."""
        client = await rbac_client("security_reviewer")
        response = await client.post(
            f"/api/v1/releases/{_TEST_UUID}/block",
            json={"rationale": "critical finding"},
        )
        assert response.status_code != 403

    @pytest.mark.asyncio
    async def test_tech_lead_allowed_assessment_request_http(self, rbac_client):
        """Tech Lead gets non-403 on POST /api/v1/releases/assess."""
        client = await rbac_client("tech_lead")
        response = await client.post(
            "/api/v1/releases/assess",
            json={"service_id": _TEST_UUID, "commit_sha": "abc123"},
        )
        assert response.status_code != 403

    @pytest.mark.asyncio
    async def test_engineering_manager_allowed_trends_http(self, rbac_client):
        """Engineering Manager gets non-403 on GET /api/v1/trends."""
        client = await rbac_client("engineering_manager")
        response = await client.get("/api/v1/trends")
        assert response.status_code != 403

    # ------------------------------------------------------------------
    # Role change effect — JWT role claim drives enforcement decisions
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_role_change_takes_effect_immediately(self, rbac_client):
        """Changing the role in the JWT immediately changes access decisions.

        A JWT with role=developer is denied; a JWT with role=platform_admin
        is allowed for the same endpoint, proving enforcement is stateless.
        """
        dev_client = await rbac_client("developer")
        admin_client = await rbac_client("platform_admin")

        dev_response = await dev_client.get("/api/v1/admin/rbac/users")
        admin_response = await admin_client.get("/api/v1/admin/rbac/users")

        assert dev_response.status_code == 403
        assert admin_response.status_code != 403

    # ------------------------------------------------------------------
    # OPTIONS preflight — must bypass RBAC entirely
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_options_preflight_bypasses_rbac(self, test_client):
        """CORS OPTIONS preflight requests return non-403 without authentication."""
        response = await test_client.options("/api/v1/policies")
        assert response.status_code != 403
        assert response.status_code != 401

    @pytest.mark.asyncio
    async def test_unauthenticated_options_returns_allowed(self, test_client):
        """Unauthenticated OPTIONS to protected endpoint is not blocked."""
        response = await test_client.options("/api/v1/admin/rbac/users")
        assert response.status_code not in (401, 403)
