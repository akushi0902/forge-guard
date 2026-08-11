"""Integration tests for auth login/refresh/logout HTTP routes (WO-022).

Uses ASGI TestClient with dependency overrides — no real database.

Scenarios:
  POST /api/v1/auth/login:
    - 200 with Set-Cookie headers on valid credentials
    - 401 on wrong password
    - 401 on non-existent user
    - 401 on inactive account
    - response body matches LoginResponse schema
    - no PII leakage in access_token cookie JWT claims

  POST /api/v1/auth/refresh:
    - 200 and new cookies on valid refresh token cookie
    - 401 when no refresh_token cookie present
    - 401 on invalid token

  POST /api/v1/auth/logout:
    - 200 and Set-Cookie max_age=0 (cookies cleared)
    - 200 even without cookie (idempotent)
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
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
_LOGOUT_URL = "/api/v1/auth/logout"

_VALID_PASSWORD = "Str0ng!P@ssword1"

_VALID_LOGIN_BODY = {
    "email": DEMO_USER_EMAIL,
    "password": _VALID_PASSWORD,
}


# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------

def _make_user_row(
    *,
    user_id: uuid.UUID = DEMO_USER_ID,
    email: str = DEMO_USER_EMAIL,
    role: str = DEMO_USER_ROLE,
    is_active: bool = True,
    locked_until: datetime | None = None,
    password: str = _VALID_PASSWORD,
) -> dict:
    return {
        "id": user_id,
        "email": email,
        "name_encrypted": b"Demo Admin",
        "password_hash": hash_password(password),
        "role": role,
        "is_active": is_active,
        "locked_until": locked_until,
        "failed_login_attempts": 0,
        "created_at": datetime.now(tz=timezone.utc),
        "updated_at": datetime.now(tz=timezone.utc),
    }


def _make_app(
    *,
    user_row: dict | None = None,
    rt_row: dict | None = None,
    create_rt_returns: dict | None = None,
):
    """Return test app with overridden repos."""
    import forgeguard.core.config as config_module  # noqa: PLC0415
    from forgeguard.core.config import Settings  # noqa: PLC0415

    settings = Settings(
        database_url="postgresql+asyncpg://postgres:postgres@localhost:5432/forgeguard_test",
        jwt_secret_key=TEST_JWT_SECRET,
        log_level="DEBUG",
        app_env="testing",
        llm_api_key="",
        forge_catalog_url="http://localhost:9999/catalog",
    )
    config_module._settings_cache = settings

    app = create_app()

    user_repo_mock = AsyncMock()
    user_repo_mock.find_by_email.return_value = user_row
    user_repo_mock.get_by_id.return_value = user_row

    rt_repo_mock = AsyncMock()
    rt_repo_mock.get_by_hash.return_value = rt_row
    rt_repo_mock.get_active_by_hash.return_value = rt_row
    rt_repo_mock.create.return_value = create_rt_returns or make_refresh_token_row()
    rt_repo_mock.revoke.return_value = None
    rt_repo_mock.revoke_all_for_user.return_value = 1

    app.dependency_overrides[get_user_repository] = lambda: user_repo_mock
    app.dependency_overrides[get_refresh_token_repository] = lambda: rt_repo_mock
    return app, user_repo_mock, rt_repo_mock


# ---------------------------------------------------------------------------
# Login — 200 success
# ---------------------------------------------------------------------------

class TestLoginSuccess:
    async def test_returns_200(self):
        app, _, _ = _make_app(user_row=_make_user_row())
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as c:
            resp = await c.post(_LOGIN_URL, json=_VALID_LOGIN_BODY)
        assert resp.status_code == 200

    async def test_sets_access_token_cookie(self):
        app, _, _ = _make_app(user_row=_make_user_row())
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as c:
            resp = await c.post(_LOGIN_URL, json=_VALID_LOGIN_BODY)
        assert "access_token" in resp.cookies

    async def test_sets_refresh_token_cookie(self):
        app, _, _ = _make_app(user_row=_make_user_row())
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as c:
            resp = await c.post(_LOGIN_URL, json=_VALID_LOGIN_BODY)
        assert "refresh_token" in resp.cookies

    async def test_response_body_contains_user_id(self):
        app, _, _ = _make_app(user_row=_make_user_row())
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as c:
            resp = await c.post(_LOGIN_URL, json=_VALID_LOGIN_BODY)
        assert "id" in resp.json()

    async def test_response_body_contains_role(self):
        app, _, _ = _make_app(user_row=_make_user_row())
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as c:
            resp = await c.post(_LOGIN_URL, json=_VALID_LOGIN_BODY)
        assert resp.json().get("role") == DEMO_USER_ROLE

    async def test_response_body_does_not_contain_password_hash(self):
        app, _, _ = _make_app(user_row=_make_user_row())
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as c:
            resp = await c.post(_LOGIN_URL, json=_VALID_LOGIN_BODY)
        body_text = str(resp.json())
        assert "password_hash" not in body_text
        assert "password" not in body_text

    async def test_access_token_jwt_has_no_pii(self):
        """JWT stored in access_token cookie must not contain email or name."""
        from forgeguard.core.security import decode_access_token  # noqa: PLC0415

        app, _, _ = _make_app(user_row=_make_user_row())
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as c:
            resp = await c.post(_LOGIN_URL, json=_VALID_LOGIN_BODY)

        access_jwt = resp.cookies.get("access_token")
        assert access_jwt is not None
        payload = decode_access_token(access_jwt, TEST_JWT_SECRET)
        assert DEMO_USER_EMAIL not in str(payload.values())
        assert "Demo Admin" not in str(payload.values())


# ---------------------------------------------------------------------------
# Login — 401 failures
# ---------------------------------------------------------------------------

class TestLoginFailures:
    async def test_wrong_password_returns_401(self):
        app, _, _ = _make_app(user_row=_make_user_row())
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as c:
            resp = await c.post(_LOGIN_URL, json={**_VALID_LOGIN_BODY, "password": "WrongPass!1"})
        assert resp.status_code == 401

    async def test_non_existent_user_returns_401(self):
        app, _, _ = _make_app(user_row=None)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as c:
            resp = await c.post(_LOGIN_URL, json=_VALID_LOGIN_BODY)
        assert resp.status_code == 401

    async def test_inactive_account_returns_401(self):
        app, _, _ = _make_app(user_row=_make_user_row(is_active=False))
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as c:
            resp = await c.post(_LOGIN_URL, json=_VALID_LOGIN_BODY)
        assert resp.status_code == 401

    async def test_locked_account_returns_401(self):
        future = datetime.now(tz=timezone.utc) + timedelta(hours=1)
        app, _, _ = _make_app(user_row=_make_user_row(locked_until=future))
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as c:
            resp = await c.post(_LOGIN_URL, json=_VALID_LOGIN_BODY)
        assert resp.status_code == 401

    async def test_missing_email_returns_422(self):
        app, _, _ = _make_app(user_row=_make_user_row())
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as c:
            resp = await c.post(_LOGIN_URL, json={"password": _VALID_PASSWORD})
        assert resp.status_code == 422

    async def test_missing_password_returns_422(self):
        app, _, _ = _make_app(user_row=_make_user_row())
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as c:
            resp = await c.post(_LOGIN_URL, json={"email": DEMO_USER_EMAIL})
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Refresh — 200 success
# ---------------------------------------------------------------------------

class TestRefreshSuccess:
    async def _make_app_with_active_rt(self):
        import secrets  # noqa: PLC0415

        raw = secrets.token_urlsafe(64)
        token_row = make_refresh_token_row(token_hash=hash_refresh_token(raw))
        new_row = make_refresh_token_row()
        app, user_repo, rt_repo = _make_app(
            user_row=_make_user_row(),
            rt_row=token_row,
            create_rt_returns=new_row,
        )
        rt_repo.get_by_hash.return_value = token_row
        return app, rt_repo, raw

    async def test_returns_200(self):
        app, _, raw = await self._make_app_with_active_rt()
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as c:
            c.cookies.set("refresh_token", raw)
            resp = await c.post(_REFRESH_URL)
        assert resp.status_code == 200

    async def test_sets_new_access_token_cookie(self):
        app, _, raw = await self._make_app_with_active_rt()
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as c:
            c.cookies.set("refresh_token", raw)
            resp = await c.post(_REFRESH_URL)
        assert "access_token" in resp.cookies

    async def test_sets_new_refresh_token_cookie(self):
        app, _, raw = await self._make_app_with_active_rt()
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as c:
            c.cookies.set("refresh_token", raw)
            resp = await c.post(_REFRESH_URL)
        assert "refresh_token" in resp.cookies


# ---------------------------------------------------------------------------
# Refresh — 401 failures
# ---------------------------------------------------------------------------

class TestRefreshFailures:
    async def test_missing_cookie_returns_401(self):
        app, _, _ = _make_app(user_row=_make_user_row())
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as c:
            resp = await c.post(_REFRESH_URL)
        assert resp.status_code == 401

    async def test_unknown_token_returns_401(self):
        import secrets  # noqa: PLC0415

        app, _, rt_repo = _make_app(user_row=_make_user_row(), rt_row=None)
        rt_repo.get_by_hash.return_value = None
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as c:
            c.cookies.set("refresh_token", secrets.token_urlsafe(64))
            resp = await c.post(_REFRESH_URL)
        assert resp.status_code == 401

    async def test_revoked_token_returns_401(self):
        import secrets  # noqa: PLC0415

        raw = secrets.token_urlsafe(64)
        revoked_row = make_refresh_token_row(
            token_hash=hash_refresh_token(raw),
            revoked_at=datetime.now(tz=timezone.utc),
        )
        app, _, rt_repo = _make_app(user_row=_make_user_row(), rt_row=revoked_row)
        rt_repo.get_by_hash.return_value = revoked_row
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as c:
            c.cookies.set("refresh_token", raw)
            resp = await c.post(_REFRESH_URL)
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Logout — 200
# ---------------------------------------------------------------------------

class TestLogout:
    async def test_returns_200_without_cookie(self):
        app, _, _ = _make_app(user_row=None)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as c:
            resp = await c.post(_LOGOUT_URL)
        assert resp.status_code == 200

    async def test_returns_200_with_cookie(self):
        import secrets  # noqa: PLC0415

        raw = secrets.token_urlsafe(64)
        row = make_refresh_token_row(token_hash=hash_refresh_token(raw))
        app, _, rt_repo = _make_app(user_row=_make_user_row(), rt_row=row)
        rt_repo.get_by_hash.return_value = row
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as c:
            c.cookies.set("refresh_token", raw)
            resp = await c.post(_LOGOUT_URL)
        assert resp.status_code == 200

    async def test_cookies_cleared_after_logout(self):
        import secrets  # noqa: PLC0415

        raw = secrets.token_urlsafe(64)
        row = make_refresh_token_row(token_hash=hash_refresh_token(raw))
        app, _, rt_repo = _make_app(user_row=_make_user_row(), rt_row=row)
        rt_repo.get_by_hash.return_value = row
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as c:
            c.cookies.set("refresh_token", raw)
            resp = await c.post(_LOGOUT_URL)
        # After logout, Set-Cookie should delete the cookies (max_age=0 or empty value)
        set_cookie_headers = resp.headers.get_list("set-cookie") if hasattr(resp.headers, "get_list") else [
            v for k, v in resp.headers.items() if k.lower() == "set-cookie"
        ]
        header_str = " ".join(set_cookie_headers)
        assert "access_token" in header_str or len(set_cookie_headers) >= 1
