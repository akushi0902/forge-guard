"""Unit tests for AuthService login / refresh / logout (WO-022).

All tests use mocked UserRepository and RefreshTokenRepository — no DB needed.

Scenarios:
  authenticate_user:
    - success: returns LoginResponse, access token, raw refresh token
    - wrong password → UnauthorizedError (generic message)
    - non-existent user → UnauthorizedError (same generic message)
    - inactive account → UnauthorizedError
    - locked account → UnauthorizedError
    - verify_password always called (timing-safe)
  refresh_tokens:
    - success: returns new access token + new raw refresh token
    - revoked token triggers family-wide revocation
    - expired token raises UnauthorizedError
    - unknown token raises UnauthorizedError
  logout:
    - active token is revoked
    - already-revoked token is no-op
    - unknown token is no-op
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest

from forgeguard.core.exceptions import UnauthorizedError
from forgeguard.core.security import hash_password, hash_refresh_token, verify_password
from forgeguard.services.auth import AuthService
from tests.fixtures.tokens import (
    DEMO_USER_ID,
    DEMO_USER_EMAIL,
    DEMO_USER_ROLE,
    TEST_JWT_SECRET,
    make_refresh_token_hash,
    make_refresh_token_row,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_VALID_PASSWORD = "Str0ng!P@ssword1"


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


def _make_service(user_row=None, rt_row=None, create_returns=None):
    """Return AuthService with AsyncMock repos pre-configured."""
    user_repo = AsyncMock()
    rt_repo = AsyncMock()

    user_repo.find_by_email.return_value = user_row
    user_repo.get_by_id.return_value = user_row

    if rt_row is not None:
        rt_repo.get_active_by_hash.return_value = rt_row
        rt_repo.get_by_hash.return_value = rt_row
    else:
        rt_repo.get_active_by_hash.return_value = None
        rt_repo.get_by_hash.return_value = None

    if create_returns is not None:
        rt_repo.create.return_value = create_returns
    else:
        rt_repo.create.return_value = make_refresh_token_row()

    rt_repo.revoke.return_value = None
    rt_repo.revoke_all_for_user.return_value = 3

    return AuthService(user_repo, rt_repo, jwt_secret=TEST_JWT_SECRET), user_repo, rt_repo


# ---------------------------------------------------------------------------
# authenticate_user — success
# ---------------------------------------------------------------------------

class TestAuthenticateUserSuccess:
    async def test_returns_three_tuple(self):
        row = _make_user_row()
        service, _, _ = _make_service(user_row=row)
        result = await service.authenticate_user(DEMO_USER_EMAIL, _VALID_PASSWORD)
        assert isinstance(result, tuple)
        assert len(result) == 3

    async def test_login_response_has_correct_email(self):
        row = _make_user_row()
        service, _, _ = _make_service(user_row=row)
        login_resp, _, _ = await service.authenticate_user(DEMO_USER_EMAIL, _VALID_PASSWORD)
        assert login_resp.email == DEMO_USER_EMAIL

    async def test_access_token_is_non_empty_string(self):
        row = _make_user_row()
        service, _, _ = _make_service(user_row=row)
        _, access_token, _ = await service.authenticate_user(DEMO_USER_EMAIL, _VALID_PASSWORD)
        assert isinstance(access_token, str)
        assert len(access_token) > 0

    async def test_raw_refresh_token_is_non_empty_string(self):
        row = _make_user_row()
        service, _, _ = _make_service(user_row=row)
        _, _, raw_refresh = await service.authenticate_user(DEMO_USER_EMAIL, _VALID_PASSWORD)
        assert isinstance(raw_refresh, str)
        assert len(raw_refresh) > 0

    async def test_refresh_token_persisted_as_hash(self):
        row = _make_user_row()
        service, _, rt_repo = _make_service(user_row=row)
        _, _, raw_refresh = await service.authenticate_user(DEMO_USER_EMAIL, _VALID_PASSWORD)
        rt_repo.create.assert_awaited_once()
        call_kwargs = rt_repo.create.call_args
        stored_hash = call_kwargs.kwargs.get("token_hash") or call_kwargs.args[1] if call_kwargs.args else None
        if stored_hash is None:
            # keyword arguments
            stored_hash = rt_repo.create.call_args.kwargs["token_hash"]
        assert stored_hash == hash_refresh_token(raw_refresh)

    async def test_raw_password_not_in_access_token(self):
        from forgeguard.core.security import decode_access_token  # noqa: PLC0415

        row = _make_user_row()
        service, _, _ = _make_service(user_row=row)
        _, access_token, _ = await service.authenticate_user(DEMO_USER_EMAIL, _VALID_PASSWORD)
        payload = decode_access_token(access_token, TEST_JWT_SECRET)
        assert _VALID_PASSWORD not in str(payload.values())
        assert DEMO_USER_EMAIL not in str(payload.values())


# ---------------------------------------------------------------------------
# authenticate_user — failure cases
# ---------------------------------------------------------------------------

class TestAuthenticateUserFailures:
    async def test_wrong_password_raises_unauthorized(self):
        row = _make_user_row()
        service, _, _ = _make_service(user_row=row)
        with pytest.raises(UnauthorizedError):
            await service.authenticate_user(DEMO_USER_EMAIL, "WrongPassword!")

    async def test_non_existent_user_raises_unauthorized(self):
        service, _, _ = _make_service(user_row=None)
        with pytest.raises(UnauthorizedError):
            await service.authenticate_user("nobody@example.com", _VALID_PASSWORD)

    async def test_wrong_password_has_generic_message(self):
        row = _make_user_row()
        service, _, _ = _make_service(user_row=row)
        with pytest.raises(UnauthorizedError) as exc_info:
            await service.authenticate_user(DEMO_USER_EMAIL, "WrongPassword!")
        assert "Invalid email or password" in str(exc_info.value)

    async def test_non_existent_user_has_same_generic_message(self):
        service, _, _ = _make_service(user_row=None)
        with pytest.raises(UnauthorizedError) as exc_info:
            await service.authenticate_user("nobody@example.com", _VALID_PASSWORD)
        assert "Invalid email or password" in str(exc_info.value)

    async def test_inactive_account_raises_unauthorized(self):
        row = _make_user_row(is_active=False)
        service, _, _ = _make_service(user_row=row)
        with pytest.raises(UnauthorizedError):
            await service.authenticate_user(DEMO_USER_EMAIL, _VALID_PASSWORD)

    async def test_locked_account_raises_unauthorized(self):
        future = datetime.now(tz=timezone.utc) + timedelta(hours=1)
        row = _make_user_row(locked_until=future)
        service, _, _ = _make_service(user_row=row)
        with pytest.raises(UnauthorizedError):
            await service.authenticate_user(DEMO_USER_EMAIL, _VALID_PASSWORD)

    async def test_expired_lock_allows_login(self):
        past = datetime.now(tz=timezone.utc) - timedelta(hours=1)
        row = _make_user_row(locked_until=past)
        service, _, _ = _make_service(user_row=row)
        result = await service.authenticate_user(DEMO_USER_EMAIL, _VALID_PASSWORD)
        assert result is not None

    async def test_verify_password_called_for_missing_user(self):
        """Timing-safe: verify_password must run even when user doesn't exist."""
        service, user_repo, _ = _make_service(user_row=None)
        with patch("forgeguard.services.auth.verify_password") as mock_vp:
            mock_vp.return_value = False
            try:
                await service.authenticate_user("ghost@example.com", "pass")
            except UnauthorizedError:
                pass
        mock_vp.assert_called_once()


