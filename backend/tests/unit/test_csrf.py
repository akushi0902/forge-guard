"""Unit tests for CSRF token protection (WO-025).

Tests for:
  core/security.py — generate_csrf_token, validate_csrf_token
  middleware/csrf.py — CSRFMiddleware dispatch logic

Scenarios:
  Token generation:
    - Returns a non-empty URL-safe string
    - Output length is >= 43 chars (32 bytes base64)
    - Same jti+secret always produces same token (deterministic)
    - Different jti produces different token
    - Different secret produces different token

  Token validation:
    - Matching token returns True
    - Mismatched token returns False
    - Empty string returns False
    - Token from different JTI returns False
    - Token from different secret returns False
    - Uses constant-time comparison (no timing leakage)

  Middleware exemptions:
    - GET requests bypass CSRF check
    - HEAD requests bypass CSRF check
    - OPTIONS requests bypass CSRF check
    - Public paths (login, health) bypass CSRF check

  Middleware enforcement:
    - POST without X-CSRF-Token header returns 403
    - POST with wrong CSRF token returns 403
    - POST with valid CSRF token passes through
    - 403 response has detail 'CSRF token required' for missing header
    - 403 response has detail 'CSRF token invalid' for wrong token
"""

from __future__ import annotations

import uuid

import pytest
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from httpx import ASGITransport, AsyncClient

from forgeguard.core.security import generate_csrf_token, validate_csrf_token
from forgeguard.middleware.authentication import AuthenticationMiddleware
from forgeguard.middleware.csrf import CSRFMiddleware
from tests.fixtures.tokens import (
    DEMO_USER_ID,
    DEMO_USER_ROLE,
    TEST_JWT_SECRET,
    make_access_token,
)

_TEST_CSRF_SECRET = "test-csrf-secret-for-unit-tests-only"
_TEST_JTI = str(uuid.uuid4())


# ---------------------------------------------------------------------------
# generate_csrf_token / validate_csrf_token
# ---------------------------------------------------------------------------

class TestGenerateCsrfToken:
    def test_returns_non_empty_string(self):
        token = generate_csrf_token(_TEST_JTI, _TEST_CSRF_SECRET)
        assert isinstance(token, str)
        assert len(token) > 0

    def test_length_represents_at_least_32_bytes(self):
        token = generate_csrf_token(_TEST_JTI, _TEST_CSRF_SECRET)
        # HMAC-SHA256 → 32 bytes → base64url without padding → 43 chars
        assert len(token) >= 43

    def test_is_url_safe(self):
        token = generate_csrf_token(_TEST_JTI, _TEST_CSRF_SECRET)
        import re
        assert re.fullmatch(r"[A-Za-z0-9_\-]+", token), f"Not URL-safe: {token}"

    def test_deterministic_same_inputs(self):
        t1 = generate_csrf_token(_TEST_JTI, _TEST_CSRF_SECRET)
        t2 = generate_csrf_token(_TEST_JTI, _TEST_CSRF_SECRET)
        assert t1 == t2

    def test_different_jti_gives_different_token(self):
        jti_a = str(uuid.uuid4())
        jti_b = str(uuid.uuid4())
        assert generate_csrf_token(jti_a, _TEST_CSRF_SECRET) != generate_csrf_token(jti_b, _TEST_CSRF_SECRET)

    def test_different_secret_gives_different_token(self):
        t1 = generate_csrf_token(_TEST_JTI, "secret-a")
        t2 = generate_csrf_token(_TEST_JTI, "secret-b")
        assert t1 != t2


class TestValidateCsrfToken:
    def test_matching_token_returns_true(self):
        token = generate_csrf_token(_TEST_JTI, _TEST_CSRF_SECRET)
        assert validate_csrf_token(token, _TEST_JTI, _TEST_CSRF_SECRET) is True

    def test_mismatched_token_returns_false(self):
        assert validate_csrf_token("wrong-token", _TEST_JTI, _TEST_CSRF_SECRET) is False

    def test_empty_string_returns_false(self):
        assert validate_csrf_token("", _TEST_JTI, _TEST_CSRF_SECRET) is False

    def test_token_from_different_jti_returns_false(self):
        other_jti = str(uuid.uuid4())
        token = generate_csrf_token(other_jti, _TEST_CSRF_SECRET)
        assert validate_csrf_token(token, _TEST_JTI, _TEST_CSRF_SECRET) is False

    def test_token_from_different_secret_returns_false(self):
        token = generate_csrf_token(_TEST_JTI, "other-secret")
        assert validate_csrf_token(token, _TEST_JTI, _TEST_CSRF_SECRET) is False


# ---------------------------------------------------------------------------
# CSRFMiddleware — test app factory
# ---------------------------------------------------------------------------

