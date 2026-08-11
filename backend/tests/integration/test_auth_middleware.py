"""Integration tests for AuthenticationMiddleware end-to-end (WO-023).

Creates a minimal FastAPI test app with the full middleware registered (just
the authentication middleware, not the entire pipeline) and verifies behaviour
against a protected and a public endpoint.

Scenarios:
  1. Protected route without any cookie → 401 "Authentication required".
  2. Protected route with valid cookie → 200 with user context echoed.
  3. Protected route with expired token → 401 "Token has expired".
  4. Protected route with tampered token → 401 "Invalid authentication token".
  5. Public path (login) without cookie → not 401.
  6. Public path (health) without cookie → not 401.
  7. OPTIONS preflight to protected route → not 401.
  8. Password change endpoint: requires valid cookie (401 without).
  9. Valid token sets correct user_id and user_role in response.
 10. 401 responses carry WWW-Authenticate: Bearer header.

No real database is used — the /change-password test exercises the route
binding (401 without auth) rather than the full service logic.
"""

from __future__ import annotations

import uuid
from datetime import timedelta

import pytest
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from httpx import ASGITransport, AsyncClient

from forgeguard.middleware.authentication import AuthenticationMiddleware
from tests.fixtures.tokens import (
    DEMO_USER_ID,
    DEMO_USER_ROLE,
    TEST_JWT_SECRET,
    make_access_token,
    make_expired_access_token,
)


# ---------------------------------------------------------------------------
# Integration test app
# ---------------------------------------------------------------------------

def _make_integration_app() -> FastAPI:
    """Full FastAPI app with only the authentication middleware registered."""
    app = FastAPI()
    app.add_middleware(AuthenticationMiddleware, jwt_secret=TEST_JWT_SECRET)

    @app.get("/api/v1/services")
    async def protected(request: Request) -> JSONResponse:
        return JSONResponse({
            "user_id": getattr(request.state, "user_id", None),
            "user_role": getattr(request.state, "user_role", None),
        })

    @app.get("/health")
    async def health() -> dict:
        return {"status": "ok"}

    @app.post("/api/v1/auth/login")
    async def login() -> dict:
        return {"message": "login ok"}

    @app.post("/api/v1/auth/change-password")
    async def change_password(request: Request) -> dict:
        return {"user_id": getattr(request.state, "user_id", None)}

    return app


_INT_APP = _make_integration_app()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _valid_token(
    user_id: uuid.UUID = DEMO_USER_ID,
    role: str = DEMO_USER_ROLE,
) -> str:
    return make_access_token(user_id=user_id, role=role)


def _expired_token() -> str:
    return make_expired_access_token()


def _tampered_token() -> str:
    t = _valid_token()
    return t[:-4] + "ZZZZ"


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestProtectedRouteWithoutToken:
    async def test_returns_401(self):
        async with AsyncClient(
            transport=ASGITransport(app=_INT_APP), base_url="http://test"
        ) as client:
            resp = await client.get("/api/v1/services")
        assert resp.status_code == 401

    async def test_detail_is_authentication_required(self):
        async with AsyncClient(
            transport=ASGITransport(app=_INT_APP), base_url="http://test"
        ) as client:
            resp = await client.get("/api/v1/services")
        assert resp.json()["detail"] == "Authentication required"

    async def test_www_authenticate_header_present(self):
        async with AsyncClient(
            transport=ASGITransport(app=_INT_APP), base_url="http://test"
        ) as client:
            resp = await client.get("/api/v1/services")
        headers_lower = {k.lower(): v for k, v in resp.headers.items()}
        assert "www-authenticate" in headers_lower


