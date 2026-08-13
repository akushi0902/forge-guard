"""Unit tests for AuthenticationMiddleware (WO-023).

All tests use a minimal FastAPI/ASGI app with the middleware registered —
no real database or external services required.

Scenarios covered:
  1. Public path (login) passes through without auth.
  2. Public path (register) passes through without auth.
  3. Public path (health) passes through without auth.
  4. Public path (docs) passes through without auth.
  5. OPTIONS preflight bypasses auth (CORS support).
  6. Missing cookie returns 401 with 'Authentication required'.
  7. Expired JWT returns 401 with 'Token has expired'.
  8. Tampered/invalid JWT returns 401 with 'Invalid authentication token'.
  9. Valid JWT sets request.state.user_id and user_role correctly.
 10. Protected route without cookie returns 401.
 11. WWW-Authenticate header present on 401 responses.
 12. PUBLIC_PATHS frozenset provides O(1) lookup (membership check).
"""

from __future__ import annotations

import uuid
from datetime import timedelta

import pytest
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from httpx import ASGITransport, AsyncClient

from forgeguard.middleware.authentication import (
    PUBLIC_PATHS,
    AuthenticationMiddleware,
)
from tests.fixtures.tokens import (
    DEMO_USER_ID,
    DEMO_USER_ROLE,
    TEST_JWT_SECRET,
    make_access_token,
    make_expired_access_token,
)


# ---------------------------------------------------------------------------
# Test app factory
# ---------------------------------------------------------------------------

def _make_app() -> FastAPI:
    """Minimal FastAPI app with AuthenticationMiddleware and one protected route."""
    app = FastAPI()
    app.add_middleware(AuthenticationMiddleware, jwt_secret=TEST_JWT_SECRET)

    @app.get("/protected")
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
        return {"token": "fake"}

    @app.post("/api/v1/auth/register")
    async def register() -> dict:
        return {"id": "fake"}

    return app


_APP = _make_app()


# ---------------------------------------------------------------------------
# Helper: set access_token cookie on client
# ---------------------------------------------------------------------------

def _valid_cookie() -> str:
    return make_access_token(user_id=DEMO_USER_ID, role=DEMO_USER_ROLE)


def _expired_cookie() -> str:
    return make_expired_access_token(user_id=DEMO_USER_ID, role=DEMO_USER_ROLE)


def _tampered_cookie() -> str:
    token = _valid_cookie()
    # Flip the last few chars to invalidate the signature.
    return token[:-4] + "XXXX"


# ---------------------------------------------------------------------------
# 1–5: Public path bypass
# ---------------------------------------------------------------------------

class TestPublicPathBypass:
    async def test_login_path_passes_without_cookie(self):
        async with AsyncClient(
            transport=ASGITransport(app=_APP), base_url="http://test"
        ) as client:
            resp = await client.post("/api/v1/auth/login")
        assert resp.status_code == 200

    async def test_register_path_passes_without_cookie(self):
        async with AsyncClient(
            transport=ASGITransport(app=_APP), base_url="http://test"
        ) as client:
            resp = await client.post("/api/v1/auth/register")
        assert resp.status_code == 200

    async def test_health_path_passes_without_cookie(self):
        async with AsyncClient(
            transport=ASGITransport(app=_APP), base_url="http://test"
        ) as client:
            resp = await client.get("/health")
        assert resp.status_code == 200

    async def test_options_preflight_bypasses_auth(self):
        async with AsyncClient(
            transport=ASGITransport(app=_APP), base_url="http://test"
        ) as client:
            resp = await client.options("/protected")
        # OPTIONS should not return 401 — 405 or 200 depending on FastAPI routing.
        assert resp.status_code != 401

    async def test_public_paths_frozenset_membership(self):
        assert "/api/v1/auth/login" in PUBLIC_PATHS
        assert "/api/v1/auth/register" in PUBLIC_PATHS
        assert "/api/v1/auth/refresh" in PUBLIC_PATHS
        assert "/health" in PUBLIC_PATHS
        assert "/api/v1/docs" in PUBLIC_PATHS
        assert "/api/v1/openapi.json" in PUBLIC_PATHS

    async def test_protected_route_not_in_public_paths(self):
        assert "/protected" not in PUBLIC_PATHS
        assert "/api/v1/services" not in PUBLIC_PATHS