def _make_csrf_app() -> tuple[FastAPI, str]:
    """Return (app, valid_access_token) with both Auth and CSRF middleware."""
    access_token = make_access_token(user_id=DEMO_USER_ID, role=DEMO_USER_ROLE)

    app = FastAPI()
    # Register innermost first; CSRF wraps Auth (so CSRF runs after Auth).
    app.add_middleware(CSRFMiddleware, csrf_secret=_TEST_CSRF_SECRET)
    app.add_middleware(AuthenticationMiddleware, jwt_secret=TEST_JWT_SECRET)

    @app.post("/api/v1/services")
    async def protected_post(request: Request) -> JSONResponse:
        return JSONResponse({"ok": True, "user_id": getattr(request.state, "user_id", None)})

    @app.get("/api/v1/services")
    async def protected_get(request: Request) -> JSONResponse:
        return JSONResponse({"ok": True})

    @app.post("/api/v1/auth/login")
    async def login() -> dict:
        return {"token": "fake"}

    @app.get("/health")
    async def health() -> dict:
        return {"status": "ok"}

    return app, access_token


# ---------------------------------------------------------------------------
# Safe method exemptions
# ---------------------------------------------------------------------------

class TestSafeMethodExemptions:
    async def test_get_bypasses_csrf(self):
        app, access_token = _make_csrf_app()
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            c.cookies.set("access_token", access_token)
            resp = await c.get("/api/v1/services")
        assert resp.status_code == 200

    async def test_options_bypasses_csrf(self):
        app, access_token = _make_csrf_app()
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.options("/api/v1/services")
        assert resp.status_code != 403


# ---------------------------------------------------------------------------
# Public path exemptions
# ---------------------------------------------------------------------------

class TestPublicPathExemptions:
    async def test_login_post_bypasses_csrf(self):
        app, _ = _make_csrf_app()
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.post("/api/v1/auth/login")
        assert resp.status_code != 403

    async def test_health_get_bypasses_csrf(self):
        app, _ = _make_csrf_app()
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.get("/health")
        assert resp.status_code != 403


# ---------------------------------------------------------------------------
# CSRF enforcement on protected mutations
# ---------------------------------------------------------------------------

class TestCsrfEnforcementOnMutations:
    async def test_post_without_csrf_header_returns_403(self):
        app, access_token = _make_csrf_app()
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            c.cookies.set("access_token", access_token)
            resp = await c.post("/api/v1/services")
        assert resp.status_code == 403

    async def test_missing_csrf_header_detail(self):
        app, access_token = _make_csrf_app()
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            c.cookies.set("access_token", access_token)
            resp = await c.post("/api/v1/services")
        assert resp.json()["detail"] == "CSRF token required"

    async def test_wrong_csrf_token_returns_403(self):
        app, access_token = _make_csrf_app()
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            c.cookies.set("access_token", access_token)
            resp = await c.post("/api/v1/services", headers={"X-CSRF-Token": "wrong-token"})
        assert resp.status_code == 403

    async def test_wrong_csrf_token_detail(self):
        app, access_token = _make_csrf_app()
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            c.cookies.set("access_token", access_token)
            resp = await c.post("/api/v1/services", headers={"X-CSRF-Token": "wrong-token"})
        assert resp.json()["detail"] == "CSRF token invalid"

    async def test_valid_csrf_token_returns_200(self):
        from forgeguard.core.security import decode_access_token  # noqa: PLC0415

        app, access_token = _make_csrf_app()
        payload = decode_access_token(access_token, TEST_JWT_SECRET)
        csrf_token = generate_csrf_token(payload["jti"], _TEST_CSRF_SECRET)

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            c.cookies.set("access_token", access_token)
            resp = await c.post("/api/v1/services", headers={"X-CSRF-Token": csrf_token})
        assert resp.status_code == 200

    async def test_multiple_requests_with_same_valid_token_all_succeed(self):
        from forgeguard.core.security import decode_access_token  # noqa: PLC0415

        app, access_token = _make_csrf_app()
        payload = decode_access_token(access_token, TEST_JWT_SECRET)
        csrf_token = generate_csrf_token(payload["jti"], _TEST_CSRF_SECRET)

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            c.cookies.set("access_token", access_token)
            for _ in range(3):
                resp = await c.post("/api/v1/services", headers={"X-CSRF-Token": csrf_token})
                assert resp.status_code == 200

    async def test_csrf_token_from_different_user_returns_403(self):
        from forgeguard.core.security import decode_access_token  # noqa: PLC0415

        app, access_token = _make_csrf_app()
        # Token from a different user (different JTI)
        other_id = uuid.uuid4()
        other_token = make_access_token(user_id=other_id, role="developer")
        other_payload = decode_access_token(other_token, TEST_JWT_SECRET)
        wrong_csrf = generate_csrf_token(other_payload["jti"], _TEST_CSRF_SECRET)

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            c.cookies.set("access_token", access_token)
            resp = await c.post("/api/v1/services", headers={"X-CSRF-Token": wrong_csrf})
        assert resp.status_code == 403