class TestProtectedRouteWithValidToken:
    async def test_returns_200(self):
        async with AsyncClient(
            transport=ASGITransport(app=_INT_APP), base_url="http://test"
        ) as client:
            client.cookies.set("access_token", _valid_token())
            resp = await client.get("/api/v1/services")
        assert resp.status_code == 200

    async def test_user_id_in_response(self):
        async with AsyncClient(
            transport=ASGITransport(app=_INT_APP), base_url="http://test"
        ) as client:
            client.cookies.set("access_token", _valid_token())
            resp = await client.get("/api/v1/services")
        assert resp.json()["user_id"] == str(DEMO_USER_ID)

    async def test_user_role_in_response(self):
        async with AsyncClient(
            transport=ASGITransport(app=_INT_APP), base_url="http://test"
        ) as client:
            client.cookies.set("access_token", _valid_token())
            resp = await client.get("/api/v1/services")
        assert resp.json()["user_role"] == DEMO_USER_ROLE

    async def test_different_user_identity_propagated(self):
        other_id = uuid.uuid4()
        token = make_access_token(user_id=other_id, role="tech_lead")
        async with AsyncClient(
            transport=ASGITransport(app=_INT_APP), base_url="http://test"
        ) as client:
            client.cookies.set("access_token", token)
            resp = await client.get("/api/v1/services")
        body = resp.json()
        assert body["user_id"] == str(other_id)
        assert body["user_role"] == "tech_lead"


class TestExpiredToken:
    async def test_expired_token_returns_401(self):
        async with AsyncClient(
            transport=ASGITransport(app=_INT_APP), base_url="http://test"
        ) as client:
            client.cookies.set("access_token", _expired_token())
            resp = await client.get("/api/v1/services")
        assert resp.status_code == 401

    async def test_expired_token_detail_message(self):
        async with AsyncClient(
            transport=ASGITransport(app=_INT_APP), base_url="http://test"
        ) as client:
            client.cookies.set("access_token", _expired_token())
            resp = await client.get("/api/v1/services")
        assert resp.json()["detail"] == "Token has expired"


class TestTamperedToken:
    async def test_tampered_token_returns_401(self):
        async with AsyncClient(
            transport=ASGITransport(app=_INT_APP), base_url="http://test"
        ) as client:
            client.cookies.set("access_token", _tampered_token())
            resp = await client.get("/api/v1/services")
        assert resp.status_code == 401

    async def test_tampered_token_detail_message(self):
        async with AsyncClient(
            transport=ASGITransport(app=_INT_APP), base_url="http://test"
        ) as client:
            client.cookies.set("access_token", _tampered_token())
            resp = await client.get("/api/v1/services")
        assert resp.json()["detail"] == "Invalid authentication token"


class TestPublicPathsBypass:
    async def test_health_bypass(self):
        async with AsyncClient(
            transport=ASGITransport(app=_INT_APP), base_url="http://test"
        ) as client:
            resp = await client.get("/health")
        assert resp.status_code != 401

    async def test_login_bypass(self):
        async with AsyncClient(
            transport=ASGITransport(app=_INT_APP), base_url="http://test"
        ) as client:
            resp = await client.post("/api/v1/auth/login")
        assert resp.status_code != 401

    async def test_options_bypass(self):
        async with AsyncClient(
            transport=ASGITransport(app=_INT_APP), base_url="http://test"
        ) as client:
            resp = await client.options("/api/v1/services")
        assert resp.status_code != 401


class TestChangePasswordEndpointAuth:
    async def test_change_password_without_cookie_returns_401(self):
        async with AsyncClient(
            transport=ASGITransport(app=_INT_APP), base_url="http://test"
        ) as client:
            resp = await client.post(
                "/api/v1/auth/change-password",
                json={"current_password": "old", "new_password": "new"},
            )
        assert resp.status_code == 401

    async def test_change_password_with_valid_cookie_not_401(self):
        async with AsyncClient(
            transport=ASGITransport(app=_INT_APP), base_url="http://test"
        ) as client:
            client.cookies.set("access_token", _valid_token())
            resp = await client.post(
                "/api/v1/auth/change-password",
                json={"current_password": "old", "new_password": "new"},
            )
        # The real service would validate, but this test app just echoes user_id.
        assert resp.status_code != 401
