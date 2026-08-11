"""Unit tests for AuthService.register_user (WO-021).

All tests use a mock UserRepository — no database required.

Scenarios covered:
  - Successful registration returns a UserResponse with correct fields
  - Duplicate email raises ConflictError
  - Service delegates hashing to core/security (never stores plaintext)
  - Invalid role is rejected at the schema layer (Pydantic 422)
  - name_encrypted stored as bytes, decoded back to string in response
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest

from forgeguard.api.schemas.auth import UserRegisterRequest, UserResponse
from forgeguard.core.exceptions import ConflictError
from forgeguard.core.security import verify_password
from forgeguard.services.auth import AuthService


# ---------------------------------------------------------------------------
# Helpers / builders
# ---------------------------------------------------------------------------

def _make_request(**overrides) -> UserRegisterRequest:
    defaults = {
        "email": "alice@example.com",
        "name": "Alice",
        "password": "Str0ng!Password",
        "role": "developer",
    }
    defaults.update(overrides)
    return UserRegisterRequest.model_validate(defaults)


def _make_db_row(request: UserRegisterRequest, hashed: str) -> dict:
    return {
        "id": uuid.uuid4(),
        "email": request.email,
        "name_encrypted": request.name.encode("utf-8"),
        "password_hash": hashed,
        "role": request.role.value,
        "is_active": True,
        "failed_login_attempts": 0,
        "locked_until": None,
        "created_at": datetime.now(tz=timezone.utc),
        "updated_at": datetime.now(tz=timezone.utc),
        "deleted_at": None,
    }


# ---------------------------------------------------------------------------
# Success cases
# ---------------------------------------------------------------------------

class TestRegisterUserSuccess:
    async def test_returns_user_response(self):
        request = _make_request()
        repo = AsyncMock()
        repo.find_by_email.return_value = None

        captured: dict = {}

        async def fake_create(data: dict) -> dict:
            captured.update(data)
            return _make_db_row(request, data["password_hash"])

        repo.create.side_effect = fake_create
        service = AuthService(repo)

        result = await service.register_user(request)

        assert isinstance(result, UserResponse)

    async def test_returned_email_matches_request(self):
        request = _make_request()
        repo = AsyncMock()
        repo.find_by_email.return_value = None

        async def fake_create(data: dict) -> dict:
            return _make_db_row(request, data["password_hash"])

        repo.create.side_effect = fake_create
        service = AuthService(repo)

        result = await service.register_user(request)
        assert result.email == "alice@example.com"

    async def test_returned_role_matches_request(self):
        request = _make_request()
        repo = AsyncMock()
        repo.find_by_email.return_value = None

        async def fake_create(data: dict) -> dict:
            return _make_db_row(request, data["password_hash"])

        repo.create.side_effect = fake_create
        service = AuthService(repo)

        result = await service.register_user(request)
        assert result.role == "developer"

    async def test_is_active_true_on_new_user(self):
        request = _make_request()
        repo = AsyncMock()
        repo.find_by_email.return_value = None

        async def fake_create(data: dict) -> dict:
            return _make_db_row(request, data["password_hash"])

        repo.create.side_effect = fake_create
        service = AuthService(repo)

        result = await service.register_user(request)
        assert result.is_active is True

    async def test_name_decoded_from_bytes(self):
        request = _make_request(name="Bob Smith")
        repo = AsyncMock()
        repo.find_by_email.return_value = None

        async def fake_create(data: dict) -> dict:
            return _make_db_row(request, data["password_hash"])

        repo.create.side_effect = fake_create
        service = AuthService(repo)

        result = await service.register_user(request)
        assert result.name == "Bob Smith"

    async def test_find_by_email_called_with_email(self):
        request = _make_request(email="check@example.com")
        repo = AsyncMock()
        repo.find_by_email.return_value = None

        async def fake_create(data: dict) -> dict:
            return _make_db_row(request, data["password_hash"])

        repo.create.side_effect = fake_create
        service = AuthService(repo)

        await service.register_user(request)
        repo.find_by_email.assert_awaited_once_with("check@example.com")


# ---------------------------------------------------------------------------
# Password hashing contract
# ---------------------------------------------------------------------------

class TestPasswordHashingContract:
    async def test_raw_password_not_stored(self):
        request = _make_request(password="Str0ng!Password")
        repo = AsyncMock()
        repo.find_by_email.return_value = None

        captured: dict = {}

        async def fake_create(data: dict) -> dict:
            captured.update(data)
            return _make_db_row(request, data["password_hash"])

        repo.create.side_effect = fake_create
        service = AuthService(repo)
        await service.register_user(request)

        assert "Str0ng!Password" not in captured.get("password_hash", "")

    async def test_stored_hash_verifies_against_original_password(self):
        plain = "Str0ng!Password"
        request = _make_request(password=plain)
        repo = AsyncMock()
        repo.find_by_email.return_value = None

        captured: dict = {}

        async def fake_create(data: dict) -> dict:
            captured.update(data)
            return _make_db_row(request, data["password_hash"])

        repo.create.side_effect = fake_create
        service = AuthService(repo)
        await service.register_user(request)

        assert verify_password(plain, captured["password_hash"])

    async def test_name_stored_as_bytes(self):
        request = _make_request(name="Charlie")
        repo = AsyncMock()
        repo.find_by_email.return_value = None

        captured: dict = {}

        async def fake_create(data: dict) -> dict:
            captured.update(data)
            return _make_db_row(request, data["password_hash"])

        repo.create.side_effect = fake_create
        service = AuthService(repo)
        await service.register_user(request)

        assert isinstance(captured.get("name_encrypted"), bytes)
        assert captured["name_encrypted"] == b"Charlie"


# ---------------------------------------------------------------------------
# Duplicate email
# ---------------------------------------------------------------------------

class TestDuplicateEmailRejection:
    async def test_duplicate_email_raises_conflict_error(self):
        request = _make_request()
        existing_row = {"id": uuid.uuid4(), "email": "alice@example.com"}
        repo = AsyncMock()
        repo.find_by_email.return_value = existing_row

        service = AuthService(repo)
        with pytest.raises(ConflictError):
            await service.register_user(request)

    async def test_duplicate_email_does_not_call_create(self):
        request = _make_request()
        repo = AsyncMock()
        repo.find_by_email.return_value = {"id": uuid.uuid4(), "email": "alice@example.com"}

        service = AuthService(repo)
        with pytest.raises(ConflictError):
            await service.register_user(request)

        repo.create.assert_not_awaited()

    async def test_conflict_error_message_contains_email_hint(self):
        request = _make_request()
        repo = AsyncMock()
        repo.find_by_email.return_value = {"id": uuid.uuid4()}

        service = AuthService(repo)
        with pytest.raises(ConflictError) as exc_info:
            await service.register_user(request)

        assert "email" in str(exc_info.value).lower()


# ---------------------------------------------------------------------------
# Role validation (Pydantic layer — not the service itself)
# ---------------------------------------------------------------------------

class TestRoleValidation:
    def test_invalid_role_raises_validation_error(self):
        from pydantic import ValidationError  # noqa: PLC0415

        with pytest.raises(ValidationError):
            UserRegisterRequest.model_validate({
                "email": "user@example.com",
                "name": "Test",
                "password": "Str0ng!Password",
                "role": "superuser",  # invalid
            })

    def test_all_six_valid_roles_accepted(self):
        valid_roles = [
            "developer", "tech_lead", "security_reviewer",
            "platform_admin", "engineering_manager", "operator",
        ]
        for role in valid_roles:
            req = UserRegisterRequest.model_validate({
                "email": f"{role}@example.com",
                "name": "Test",
                "password": "Str0ng!Password",
                "role": role,
            })
            assert req.role.value == role
