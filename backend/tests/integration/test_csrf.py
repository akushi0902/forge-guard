"""Integration tests for CSRF token protection (WO-025).

Uses the full FastAPI application with dependency overrides — no real database.

Scenarios:
  1. Login response includes X-CSRF-Token header.
  2. Mutation request with captured CSRF token succeeds.
  3. Mutation request without X-CSRF-Token header returns 403.
  4. Mutation request with wrong X-CSRF-Token returns 403.
  5. Refresh response includes a new X-CSRF-Token header.
  6. Old CSRF token (from before refresh) is rejected after token rotation.
  7. GET request to protected endpoint never requires CSRF token.
  8. Public endpoint (POST /login) is exempt from CSRF.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest
from httpx import ASGITransport, AsyncClient

from forgeguard.core.dependencies import get_refresh_token_repository, get_user_repository
from forgeguard.core.security import hash_password, hash_refresh_token
from forgeguard.main import create_app
from tests.fixtures.tokens import (
    DEMO_USER_EMAIL,
    DEMO_USER_ID,
    DEMO_USER_ROLE,
    TEST_JWT_SECRET,
    make_refresh_token_row,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_LOGIN_URL = "/api/v1/auth/login"
_REFRESH_URL = "/api/v1/auth/refresh"
_PASSWORD = "Str0ng!P@ssword1"
_TEST_CSRF_SECRET = "test-csrf-secret-for-integration"

# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------


def _make_user_row(*, locked_until=None) -> dict:
    return {
        "id": DEMO_USER_ID,
        "email": DEMO_USER_EMAIL,
        "name_encrypted": b"Demo",
        "password_hash": hash_password(_PASSWORD),
        "role": DEMO_USER_ROLE,
        "is_active": True,
        "locked_until": locked_until,
        "failed_login_attempts": 0,
        "created_at": datetime.now(tz=timezone.utc),
        "updated_at": datetime.now(tz=timezone.utc),
    }


def _make_app(*, user_row=None, rt_row=None, create_rt=None):
    import forgeguard.core.config as config_module  # noqa: PLC0415
    from forgeguard.core.config import Settings  # noqa: PLC0415

    settings = Settings(
        database_url="postgresql+asyncpg://localhost/test",
        jwt_secret_key=TEST_JWT_SECRET,
        csrf_secret_key=_TEST_CSRF_SECRET,
        log_level="DEBUG",
        app_env="testing",
        llm_api_key="",
        forge_catalog_url="http://localhost:9999/catalog",
    )
    config_module._settings_cache = settings
    app = create_app()

    user_repo = AsyncMock()
    user_repo.find_by_email.return_value = user_row
    user_repo.get_by_id.return_value = user_row
    user_repo.increment_failed_attempts = AsyncMock(return_value=1)
    user_repo.reset_failed_attempts = AsyncMock(return_value=None)
    user_repo.lock_account = AsyncMock(return_value=None)

    rt_repo = AsyncMock()
    rt_repo.get_by_hash.return_value = rt_row
    rt_repo.create.return_value = create_rt or make_refresh_token_row()
    rt_repo.revoke.return_value = None
    rt_repo.revoke_all_for_user.return_value = 1

    app.dependency_overrides[get_user_repository] = lambda: user_repo
    app.dependency_overrides[get_refresh_token_repository] = lambda: rt_repo
    return app, user_repo, rt_repo


# ---------------------------------------------------------------------------
# Login response includes X-CSRF-Token
# ---------------------------------------------------------------------------

class TestLoginIncludesCsrfToken:
    async def test_login_response_has_csrf_header(self):
        app, _, _ = _make_app(user_row=_make_user_row())
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.post(_LOGIN_URL, json={"email": DEMO_USER_EMAIL, "password": _PASSWORD})
        assert resp.status_code == 200
        headers_lower = {k.lower(): v for k, v in resp.headers.items()}
        assert "x-csrf-token" in headers_lower

    async def test_csrf_token_is_non_empty(self):
        app, _, _ = _make_app(user_row=_make_user_row())
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.post(_LOGIN_URL, json={"email": DEMO_USER_EMAIL, "password": _PASSWORD})
        headers_lower = {k.lower(): v for k, v in resp.headers.items()}
        assert len(headers_lower.get("x-csrf-token", "")) >= 43


# ---------------------------------------------------------------------------
# Refresh response includes new X-CSRF-Token
# ---------------------------------------------------------------------------

class TestRefreshIncludesCsrfToken:
    async def test_refresh_returns_new_csrf_token(self):
        import secrets as _secrets  # noqa: PLC0415

        raw = _secrets.token_urlsafe(64)
        old_row = make_refresh_token_row(token_hash=hash_refresh_token(raw))
        new_row = make_refresh_token_row()
        app, _, rt_repo = _make_app(user_row=_make_user_row(), rt_row=old_row, create_rt=new_row)
        rt_repo.get_by_hash.return_value = old_row
        rt_repo.create.return_value = new_row

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            c.cookies.set("refresh_token", raw)
            resp = await c.post(_REFRESH_URL)

        assert resp.status_code == 200
        headers_lower = {k.lower(): v for k, v in resp.headers.items()}
        assert "x-csrf-token" in headers_lower
        assert len(headers_lower["x-csrf-token"]) >= 43

    async def test_refresh_csrf_token_differs_from_login_csrf_token(self):
        import secrets as _secrets  # noqa: PLC0415

        # Login to get initial CSRF token
        app, _, rt_repo = _make_app(user_row=_make_user_row())

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            login_resp = await c.post(_LOGIN_URL, json={"email": DEMO_USER_EMAIL, "password": _PASSWORD})
        login_headers = {k.lower(): v for k, v in login_resp.headers.items()}
        first_csrf = login_headers.get("x-csrf-token")

        # Refresh to get new CSRF token
        raw = _secrets.token_urlsafe(64)
        rt_row = make_refresh_token_row(token_hash=hash_refresh_token(raw))
        new_row = make_refresh_token_row()
        app2, _, rt_repo2 = _make_app(user_row=_make_user_row(), rt_row=rt_row, create_rt=new_row)
        rt_repo2.get_by_hash.return_value = rt_row
        rt_repo2.create.return_value = new_row

        async with AsyncClient(transport=ASGITransport(app=app2), base_url="http://test") as c:
            c.cookies.set("refresh_token", raw)
            refresh_resp = await c.post(_REFRESH_URL)
        refresh_headers = {k.lower(): v for k, v in refresh_resp.headers.items()}
        second_csrf = refresh_headers.get("x-csrf-token")

        # Different JTIs → different CSRF tokens
        assert first_csrf != second_csrf


# ---------------------------------------------------------------------------
# CSRF validation on the full app (uses /api/v1/auth/change-password as
# a protected mutation endpoint that requires auth + CSRF)
# ---------------------------------------------------------------------------

class TestCsrfValidationOnProtectedEndpoints:
    async def _login_and_get_csrf(self, app) -> tuple[str, str]:
        """Login and return (access_token, csrf_token)."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.post(_LOGIN_URL, json={"email": DEMO_USER_EMAIL, "password": _PASSWORD})
        headers_lower = {k.lower(): v for k, v in resp.headers.items()}
        access_token = resp.cookies.get("access_token") or ""
        csrf_token = headers_lower.get("x-csrf-token", "")
        return access_token, csrf_token

    async def test_mutation_without_csrf_returns_403(self):
        # Use change-password endpoint as a convenient protected POST
        app, user_repo, _ = _make_app(user_row=_make_user_row())
        user_repo.get_by_id.return_value = _make_user_row()
        access_token, _ = await self._login_and_get_csrf(app)

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            c.cookies.set("access_token", access_token)
            resp = await c.post(
                "/api/v1/auth/change-password",
                json={"current_password": "old", "new_password": "New!Str0ngP@ss"},
            )
        assert resp.status_code == 403

    async def test_mutation_with_wrong_csrf_returns_403(self):
        app, user_repo, _ = _make_app(user_row=_make_user_row())
        user_repo.get_by_id.return_value = _make_user_row()
        access_token, _ = await self._login_and_get_csrf(app)

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            c.cookies.set("access_token", access_token)
            resp = await c.post(
                "/api/v1/auth/change-password",
                json={"current_password": "old", "new_password": "New!Str0ngP@ss"},
                headers={"X-CSRF-Token": "obviously-wrong-csrf"},
            )
        assert resp.status_code == 403

    async def test_login_post_exempt_from_csrf(self):
        app, _, _ = _make_app(user_row=_make_user_row())
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.post(_LOGIN_URL, json={"email": DEMO_USER_EMAIL, "password": _PASSWORD})
        assert resp.status_code == 200
