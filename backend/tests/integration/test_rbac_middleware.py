"""Integration tests for RBACMiddleware end-to-end (WO-027).

Uses a minimal FastAPI application with the full Auth + RBAC middleware stack
to verify end-to-end authorization behaviour.

Scenarios:
  1. Developer accessing a service.view endpoint → 200.
  2. Developer accessing a policy.manage endpoint → 403.
  3. Platform Admin accessing any endpoint → 200.
  4. Request to unmapped endpoint → 403 with warning-log.
  5. 403 response body matches the structured format from WO-026.
  6. Security Reviewer can block a release.
  7. Security Reviewer cannot approve a release.
  8. Operator can access platform health.
  9. Engineering Manager can view services (has trends.view + service.view).
 10. Tech Lead can approve a release.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from httpx import ASGITransport, AsyncClient

from forgeguard.middleware.authentication import AuthenticationMiddleware
from forgeguard.middleware.rbac import RBACMiddleware
from tests.fixtures.tokens import TEST_JWT_SECRET, make_access_token


# ---------------------------------------------------------------------------
# Full-stack test app factory
# ---------------------------------------------------------------------------

def _make_full_app() -> FastAPI:
    """Minimal app with AuthenticationMiddleware + RBACMiddleware stacked correctly.

    AuthenticationMiddleware (pos 5) is registered AFTER RBACMiddleware (pos 6)
    in code (innermost-first registration order), matching production main.py.
    """
    app = FastAPI()

    # Routes under test
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

    @app.get("/api/v1/admin/prompt-templates")
    async def list_templates() -> JSONResponse:
        return JSONResponse({"items": []})

    @app.get("/api/v1/trends")
    async def trends() -> JSONResponse:
        return JSONResponse({"trends": []})

    @app.get("/api/v1/unlisted-secret")
    async def unlisted() -> JSONResponse:
        return JSONResponse({"secret": True})

    # Middleware stack — innermost registered first (mirrors main.py).
    app.add_middleware(RBACMiddleware)               # pos 6 — checks permissions
    app.add_middleware(                              # pos 5 — sets user_role
        AuthenticationMiddleware,
        jwt_secret=TEST_JWT_SECRET,
    )

    return app


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_APP = _make_full_app()


def _client_for_role(role: str) -> AsyncClient:
    """Return an AsyncClient pre-configured with a valid JWT for *role*."""
    token = make_access_token(role=role)
    return AsyncClient(
        transport=ASGITransport(app=_APP),
        base_url="http://testserver",
        cookies={"access_token": token},
    )


@pytest.fixture
async def developer() -> AsyncClient:
    async with _client_for_role("developer") as client:
        yield client


@pytest.fixture
async def tech_lead() -> AsyncClient:
    async with _client_for_role("tech_lead") as client:
        yield client


@pytest.fixture
async def security_reviewer() -> AsyncClient:
    async with _client_for_role("security_reviewer") as client:
        yield client


@pytest.fixture
async def platform_admin() -> AsyncClient:
    async with _client_for_role("platform_admin") as client:
        yield client


@pytest.fixture
async def engineering_manager() -> AsyncClient:
    async with _client_for_role("engineering_manager") as client:
        yield client


@pytest.fixture
async def operator() -> AsyncClient:
    async with _client_for_role("operator") as client:
        yield client


@pytest.fixture
async def unauthenticated() -> AsyncClient:
    async with AsyncClient(
        transport=ASGITransport(app=_APP),
        base_url="http://testserver",
    ) as client:
        yield client


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestDeveloperRole:
    async def test_can_list_services(self, developer: AsyncClient) -> None:
        resp = await developer.get("/api/v1/services")
        assert resp.status_code == 200

    async def test_can_view_service_by_id(self, developer: AsyncClient) -> None:
        uid = str(uuid.uuid4())
        resp = await developer.get(f"/api/v1/services/{uid}")
        assert resp.status_code == 200

    async def test_cannot_create_service(self, developer: AsyncClient) -> None:
        resp = await developer.post("/api/v1/services")
        assert resp.status_code == 403

    async def test_cannot_approve_release(self, developer: AsyncClient) -> None:
        uid = str(uuid.uuid4())
        resp = await developer.post(f"/api/v1/releases/{uid}/approve")
        assert resp.status_code == 403

    async def test_cannot_access_platform_health(self, developer: AsyncClient) -> None:
        resp = await developer.get("/api/v1/platform/health")
        assert resp.status_code == 403

    async def test_unmapped_endpoint_denied(self, developer: AsyncClient) -> None:
        resp = await developer.get("/api/v1/unlisted-secret")
        assert resp.status_code == 403
        assert "not been configured" in resp.json()["detail"]


class TestPlatformAdminRole:
    async def test_can_create_service(self, platform_admin: AsyncClient) -> None:
        resp = await platform_admin.post("/api/v1/services")
        assert resp.status_code == 200

    async def test_can_list_templates(self, platform_admin: AsyncClient) -> None:
        resp = await platform_admin.get("/api/v1/admin/prompt-templates")
        assert resp.status_code == 200

    async def test_can_approve_release(self, platform_admin: AsyncClient) -> None:
        uid = str(uuid.uuid4())
        resp = await platform_admin.post(f"/api/v1/releases/{uid}/approve")
        assert resp.status_code == 200

    async def test_can_access_platform_health(self, platform_admin: AsyncClient) -> None:
        resp = await platform_admin.get("/api/v1/platform/health")
        assert resp.status_code == 200


class TestSecurityReviewerRole:
    async def test_can_view_services(self, security_reviewer: AsyncClient) -> None:
        resp = await security_reviewer.get("/api/v1/services")
        assert resp.status_code == 200

    async def test_can_block_release(self, security_reviewer: AsyncClient) -> None:
        uid = str(uuid.uuid4())
        resp = await security_reviewer.post(f"/api/v1/releases/{uid}/block")
        assert resp.status_code == 200

    async def test_cannot_approve_release(self, security_reviewer: AsyncClient) -> None:
        uid = str(uuid.uuid4())
        resp = await security_reviewer.post(f"/api/v1/releases/{uid}/approve")
        assert resp.status_code == 403


class TestTechLeadRole:
    async def test_can_approve_release(self, tech_lead: AsyncClient) -> None:
        uid = str(uuid.uuid4())
        resp = await tech_lead.post(f"/api/v1/releases/{uid}/approve")
        assert resp.status_code == 200

    async def test_can_view_trends(self, tech_lead: AsyncClient) -> None:
        resp = await tech_lead.get("/api/v1/trends")
        assert resp.status_code == 200


class TestOperatorRole:
    async def test_can_access_platform_health(self, operator: AsyncClient) -> None:
        resp = await operator.get("/api/v1/platform/health")
        assert resp.status_code == 200

    async def test_can_view_services(self, operator: AsyncClient) -> None:
        resp = await operator.get("/api/v1/services")
        assert resp.status_code == 200


class TestEngineeringManagerRole:
    async def test_can_view_services(self, engineering_manager: AsyncClient) -> None:
        resp = await engineering_manager.get("/api/v1/services")
        assert resp.status_code == 200

    async def test_cannot_create_service(self, engineering_manager: AsyncClient) -> None:
        resp = await engineering_manager.post("/api/v1/services")
        assert resp.status_code == 403


class TestUnauthenticated:
    async def test_protected_route_returns_401(self, unauthenticated: AsyncClient) -> None:
        resp = await unauthenticated.get("/api/v1/services")
        assert resp.status_code == 401


class TestStructuredErrorBody:
    async def test_permission_denied_body_has_required_fields(
        self, developer: AsyncClient
    ) -> None:
        resp = await developer.post("/api/v1/services")
        body = resp.json()
        assert "detail" in body
        assert "required_permission" in body
        assert "required_roles" in body

    async def test_required_roles_is_list(self, developer: AsyncClient) -> None:
        resp = await developer.post("/api/v1/services")
        assert isinstance(resp.json()["required_roles"], list)

    async def test_unmapped_403_body_has_detail(self, developer: AsyncClient) -> None:
        resp = await developer.get("/api/v1/unlisted-secret")
        assert "detail" in resp.json()