# ---------------------------------------------------------------------------
# refresh_tokens
# ---------------------------------------------------------------------------

class TestRefreshTokens:
    async def test_success_returns_two_strings(self):
        import secrets  # noqa: PLC0415

        raw = secrets.token_urlsafe(64)
        token_row = make_refresh_token_row(token_hash=hash_refresh_token(raw))
        user_row = _make_user_row()
        service, _, rt_repo = _make_service(user_row=user_row, rt_row=token_row)
        # get_by_hash should return the same row (not revoked)
        rt_repo.get_by_hash.return_value = token_row
        new_token_row = make_refresh_token_row()
        rt_repo.create.return_value = new_token_row

        result = await service.refresh_tokens(raw)
        assert isinstance(result, tuple)
        assert len(result) == 2
        new_access, new_refresh = result
        assert isinstance(new_access, str) and len(new_access) > 0
        assert isinstance(new_refresh, str) and len(new_refresh) > 0

    async def test_reuse_detection_revokes_family(self):
        import secrets  # noqa: PLC0415

        raw = secrets.token_urlsafe(64)
        revoked_row = make_refresh_token_row(
            token_hash=hash_refresh_token(raw),
            revoked_at=datetime.now(tz=timezone.utc) - timedelta(minutes=5),
        )
        user_row = _make_user_row()
        service, _, rt_repo = _make_service(user_row=user_row, rt_row=revoked_row)
        rt_repo.get_by_hash.return_value = revoked_row

        with pytest.raises(UnauthorizedError):
            await service.refresh_tokens(raw)

        rt_repo.revoke_all_for_user.assert_awaited_once()

    async def test_expired_token_raises_unauthorized(self):
        import secrets  # noqa: PLC0415

        raw = secrets.token_urlsafe(64)
        expired_row = make_refresh_token_row(
            token_hash=hash_refresh_token(raw),
            expires_delta=timedelta(seconds=-1),
        )
        user_row = _make_user_row()
        service, _, rt_repo = _make_service(user_row=user_row, rt_row=expired_row)
        rt_repo.get_by_hash.return_value = expired_row

        with pytest.raises(UnauthorizedError):
            await service.refresh_tokens(raw)

    async def test_unknown_token_raises_unauthorized(self):
        import secrets  # noqa: PLC0415

        raw = secrets.token_urlsafe(64)
        service, _, rt_repo = _make_service(user_row=_make_user_row(), rt_row=None)
        rt_repo.get_by_hash.return_value = None

        with pytest.raises(UnauthorizedError):
            await service.refresh_tokens(raw)

    async def test_old_token_revoked_with_replaced_by_id(self):
        import secrets  # noqa: PLC0415

        raw = secrets.token_urlsafe(64)
        old_row = make_refresh_token_row(token_hash=hash_refresh_token(raw))
        new_row = make_refresh_token_row()
        user_row = _make_user_row()
        service, _, rt_repo = _make_service(user_row=user_row, rt_row=old_row)
        rt_repo.get_by_hash.return_value = old_row
        rt_repo.create.return_value = new_row

        await service.refresh_tokens(raw)

        rt_repo.revoke.assert_awaited_once()
        call_kwargs = rt_repo.revoke.call_args.kwargs
        assert "replaced_by_id" in call_kwargs
        assert call_kwargs["replaced_by_id"] == new_row["id"]


