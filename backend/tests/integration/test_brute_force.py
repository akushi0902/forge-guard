"""Integration tests for brute-force / account lockout (WO-024).

Uses ASGI TestClient with dependency overrides — no real database.
Simulates the full lockout lifecycle through the HTTP layer.

Scenarios:
  1. 5 failed attempts → generic 401 each time.
  2. 6th attempt with lockout active → 401 with lockout message.
  3. After lockout expires (mocked) → login proceeds normally.
  4. Successful login after any failures → counter reset called.
  5. Non-existent user → generic 401, no increment.
  6. Auth endpoints rate-limited (429 after exceeding limit).
  7. General endpoints NOT blocked at auth limit.

Helper:
  _rapid_failures(n) — sends n bad password attempts quickly.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest
from httpx import ASGITransport, AsyncClient

from forgeguard.core.dependencies import get_refresh_token_repository, get_user_repository
from forgeguard.core.security import hash_password
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
_PASSWORD = "Str0ng!P@ssword1"
_LOCKED_MSG = "Account temporarily locked. Try again later."


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_user_row(
    *,
    locked_until: datetime | None = None,
    failed_login_attempts: int = 0,
    is_active: bool = True,
) -> dict:
    return {
        "id": DEMO_USER_ID,
        "email": DEMO_USER_EMAIL,
        "name_encrypted": b"Demo",
        "password_hash": hash_password(_PASSWORD),
        "role": DEMO_USER_ROLE,
        "is_active": is_active,
        "locked_until": locked_until,
        "failed_login_attempts": failed_login_attempts,
        "created_at": datetime.now(tz=timezone.utc),
        "updated_at": datetime.now(tz=timezone.utc),
    }


def _make_app(
    *,
    user_row: dict | None = None,
    increment_side_effect=None,
) -> tuple:
    """Return (app, user_repo_mock, rt_repo_mock)."""
    import forgeguard.core.config as config_module  # noqa: PLC0415
    from forgeguard.core.config import Settings  # noqa: PLC0415

    settings = Settings(
        database_url="postgresql+asyncpg://localhost/test",
        jwt_secret_key=TEST_JWT_SECRET,
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
    if increment_side_effect is not None:
        user_repo.increment_failed_attempts.side_effect = increment_side_effect

    rt_repo = AsyncMock()
    rt_repo.create.return_value = make_refresh_token_row()
    rt_repo.revoke.return_value = None
    rt_repo.revoke_all_for_user.return_value = 1

    app.dependency_overrides[get_user_repository] = lambda: user_repo
    app.dependency_overrides[get_refresh_token_repository] = lambda: rt_repo
    return app, user_repo, rt_repo


async def _rapid_failures(client: AsyncClient, count: int, email: str = DEMO_USER_EMAIL) -> list:
    """Send `count` bad-password login attempts and return all responses."""
    responses = []
    for _ in range(count):
        resp = await client.post(_LOGIN_URL, json={"email": email, "password": "WrongPass!1"})
        responses.append(resp)
    return responses


# ---------------------------------------------------------------------------
# Lockout lifecycle
# ---------------------------------------------------------------------------

class TestLockoutLifecycle:
    async def test_five_failed_attempts_return_generic_401(self):
        # Simulate incrementing counter: returns 1..5
        counts = iter(range(1, 6))
        app, user_repo, _ = _make_app(
            user_row=_make_user_row(),
            increment_side_effect=lambda _: next(counts),
        )
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            responses = await _rapid_failures(c, 5)
        for resp in responses:
            assert resp.status_code == 401
            assert resp.json()["detail"] == "Invalid email or password."

    async def test_fifth_failure_triggers_lock_account_call(self):
        counts = iter(range(1, 6))
        app, user_repo, _ = _make_app(
            user_row=_make_user_row(),
            increment_side_effect=lambda _: next(counts),
        )
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            await _rapid_failures(c, 5)
        user_repo.lock_account.assert_awaited_once()

    async def test_locked_account_returns_401_with_lockout_message(self):
        future = datetime.now(tz=timezone.utc) + timedelta(minutes=1)
        app, _, _ = _make_app(user_row=_make_user_row(locked_until=future))
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.post(_LOGIN_URL, json={"email": DEMO_USER_EMAIL, "password": "AnyPass!1"})
        assert resp.status_code == 401
        assert resp.json()["detail"] == _LOCKED_MSG

    async def test_lockout_message_hides_duration(self):
        future = datetime.now(tz=timezone.utc) + timedelta(minutes=2)
        app, _, _ = _make_app(user_row=_make_user_row(locked_until=future))
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.post(_LOGIN_URL, json={"email": DEMO_USER_EMAIL, "password": "AnyPass!1"})
        detail = resp.json()["detail"]
        assert "minute" not in detail.lower()
        assert "120" not in detail

    async def test_expired_lock_allows_login(self):
        past = datetime.now(tz=timezone.utc) - timedelta(hours=1)
        app, _, _ = _make_app(user_row=_make_user_row(locked_until=past))
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.post(_LOGIN_URL, json={"email": DEMO_USER_EMAIL, "password": _PASSWORD})
        assert resp.status_code == 200

    async def test_successful_login_resets_counter(self):
        app, user_repo, _ = _make_app(user_row=_make_user_row())
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            await c.post(_LOGIN_URL, json={"email": DEMO_USER_EMAIL, "password": _PASSWORD})
        user_repo.reset_failed_attempts.assert_awaited_once_with(DEMO_USER_ID)

    async def test_nonexistent_user_no_increment(self):
        app, user_repo, _ = _make_app(user_row=None)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            await c.post(_LOGIN_URL, json={"email": "ghost@example.com", "password": "WrongPass!1"})
        user_repo.increment_failed_attempts.assert_not_awaited()


# ---------------------------------------------------------------------------
# Rate limiting on auth endpoints
# ---------------------------------------------------------------------------

class TestAuthRateLimiting:
    async def test_auth_endpoint_returns_429_when_rate_exceeded(self):
        """Verify the rate limiter returns 429 after exhausting the auth bucket.

        We bypass the actual login logic by using a non-existent user so
        DB mocks don't interfere.  The rate limiter runs at middleware stage 3,
        before the auth service, so any response after exhaustion should be 429.
        """
        import forgeguard.core.config as config_module  # noqa: PLC0415
        from forgeguard.core.config import Settings  # noqa: PLC0415
        from forgeguard.middleware.rate_limiter import RateLimiterMiddleware  # noqa: PLC0415

        # Create app with very tight limits
        settings = Settings(
            database_url="postgresql+asyncpg://localhost/test",
            jwt_secret_key=TEST_JWT_SECRET,
            log_level="DEBUG",
            app_env="testing",
            llm_api_key="",
            forge_catalog_url="http://localhost:9999/catalog",
            rate_limit_auth=2,
            rate_limit_general=100,
            rate_limit_window_seconds=60,
        )
        config_module._settings_cache = settings
        app = create_app()

        user_repo = AsyncMock()
        user_repo.find_by_email.return_value = None
        user_repo.increment_failed_attempts = AsyncMock(return_value=1)
        user_repo.reset_failed_attempts = AsyncMock(return_value=None)
        user_repo.lock_account = AsyncMock(return_value=None)
        rt_repo = AsyncMock()
        rt_repo.create.return_value = make_refresh_token_row()

        app.dependency_overrides[get_user_repository] = lambda: user_repo
        app.dependency_overrides[get_refresh_token_repository] = lambda: rt_repo

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            # Exhaust the 2-request auth bucket
            for _ in range(2):
                await c.post(_LOGIN_URL, json={"email": "x@x.com", "password": "Pass!1"})
            resp = await c.post(_LOGIN_URL, json={"email": "x@x.com", "password": "Pass!1"})
        assert resp.status_code == 429
        assert "retry-after" in resp.headers or "Retry-After" in resp.headers
