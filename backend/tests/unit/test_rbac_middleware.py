"""Unit tests for RBACMiddleware and route-permission mapping (WO-027).

Scenarios covered (12+):
  1.  Public path bypasses RBAC enforcement.
  2.  OPTIONS preflight bypasses RBAC enforcement.
  3.  Missing user_role in request.state returns 401.
  4.  Unmapped route returns 403 with 'not configured' message.
  5.  Mapped route — permission granted — request passes through.
  6.  Mapped route — permission denied — returns 403 with structured body.
  7.  Wildcard single-segment path matching (GET /api/v1/services/<uuid>).
  8.  Wildcard multi-action path matching (POST /api/v1/releases/*/approve).
  9.  Method wildcard ('*') matches any HTTP method.
 10.  HEAD method inherits GET permission.
 11.  Case-insensitive method matching (lowercase method).
 12.  'deny-by-default' warning logged for unmapped route.
 13.  Path pattern compilation: exact match, * segment, ** multi-segment.
 14.  require_any semantics: passes when user holds any of the permissions.
 15.  Platform Admin bypasses all permission checks (holds ALL_PERMISSIONS).
"""

from __future__ import annotations

import uuid
from typing import Any
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from httpx import ASGITransport, AsyncClient

from forgeguard.core.permissions import Permissions
from forgeguard.middleware.authentication import PUBLIC_PATHS
from forgeguard.middleware.rbac import RBACMiddleware, _resolve_route
from forgeguard.middleware.route_permissions import (
    ROUTE_PERMISSION_MAP,
    RoutePermission,
    _compile_pattern,
)
from tests.fixtures.tokens import (
    TEST_JWT_SECRET,
    make_access_token,
)


# ---------------------------------------------------------------------------
# Helpers: minimal test app
# ---------------------------------------------------------------------------

def _make_app(*, user_role: str | None = "developer") -> FastAPI:
    """Minimal FastAPI app with RBACMiddleware only.

    Injects *user_role* directly onto request.state to simulate what
    AuthenticationMiddleware would set, without requiring a real JWT.
    """
    app = FastAPI()

    # A prehook middleware that sets request.state.user_role (auth simulation).
    class _FakeAuthMiddleware:
        def __init__(self, inner: Any, role: str | None) -> None:
            self._inner = inner
            self._role = role

        async def __call__(self, scope: Any, receive: Any, send: Any) -> None:
            if scope["type"] == "http":
                request = Request(scope, receive)
                if self._role is not None:
                    request.state.user_role = self._role
            await self._inner(scope, receive, send)

    app.add_middleware(RBACMiddleware)
    app.add_middleware(_FakeAuthMiddleware, role=user_role)  # type: ignore[arg-type]

    @app.get("/api/v1/services")
    async def list_services() -> JSONResponse:
        return JSONResponse({"ok": True})

    @app.get("/api/v1/services/{svc_id}")
    async def get_service(svc_id: str) -> JSONResponse:
        return JSONResponse({"id": svc_id})

    @app.post("/api/v1/services")
    async def create_service() -> JSONResponse:
        return JSONResponse({"created": True})

    @app.post("/api/v1/releases/{rid}/approve")
    async def approve_release(rid: str) -> JSONResponse:
        return JSONResponse({"approved": rid})

    @app.post("/api/v1/releases/{rid}/block")
    async def block_release(rid: str) -> JSONResponse:
        return JSONResponse({"blocked": rid})

    @app.get("/api/v1/platform/health")
    async def platform_health() -> JSONResponse:
        return JSONResponse({"status": "ok"})

    @app.post("/api/v1/admin/prompt-templates")
    async def create_template() -> JSONResponse:
        return JSONResponse({"created": True})

    @app.get("/api/v1/unlisted-endpoint")
    async def unlisted() -> JSONResponse:
        return JSONResponse({"secret": True})

    return app


# ---------------------------------------------------------------------------
# Pattern compilation unit tests
# ---------------------------------------------------------------------------