# ---------------------------------------------------------------------------
# logout
# ---------------------------------------------------------------------------

class TestLogout:
    async def test_active_token_is_revoked(self):
        import secrets  # noqa: PLC0415

        raw = secrets.token_urlsafe(64)
        row = make_refresh_token_row(token_hash=hash_refresh_token(raw))
        service, _, rt_repo = _make_service(user_row=_make_user_row(), rt_row=row)
        rt_repo.get_by_hash.return_value = row

        await service.logout(raw)
        rt_repo.revoke.assert_awaited_once()

    async def test_already_revoked_token_is_noop(self):
        import secrets  # noqa: PLC0415

        raw = secrets.token_urlsafe(64)
        row = make_refresh_token_row(
            token_hash=hash_refresh_token(raw),
            revoked_at=datetime.now(tz=timezone.utc),
        )
        service, _, rt_repo = _make_service(user_row=_make_user_row(), rt_row=row)
        rt_repo.get_by_hash.return_value = row

        await service.logout(raw)
        rt_repo.revoke.assert_not_awaited()

    async def test_unknown_token_is_noop(self):
        import secrets  # noqa: PLC0415

        raw = secrets.token_urlsafe(64)
        service, _, rt_repo = _make_service(user_row=None, rt_row=None)
        rt_repo.get_by_hash.return_value = None

        await service.logout(raw)
        rt_repo.revoke.assert_not_awaited()