# ---------------------------------------------------------------------------
# 6–8: 401 scenarios
# ---------------------------------------------------------------------------

class TestUnauthorizedCases:
    async def test_missing_cookie_returns_401(self):
        async with AsyncClient(
            transport=ASGITransport(app=_APP), base_url="http://test"
        ) as client:
            resp = await client.get("/protected")
        assert resp.status_code == 401
        assert resp.json()["detail"] == "Authentication required"

    async def test_expired_token_returns_401_with_token_has_expired(self):
        async with AsyncClient(
            transport=ASGITransport(app=_APP), base_url="http://test"
        ) as client:
            client.cookies.set("access_token", _expired_cookie())
            resp = await client.get("/protected")
        assert resp.status_code == 401
        assert resp.json()["detail"] == "Token has expired"

    async def test_tampered_token_returns_401_with_invalid_message(self):
        async with AsyncClient(
            transport=ASGITransport(app=_APP), base_url="http://test"
        ) as client:
            client.cookies.set("access_token", _tampered_cookie())
            resp = await client.get("/protected")
        assert resp.status_code == 401
        assert resp.json()["detail"] == "Invalid authentication token"

    async def test_malformed_token_returns_401(self):
        async with AsyncClient(
            transport=ASGITransport(app=_APP), base_url="http://test"
        ) as client:
            client.cookies.set("access_token", "not.a.jwt")
            resp = await client.get("/protected")
        assert resp.status_code == 401

    async def test_401_includes_www_authenticate_header(self):
        async with AsyncClient(
            transport=ASGITransport(app=_APP), base_url="http://test"
        ) as client:
            resp = await client.get("/protected")
        assert resp.status_code == 401
        assert "www-authenticate" in resp.headers or "WWW-Authenticate" in resp.headers


# ---------------------------------------------------------------------------
# 9: Valid token attaches user context to request.state
# ---------------------------------------------------------------------------

class TestValidTokenAttachesContext:
    async def test_valid_token_returns_200(self):
        async with AsyncClient(
            transport=ASGITransport(app=_APP), base_url="http://test"
        ) as client:
            client.cookies.set("access_token", _valid_cookie())
            resp = await client.get("/protected")
        assert resp.status_code == 200

    async def test_valid_token_sets_user_id_in_state(self):
        async with AsyncClient(
            transport=ASGITransport(app=_APP), base_url="http://test"
        ) as client:
            client.cookies.set("access_token", _valid_cookie())
            resp = await client.get("/protected")
        body = resp.json()
        assert body["user_id"] == str(DEMO_USER_ID)

    async def test_valid_token_sets_user_role_in_state(self):
        async with AsyncClient(
            transport=ASGITransport(app=_APP), base_url="http://test"
        ) as client:
            client.cookies.set("access_token", _valid_cookie())
            resp = await client.get("/protected")
        body = resp.json()
        assert body["user_role"] == DEMO_USER_ROLE

    async def test_different_roles_set_correctly(self):
        other_id = uuid.uuid4()
        token = make_access_token(user_id=other_id, role="developer")
        async with AsyncClient(
            transport=ASGITransport(app=_APP), base_url="http://test"
        ) as client:
            client.cookies.set("access_token", token)
            resp = await client.get("/protected")
        body = resp.json()
        assert body["user_id"] == str(other_id)
        assert body["user_role"] == "developer"

    async def test_wrong_jwt_secret_returns_401(self):
        wrong_secret_app = FastAPI()
        wrong_secret_app.add_middleware(
            AuthenticationMiddleware, jwt_secret="wrong-secret"
        )

        @wrong_secret_app.get("/protected")
        async def _protected() -> dict:
            return {"ok": True}

        token = make_access_token()  # signed with TEST_JWT_SECRET
        async with AsyncClient(
            transport=ASGITransport(app=wrong_secret_app), base_url="http://test"
        ) as client:
            client.cookies.set("access_token", token)
            resp = await client.get("/protected")
        assert resp.status_code == 401
        assert resp.json()["detail"] == "Invalid authentication token"
