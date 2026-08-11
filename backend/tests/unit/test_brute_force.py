"""Unit tests for brute-force / account lockout protection (WO-024).

All tests use mocked UserRepository and RefreshTokenRepository — no DB needed.

Scenarios:
  calculate_lockout_duration:
    - lockout_count=1 → 60s (1 min)
    - lockout_count=2 → 120s (2 min)
    - lockout_count=3 → 240s (4 min)
    - lockout_count=4 → 480s (8 min)
    - lockout_count=5 → 960s (16 min)
    - lockout_count=6 → 1800s cap (30 min)
    - lockout_count=10 → still 1800s cap

  authenticate_user — brute-force tracking:
    - wrong password increments failed_login_attempts counter
    - 5th failure (new_count=5) triggers lockout
    - lockout message is generic (no duration revealed)
    - locked account raises UnauthorizedError before credential check
    - expired lock allows login (auto-unlock)
    - successful login calls reset_failed_attempts
    - non-existent user does NOT call increment_failed_attempts
    - 10th failure triggers 2nd lockout with doubled duration
    - counter reset is NOT called on failed login
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, call, patch

import pytest

from forgeguard.core.exceptions import UnauthorizedError
from forgeguard.core.security import hash_password
from forgeguard.services.auth import AuthService, _LOCKED_MSG, calculate_lockout_duration
from tests.fixtures.tokens import (
    DEMO_USER_EMAIL,
    DEMO_USER_ID,
    DEMO_USER_ROLE,
    TEST_JWT_SECRET,
    make_refresh_token_row,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_PASSWORD = "Str0ng!P@ssword1"


def _make_user_row(
    *,
    user_id: uuid.UUID = DEMO_USER_ID,
    email: str = DEMO_USER_EMAIL,
    is_active: bool = True,
    locked_until: datetime | None = None,
    failed_login_attempts: int = 0,
    password: str = _PASSWORD,
) -> dict:
    return {
        "id": user_id,
        "email": email,
        "name_encrypted": b"Demo",
        "password_hash": hash_password(password),
        "role": DEMO_USER_ROLE,
        "is_active": is_active,
        "locked_until": locked_until,
        "failed_login_attempts": failed_login_attempts,
        "created_at": datetime.now(tz=timezone.utc),
        "updated_at": datetime.now(tz=timezone.utc),
    }


def _make_service(
    user_row=None,
    *,
    increment_returns: int = 1,
) -> tuple[AuthService, AsyncMock, AsyncMock]:
    user_repo = AsyncMock()
    rt_repo = AsyncMock()

    user_repo.find_by_email.return_value = user_row
    user_repo.get_by_id.return_value = user_row
    user_repo.increment_failed_attempts = AsyncMock(return_value=increment_returns)
    user_repo.reset_failed_attempts = AsyncMock(return_value=None)
    user_repo.lock_account = AsyncMock(return_value=None)

    rt_repo.create.return_value = make_refresh_token_row()
    rt_repo.revoke.return_value = None
    rt_repo.revoke_all_for_user.return_value = 1

    service = AuthService(user_repo, rt_repo, jwt_secret=TEST_JWT_SECRET)
    return service, user_repo, rt_repo


# ---------------------------------------------------------------------------
# calculate_lockout_duration — pure function
# ---------------------------------------------------------------------------

class TestCalculateLockoutDuration:
    def test_first_lockout_is_60_seconds(self):
        assert calculate_lockout_duration(1) == timedelta(seconds=60)

    def test_second_lockout_is_120_seconds(self):
        assert calculate_lockout_duration(2) == timedelta(seconds=120)

    def test_third_lockout_is_240_seconds(self):
        assert calculate_lockout_duration(3) == timedelta(seconds=240)

    def test_fourth_lockout_is_480_seconds(self):
        assert calculate_lockout_duration(4) == timedelta(seconds=480)

    def test_fifth_lockout_is_960_seconds(self):
        assert calculate_lockout_duration(5) == timedelta(seconds=960)

    def test_sixth_lockout_is_capped_at_1800_seconds(self):
        assert calculate_lockout_duration(6) == timedelta(seconds=1800)

    def test_high_lockout_count_still_capped_at_1800(self):
        assert calculate_lockout_duration(10) == timedelta(seconds=1800)
        assert calculate_lockout_duration(100) == timedelta(seconds=1800)


# ---------------------------------------------------------------------------
# Failed attempt tracking
# ---------------------------------------------------------------------------

class TestFailedAttemptTracking:
    async def test_wrong_password_calls_increment(self):
        row = _make_user_row()
        service, user_repo, _ = _make_service(user_row=row, increment_returns=1)
        with pytest.raises(UnauthorizedError):
            await service.authenticate_user(DEMO_USER_EMAIL, "WrongPass!1")
        user_repo.increment_failed_attempts.assert_awaited_once_with(DEMO_USER_ID)

    async def test_nonexistent_user_does_not_increment(self):
        service, user_repo, _ = _make_service(user_row=None)
        with pytest.raises(UnauthorizedError):
            await service.authenticate_user("ghost@example.com", "AnyPass!1")
        user_repo.increment_failed_attempts.assert_not_awaited()

    async def test_fifth_failure_triggers_lockout(self):
        row = _make_user_row(failed_login_attempts=4)
        service, user_repo, _ = _make_service(user_row=row, increment_returns=5)
        with pytest.raises(UnauthorizedError):
            await service.authenticate_user(DEMO_USER_EMAIL, "WrongPass!1")
        user_repo.lock_account.assert_awaited_once()

    async def test_fourth_failure_does_not_trigger_lockout(self):
        row = _make_user_row(failed_login_attempts=3)
        service, user_repo, _ = _make_service(user_row=row, increment_returns=4)
        with pytest.raises(UnauthorizedError):
            await service.authenticate_user(DEMO_USER_EMAIL, "WrongPass!1")
        user_repo.lock_account.assert_not_awaited()

    async def test_tenth_failure_triggers_second_lockout(self):
        row = _make_user_row(failed_login_attempts=9)
        service, user_repo, _ = _make_service(user_row=row, increment_returns=10)
        with pytest.raises(UnauthorizedError):
            await service.authenticate_user(DEMO_USER_EMAIL, "WrongPass!1")
        user_repo.lock_account.assert_awaited_once()

    async def test_lockout_duration_for_first_lockout_is_one_minute(self):
        row = _make_user_row(failed_login_attempts=4)
        service, user_repo, _ = _make_service(user_row=row, increment_returns=5)
        with pytest.raises(UnauthorizedError):
            await service.authenticate_user(DEMO_USER_EMAIL, "WrongPass!1")
        call_args = user_repo.lock_account.call_args
        locked_until = call_args.args[1] if call_args.args else call_args.kwargs.get("locked_until")
        expected_min = datetime.now(tz=timezone.utc) + timedelta(seconds=55)
        expected_max = datetime.now(tz=timezone.utc) + timedelta(seconds=65)
        assert expected_min <= locked_until <= expected_max

    async def test_lockout_duration_for_second_lockout_is_two_minutes(self):
        row = _make_user_row(failed_login_attempts=9)
        service, user_repo, _ = _make_service(user_row=row, increment_returns=10)
        with pytest.raises(UnauthorizedError):
            await service.authenticate_user(DEMO_USER_EMAIL, "WrongPass!1")
        call_args = user_repo.lock_account.call_args
        locked_until = call_args.args[1] if call_args.args else call_args.kwargs.get("locked_until")
        expected_min = datetime.now(tz=timezone.utc) + timedelta(seconds=115)
        expected_max = datetime.now(tz=timezone.utc) + timedelta(seconds=125)
        assert expected_min <= locked_until <= expected_max


# ---------------------------------------------------------------------------
# Locked account enforcement
# ---------------------------------------------------------------------------

class TestLockedAccountEnforcement:
    async def test_locked_account_raises_unauthorized(self):
        future = datetime.now(tz=timezone.utc) + timedelta(hours=1)
        row = _make_user_row(locked_until=future)
        service, _, _ = _make_service(user_row=row)
        with pytest.raises(UnauthorizedError) as exc_info:
            await service.authenticate_user(DEMO_USER_EMAIL, _PASSWORD)
        assert _LOCKED_MSG in str(exc_info.value)

    async def test_locked_message_does_not_reveal_duration(self):
        future = datetime.now(tz=timezone.utc) + timedelta(minutes=2)
        row = _make_user_row(locked_until=future)
        service, _, _ = _make_service(user_row=row)
        with pytest.raises(UnauthorizedError) as exc_info:
            await service.authenticate_user(DEMO_USER_EMAIL, _PASSWORD)
        msg = str(exc_info.value)
        assert "minute" not in msg.lower()
        assert "second" not in msg.lower()
        assert "120" not in msg

    async def test_locked_account_does_not_increment_counter(self):
        future = datetime.now(tz=timezone.utc) + timedelta(hours=1)
        row = _make_user_row(locked_until=future)
        service, user_repo, _ = _make_service(user_row=row)
        with pytest.raises(UnauthorizedError):
            await service.authenticate_user(DEMO_USER_EMAIL, _PASSWORD)
        user_repo.increment_failed_attempts.assert_not_awaited()

    async def test_expired_lock_allows_login(self):
        past = datetime.now(tz=timezone.utc) - timedelta(hours=1)
        row = _make_user_row(locked_until=past)
        service, _, _ = _make_service(user_row=row)
        result = await service.authenticate_user(DEMO_USER_EMAIL, _PASSWORD)
        assert result is not None

    async def test_naive_locked_until_treated_as_utc(self):
        future_naive = datetime.utcnow() + timedelta(hours=1)
        assert future_naive.tzinfo is None
        row = _make_user_row(locked_until=future_naive)
        service, _, _ = _make_service(user_row=row)
        with pytest.raises(UnauthorizedError) as exc_info:
            await service.authenticate_user(DEMO_USER_EMAIL, _PASSWORD)
        assert _LOCKED_MSG in str(exc_info.value)


# ---------------------------------------------------------------------------
# Successful login counter reset
# ---------------------------------------------------------------------------

class TestSuccessfulLoginResetsCounter:
    async def test_success_calls_reset_failed_attempts(self):
        row = _make_user_row()
        service, user_repo, _ = _make_service(user_row=row)
        await service.authenticate_user(DEMO_USER_EMAIL, _PASSWORD)
        user_repo.reset_failed_attempts.assert_awaited_once_with(DEMO_USER_ID)

    async def test_failed_login_does_not_call_reset(self):
        row = _make_user_row()
        service, user_repo, _ = _make_service(user_row=row, increment_returns=1)
        with pytest.raises(UnauthorizedError):
            await service.authenticate_user(DEMO_USER_EMAIL, "WrongPass!1")
        user_repo.reset_failed_attempts.assert_not_awaited()