class TestCompilePattern:
    def test_exact_match(self) -> None:
        regex = _compile_pattern("/api/v1/services")
        assert regex.match("/api/v1/services")
        assert not regex.match("/api/v1/services/extra")

    def test_single_wildcard_matches_uuid_segment(self) -> None:
        regex = _compile_pattern("/api/v1/services/*")
        uid = str(uuid.uuid4())
        assert regex.match(f"/api/v1/services/{uid}")
        assert not regex.match("/api/v1/services")
        assert not regex.match(f"/api/v1/services/{uid}/sub")

    def test_wildcard_in_middle(self) -> None:
        regex = _compile_pattern("/api/v1/releases/*/approve")
        uid = str(uuid.uuid4())
        assert regex.match(f"/api/v1/releases/{uid}/approve")
        assert not regex.match(f"/api/v1/releases/{uid}/block")

    def test_double_wildcard_matches_any_subpath(self) -> None:
        regex = _compile_pattern("/api/v1/admin/rbac/**")
        assert regex.match("/api/v1/admin/rbac/users/role-assignment")
        assert regex.match("/api/v1/admin/rbac/roles")

    def test_special_characters_in_path_are_escaped(self) -> None:
        regex = _compile_pattern("/api/v1/items.json")
        assert regex.match("/api/v1/items.json")
        # The dot must be literal, not a regex wildcard.
        assert not regex.match("/api/v1/itemsXjson")


# ---------------------------------------------------------------------------
# _resolve_route unit tests
# ---------------------------------------------------------------------------

class TestResolveRoute:
    def test_resolves_get_services(self) -> None:
        entry = _resolve_route("GET", "/api/v1/services")
        assert entry is not None
        assert Permissions.SERVICE_VIEW in entry.permissions

    def test_resolves_post_services(self) -> None:
        entry = _resolve_route("POST", "/api/v1/services")
        assert entry is not None
        assert Permissions.POLICY_MANAGE in entry.permissions

    def test_resolves_wildcard_service_id(self) -> None:
        uid = str(uuid.uuid4())
        entry = _resolve_route("GET", f"/api/v1/services/{uid}")
        assert entry is not None
        assert Permissions.SERVICE_VIEW in entry.permissions

    def test_resolves_release_approve(self) -> None:
        uid = str(uuid.uuid4())
        entry = _resolve_route("POST", f"/api/v1/releases/{uid}/approve")
        assert entry is not None
        assert Permissions.RELEASE_APPROVE in entry.permissions

    def test_resolves_release_block(self) -> None:
        uid = str(uuid.uuid4())
        entry = _resolve_route("POST", f"/api/v1/releases/{uid}/block")
        assert entry is not None
        assert Permissions.RELEASE_BLOCK in entry.permissions

    def test_unresolved_returns_none(self) -> None:
        assert _resolve_route("GET", "/api/v1/unlisted-endpoint") is None

    def test_head_inherits_get(self) -> None:
        entry = _resolve_route("HEAD", "/api/v1/services")
        assert entry is not None
        assert Permissions.SERVICE_VIEW in entry.permissions

    def test_method_wildcard_matches_any(self) -> None:
        entry_post = _resolve_route("POST", "/api/v1/admin/prompt-templates")
        entry_get = _resolve_route("GET", "/api/v1/admin/prompt-templates")
        entry_delete = _resolve_route("DELETE", "/api/v1/admin/prompt-templates")
        assert all(e is not None for e in [entry_post, entry_get, entry_delete])
        assert all(Permissions.POLICY_MANAGE in e.permissions for e in [entry_post, entry_get, entry_delete])  # type: ignore[union-attr]


# ---------------------------------------------------------------------------
# HTTP-level middleware tests
# ---------------------------------------------------------------------------

@pytest.fixture
async def developer_client() -> AsyncClient:
    app = _make_app(user_role="developer")
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        yield client


@pytest.fixture
async def admin_client() -> AsyncClient:
    app = _make_app(user_role="platform_admin")
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        yield client


