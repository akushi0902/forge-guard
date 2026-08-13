"""Integration tests for RBAC permission enforcement (WO-026).

Uses test routes decorated with require_permission/require_any_permission
and verifies correct 200/403 responses for each role.
"""

from __future__ import annotations

import pytest
from fastapi import Depends, FastAPI
from httpx import ASGITransport, AsyncClient

from forgeguard.api.dependencies.rbac import require_any_permission, require_permission
from forgeguard.core.error_handlers import register_error_handlers
from forgeguard.core.permissions import Permissions, UserRole


# ---------------------------------------------------------------------------
# Test app factory
# ---------------------------------------------------------------------------

def _make_test_app() -> FastAPI:
    """FastAPI app with test routes guarded by RBAC dependencies."""
    app = FastAPI()
    register_error_handlers(app)

    @app.get("/test/service-view", dependencies=[Depends(require_permission(Permissions.SERVICE_VIEW))])
    async def service_view_endpoint():
        return {"ok": True}

    @app.get("/test/policy-manage", dependencies=[Depends(require_permission(Permissions.POLICY_MANAGE))])
    async def policy_manage_endpoint():
        return {"ok": True}

    @app.get("/test/trends-or-release", dependencies=[
        Depends(require_any_permission([Permissions.TRENDS_VIEW, Permissions.RELEASE_APPROVE]))
    ])
    async def trends_or_release_endpoint():
        return {"ok": True}

    @app.get("/test/release-block", dependencies=[Depends(require_permission(Permissions.RELEASE_BLOCK))])
    async def release_block_endpoint():
        return {"ok": True}

    @app.get("/test/health-monitor", dependencies=[Depends(require_permission(Permissions.HEALTH_MONITOR))])
    async def health_monitor_endpoint():
        return {"ok": True}

    @app.get("/test/rbac-manage", dependencies=[Depends(require_permission(Permissions.RBAC_MANAGE))])
    async def rbac_manage_endpoint():
        return {"ok": True}

    return app


def _set_role(role: str) -> dict:
    return {"X-Test-Role": role}


_TEST_APP: FastAPI | None = None


def _get_app() -> FastAPI:
    global _TEST_APP
    if _TEST_APP is None:
        _TEST_APP = _make_test_app()
        # Inject user_role from X-Test-Role header via middleware
        from starlette.middleware.base import BaseHTTPMiddleware  # noqa: PLC0415

        class RoleInjectorMiddleware(BaseHTTPMiddleware):
            async def dispatch(self, request, call_next):
                role = request.headers.get("X-Test-Role", "")
                request.state.user_role = role
                return await call_next(request)

        _TEST_APP.add_middleware(RoleInjectorMiddleware)
    return _TEST_APP


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _get(path: str, role: str) -> int:
    app = _get_app()
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
        headers={"X-Test-Role": role},
    ) as client:
        resp = await client.get(path)
    return resp.status_code


# ---------------------------------------------------------------------------
# service.view — all roles can access
# ---------------------------------------------------------------------------

class TestServiceViewAllRoles:
    @pytest.mark.parametrize("role", [r.value for r in UserRole])
    async def test_all_roles_200(self, role: str):
        status = await _get("/test/service-view", role)
        assert status == 200, f"role={role} expected 200 got {status}"

    async def test_unknown_role_403(self):
        status = await _get("/test/service-view", "hacker")
        assert status == 403

    async def test_empty_role_403(self):
        status = await _get("/test/service-view", "")
        assert status == 403


# ---------------------------------------------------------------------------
# policy.manage — platform_admin only
# ---------------------------------------------------------------------------

class TestPolicyManage:
    async def test_platform_admin_200(self):
        assert await _get("/test/policy-manage", "platform_admin") == 200

    @pytest.mark.parametrize("role", [
        "developer", "tech_lead", "security_reviewer",
        "engineering_manager", "operator",
    ])
    async def test_non_admin_roles_403(self, role: str):
        status = await _get("/test/policy-manage", role)
        assert status == 403, f"role={role} should get 403"


# ---------------------------------------------------------------------------
# release.block — security_reviewer + platform_admin
# ---------------------------------------------------------------------------

class TestReleaseBlock:
    @pytest.mark.parametrize("role", ["security_reviewer", "platform_admin"])
    async def test_authorized_roles_200(self, role: str):
        assert await _get("/test/release-block", role) == 200

    @pytest.mark.parametrize("role", ["developer", "tech_lead", "engineering_manager", "operator"])
    async def test_unauthorized_roles_403(self, role: str):
        assert await _get("/test/release-block", role) == 403


# ---------------------------------------------------------------------------
# health.monitor — operator + platform_admin
# ---------------------------------------------------------------------------

class TestHealthMonitor:
    @pytest.mark.parametrize("role", ["operator", "platform_admin"])
    async def test_authorized_roles_200(self, role: str):
        assert await _get("/test/health-monitor", role) == 200

    @pytest.mark.parametrize("role", [
        "developer", "tech_lead", "security_reviewer", "engineering_manager",
    ])
    async def test_unauthorized_roles_403(self, role: str):
        assert await _get("/test/health-monitor", role) == 403


# ---------------------------------------------------------------------------
# rbac.manage — platform_admin only
# ---------------------------------------------------------------------------

class TestRbacManage:
    async def test_platform_admin_200(self):
        assert await _get("/test/rbac-manage", "platform_admin") == 200

    @pytest.mark.parametrize("role", [
        "developer", "tech_lead", "security_reviewer",
        "engineering_manager", "operator",
    ])
    async def test_non_admin_403(self, role: str):
        assert await _get("/test/rbac-manage", role) == 403


# ---------------------------------------------------------------------------
# require_any_permission — trends.view OR release.approve
# ---------------------------------------------------------------------------

class TestRequireAnyPermission:
    @pytest.mark.parametrize("role", ["tech_lead", "engineering_manager", "platform_admin"])
    async def test_roles_with_any_permission_200(self, role: str):
        assert await _get("/test/trends-or-release", role) == 200

    @pytest.mark.parametrize("role", ["developer", "security_reviewer", "operator"])
    async def test_roles_without_either_permission_403(self, role: str):
        assert await _get("/test/trends-or-release", role) == 403


# ---------------------------------------------------------------------------
# 403 response body structure
# ---------------------------------------------------------------------------

class TestForbiddenResponseStructure:
    async def test_403_body_has_required_permission(self):
        app = _get_app()
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://testserver",
            headers={"X-Test-Role": "developer"},
        ) as client:
            resp = await client.get("/test/policy-manage")
        assert resp.status_code == 403
        body = resp.json()
        assert body.get("required_permission") == Permissions.POLICY_MANAGE

    async def test_403_body_has_required_roles(self):
        app = _get_app()
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://testserver",
            headers={"X-Test-Role": "developer"},
        ) as client:
            resp = await client.get("/test/policy-manage")
        body = resp.json()
        assert "required_roles" in body
        assert isinstance(body["required_roles"], list)
        assert "platform_admin" in body["required_roles"]

    async def test_403_body_has_error_field(self):
        app = _get_app()
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://testserver",
            headers={"X-Test-Role": "developer"},
        ) as client:
            resp = await client.get("/test/rbac-manage")
        body = resp.json()
        assert body.get("error") == "forbidden"
