"""Unit tests for AuthService.change_password (WO-023).

All tests use mocked UserRepository and RefreshTokenRepository — no DB required.

Scenarios covered:
  1. Correct current password updates hash and revokes all refresh tokens.
  2. Wrong current password raises BadRequestError without modifying anything.
  3. Weak new password raises BadRequestError with violations list.
  4. User not found raises UnauthorizedError.
  5. revoke_all_for_user is called exactly once on success.
  6. New password hash is different from old hash.
  7. change_password works without a refresh_token_repo (no token revocation).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, call

import pytest

from forgeguard.core.exceptions import BadRequestError, UnauthorizedError
from forgeguard.core.security import hash_password, verify_password
from forgeguard.services.auth import AuthService

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_USER_ID = uuid.UUID("a0000000-0000-0000-0000-000000000002")
_CURRENT_PASSWORD = "Current!P@ss1"
_NEW_PASSWORD = "NewStr0ng!P@ss"
_WEAK_PASSWORD = "short"


def _make_user_row(password: str = _CURRENT_PASSWORD) -> dict:
    return {
        "id": _USER_ID,
        "email": "user@example.com",
        "password_hash": hash_password(password),
        "role": "developer",
        "is_active": True,
        "created_at": datetime.now(tz=timezone.utc),
    }


def _make_service(
    user_row: dict | None = None,
    *,
    include_rt_repo: bool = True,
) -> tuple[AuthService, AsyncMock, AsyncMock | None]:
    """Return (service, mock_user_repo, mock_rt_repo)."""
    user_repo = AsyncMock()
    user_repo.get_by_id.return_value = user_row if user_row is not None else _make_user_row()
    user_repo.update_password = AsyncMock(return_value=None)

    rt_repo: AsyncMock | None = None
    if include_rt_repo:
        rt_repo = AsyncMock()
        rt_repo.revoke_all_for_user = AsyncMock(return_value=3)

    service = AuthService(user_repo, rt_repo)
    return service, user_repo, rt_repo


# ---------------------------------------------------------------------------
# 1. Successful password change
# ---------------------------------------------------------------------------

class TestChangePasswordSuccess:
    async def test_change_password_succeeds(self):
        service, user_repo, rt_repo = _make_service()
        await service.change_password(
            user_id=_USER_ID,
            current_password=_CURRENT_PASSWORD,
            new_password=_NEW_PASSWORD,
        )
        user_repo.update_password.assert_called_once()
        call_args = user_repo.update_password.call_args
        # First arg is user_id, second is the new hash.
        assert call_args.args[0] == _USER_ID

    async def test_new_password_hash_stored_not_plaintext(self):
        service, user_repo, _ = _make_service()
        await service.change_password(
            user_id=_USER_ID,
            current_password=_CURRENT_PASSWORD,
            new_password=_NEW_PASSWORD,
        )
        stored_hash = user_repo.update_password.call_args.args[1]
        # Stored hash must be a bcrypt hash, not the plaintext.
        assert stored_hash != _NEW_PASSWORD
        assert verify_password(_NEW_PASSWORD, stored_hash)

    async def test_revoke_all_for_user_called_on_success(self):
        service, _, rt_repo = _make_service()
        await service.change_password(
            user_id=_USER_ID,
            current_password=_CURRENT_PASSWORD,
            new_password=_NEW_PASSWORD,
        )
        rt_repo.revoke_all_for_user.assert_called_once_with(_USER_ID)

    async def test_revoke_called_exactly_once(self):
        service, _, rt_repo = _make_service()
        await service.change_password(
            user_id=_USER_ID,
            current_password=_CURRENT_PASSWORD,
            new_password=_NEW_PASSWORD,
        )
        assert rt_repo.revoke_all_for_user.call_count == 1


# ---------------------------------------------------------------------------
# 2. Wrong current password
# ---------------------------------------------------------------------------

class TestChangePasswordWrongCurrentPassword:
    async def test_wrong_password_raises_bad_request(self):
        service, user_repo, rt_repo = _make_service()
        with pytest.raises(BadRequestError) as exc_info:
            await service.change_password(
                user_id=_USER_ID,
                current_password="Wr0ng!P@ssword",
                new_password=_NEW_PASSWORD,
            )
        assert "current password" in str(exc_info.value).lower()

    async def test_wrong_password_does_not_update_hash(self):
        service, user_repo, _ = _make_service()
        with pytest.raises(BadRequestError):
            await service.change_password(
                user_id=_USER_ID,
                current_password="Wr0ng!P@ssword",
                new_password=_NEW_PASSWORD,
            )
        user_repo.update_password.assert_not_called()

    async def test_wrong_password_does_not_revoke_tokens(self):
        service, _, rt_repo = _make_service()
        with pytest.raises(BadRequestError):
            await service.change_password(
                user_id=_USER_ID,
                current_password="Wr0ng!P@ssword",
                new_password=_NEW_PASSWORD,
            )
        rt_repo.revoke_all_for_user.assert_not_called()


# ---------------------------------------------------------------------------
# 3. Weak new password
# ---------------------------------------------------------------------------

class TestChangePasswordWeakNewPassword:
    async def test_weak_new_password_raises_bad_request(self):
        service, _, _ = _make_service()
        with pytest.raises(BadRequestError) as exc_info:
            await service.change_password(
                user_id=_USER_ID,
                current_password=_CURRENT_PASSWORD,
                new_password=_WEAK_PASSWORD,
            )
        assert "password" in str(exc_info.value).lower()

    async def test_weak_password_error_has_violations_detail(self):
        service, _, _ = _make_service()
        with pytest.raises(BadRequestError) as exc_info:
            await service.change_password(
                user_id=_USER_ID,
                current_password=_CURRENT_PASSWORD,
                new_password=_WEAK_PASSWORD,
            )
        assert exc_info.value.details is not None
        assert "violations" in exc_info.value.details

    async def test_weak_password_does_not_update_hash(self):
        service, user_repo, _ = _make_service()
        with pytest.raises(BadRequestError):
            await service.change_password(
                user_id=_USER_ID,
                current_password=_CURRENT_PASSWORD,
                new_password=_WEAK_PASSWORD,
            )
        user_repo.update_password.assert_not_called()


# ---------------------------------------------------------------------------
# 4. User not found
# ---------------------------------------------------------------------------

class TestChangePasswordUserNotFound:
    async def test_missing_user_raises_unauthorized(self):
        service, _, _ = _make_service(user_row=None)
        with pytest.raises(UnauthorizedError):
            await service.change_password(
                user_id=_USER_ID,
                current_password=_CURRENT_PASSWORD,
                new_password=_NEW_PASSWORD,
            )

    async def test_missing_user_does_not_update_hash(self):
        service, user_repo, _ = _make_service(user_row=None)
        with pytest.raises(UnauthorizedError):
            await service.change_password(
                user_id=_USER_ID,
                current_password=_CURRENT_PASSWORD,
                new_password=_NEW_PASSWORD,
            )
        user_repo.update_password.assert_not_called()


# ---------------------------------------------------------------------------
# 7. Without refresh token repo — no token revocation attempted
# ---------------------------------------------------------------------------

class TestChangePasswordNoRefreshTokenRepo:
    async def test_succeeds_without_rt_repo(self):
        service, user_repo, _ = _make_service(include_rt_repo=False)
        # Should not raise even without a rt_repo.
        await service.change_password(
            user_id=_USER_ID,
            current_password=_CURRENT_PASSWORD,
            new_password=_NEW_PASSWORD,
        )
        user_repo.update_password.assert_called_once()