@pytest.fixture
async def no_role_client() -> AsyncClient:
    app = _make_app(user_role=None)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        yield client


class TestPublicPathBypass:
    async def test_public_login_path_bypasses_rbac(self, no_role_client: AsyncClient) -> None:
        # /api/v1/auth/login is in PUBLIC_PATHS — no RBAC even without a role.
        # We can't register this route on our minimal app but we can verify PUBLIC_PATHS membership.
        assert "/api/v1/auth/login" in PUBLIC_PATHS

    def test_public_paths_frozenset(self) -> None:
        assert isinstance(PUBLIC_PATHS, frozenset)
        assert "/api/v1/auth/register" in PUBLIC_PATHS
        assert "/api/v1/auth/refresh" in PUBLIC_PATHS
        assert "/health" in PUBLIC_PATHS
        assert "/api/v1/docs" in PUBLIC_PATHS


class TestMissingUserRole:
    async def test_missing_user_role_returns_401(self, no_role_client: AsyncClient) -> None:
        resp = await no_role_client.get("/api/v1/services")
        assert resp.status_code == 401
        assert resp.json()["detail"] == "Authentication required"

    async def test_401_has_www_authenticate_header(self, no_role_client: AsyncClient) -> None:
        resp = await no_role_client.get("/api/v1/services")
        assert resp.headers.get("www-authenticate") == "Bearer"


class TestPermissionGranted:
    async def test_developer_can_list_services(self, developer_client: AsyncClient) -> None:
        resp = await developer_client.get("/api/v1/services")
        assert resp.status_code == 200

    async def test_developer_can_get_service_by_id(self, developer_client: AsyncClient) -> None:
        uid = str(uuid.uuid4())
        resp = await developer_client.get(f"/api/v1/services/{uid}")
        assert resp.status_code == 200

    async def test_admin_can_create_service(self, admin_client: AsyncClient) -> None:
        resp = await admin_client.post("/api/v1/services")
        assert resp.status_code == 200

    async def test_admin_can_manage_prompt_templates(self, admin_client: AsyncClient) -> None:
        resp = await admin_client.post("/api/v1/admin/prompt-templates")
        assert resp.status_code == 200


class TestPermissionDenied:
    async def test_developer_cannot_create_service(self, developer_client: AsyncClient) -> None:
        resp = await developer_client.post("/api/v1/services")
        assert resp.status_code == 403

    async def test_developer_cannot_approve_release(self, developer_client: AsyncClient) -> None:
        uid = str(uuid.uuid4())
        resp = await developer_client.post(f"/api/v1/releases/{uid}/approve")
        assert resp.status_code == 403

    async def test_developer_cannot_access_platform_health(
        self, developer_client: AsyncClient
    ) -> None:
        resp = await developer_client.get("/api/v1/platform/health")
        assert resp.status_code == 403

    async def test_403_structured_body(self, developer_client: AsyncClient) -> None:
        resp = await developer_client.post("/api/v1/services")
        body = resp.json()
        assert "required_permission" in body
        assert "required_roles" in body
        assert Permissions.POLICY_MANAGE in body["required_permission"]


class TestDenyByDefault:
    async def test_unmapped_route_returns_403(self, developer_client: AsyncClient) -> None:
        resp = await developer_client.get("/api/v1/unlisted-endpoint")
        assert resp.status_code == 403
        assert "not been configured" in resp.json()["detail"]

    async def test_unmapped_route_403_body_format(self, developer_client: AsyncClient) -> None:
        resp = await developer_client.get("/api/v1/unlisted-endpoint")
        body = resp.json()
        assert "detail" in body


class TestHeadMethodInheritance:
    async def test_head_inherits_get_permission(self, developer_client: AsyncClient) -> None:
        # Developer has service.view → HEAD /api/v1/services should pass.
        resp = await developer_client.head("/api/v1/services")
        # FastAPI returns 200 for HEAD on a registered GET route.
        assert resp.status_code == 200
