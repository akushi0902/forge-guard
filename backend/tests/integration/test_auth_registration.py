"""Integration tests for POST /api/v1/auth/register (WO-021).

Tests use the app fixture (no real database) with a mocked UserRepository
injected via FastAPI dependency overrides.

HTTP status scenarios verified:
  201  — valid registration by Platform Admin
  400  — password policy violations (structured violations list)
  403  — non-admin caller
  409  — duplicate email
  422  — invalid role / missing fields / invalid email format
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest
from httpx import ASGITransport, AsyncClient

from forgeguard.core.dependencies import get_user_repository
from forgeguard.core.exceptions import ConflictError
from forgeguard.main import create_app


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_ADMIN_HEADERS = {"X-User-Role": "platform_admin"}
_REGISTER_URL = "/api/v1/auth/register"

_VALID_BODY = {
    "email": "newuser@example.com",
    "name": "New User",
    "password": "Str0ng!P@ssword1",
    "role": "developer",
}


def _fake_created_row(body: dict) -> dict:
    return {
        "id": uuid.uuid4(),
        "email": body["email"],
        "name_encrypted": body["name"].encode("utf-8"),
        "password_hash": "$2b$12$fakehash",
        "role": body["role"],
        "is_active": True,
        "failed_login_attempts": 0,
        "locked_until": None,
        "created_at": datetime.now(tz=timezone.utc),
        "updated_at": datetime.now(tz=timezone.utc),
        "deleted_at": None,
    }


def _make_app(*, existing_email: str | None = None, create_raises: Exception | None = None):
    """Return a FastAPI app with mocked UserRepository override."""
    import forgeguard.core.config as config_module  # noqa: PLC0415
    from forgeguard.core.config import Settings  # noqa: PLC0415

    settings = Settings(
        database_url="postgresql+asyncpg://postgres:postgres@localhost:5432/forgeguard_test",
        jwt_secret_key="test-secret",
        log_level="DEBUG",
        app_env="testing",
        llm_api_key="",
        forge_catalog_url="http://localhost:9999/catalog",
    )
    config_module._settings_cache = settings

    app = create_app()

    mock_repo = AsyncMock()
    if existing_email:
        async def _find_by_email(email: str):
            if email == existing_email:
                return {"id": uuid.uuid4(), "email": email}
            return None
        mock_repo.find_by_email.side_effect = _find_by_email
    else:
        mock_repo.find_by_email.return_value = None

    if create_raises:
        mock_repo.create.side_effect = create_raises
    else:
        async def _create(data: dict) -> dict:
            return _fake_created_row({
                "email": data["email"],
                "name": data.get("name_encrypted", b"").decode("utf-8", errors="replace"),
                "role": data["role"],
            })
        mock_repo.create.side_effect = _create

    app.dependency_overrides[get_user_repository] = lambda: mock_repo
    return app


# ---------------------------------------------------------------------------
# 201 Created
# ---------------------------------------------------------------------------

class TestRegistrationSuccess:
    async def test_valid_request_returns_201(self):
        app = _make_app()
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://testserver"
        ) as client:
            resp = await client.post(_REGISTER_URL, json=_VALID_BODY, headers=_ADMIN_HEADERS)
        assert resp.status_code == 201

    async def test_response_contains_user_id(self):
        app = _make_app()
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://testserver"
        ) as client:
            resp = await client.post(_REGISTER_URL, json=_VALID_BODY, headers=_ADMIN_HEADERS)
        body = resp.json()
        assert "id" in body

    async def test_response_contains_email(self):
        app = _make_app()
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://testserver"
        ) as client:
            resp = await client.post(_REGISTER_URL, json=_VALID_BODY, headers=_ADMIN_HEADERS)
        assert resp.json()["email"] == "newuser@example.com"

    async def test_response_does_not_contain_password_hash(self):
        app = _make_app()
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://testserver"
        ) as client:
            resp = await client.post(_REGISTER_URL, json=_VALID_BODY, headers=_ADMIN_HEADERS)
        assert "password_hash" not in resp.json()
        assert "password" not in resp.json()

    async def test_response_is_active_true(self):
        app = _make_app()
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://testserver"
        ) as client:
            resp = await client.post(_REGISTER_URL, json=_VALID_BODY, headers=_ADMIN_HEADERS)
        assert resp.json()["is_active"] is True

    async def test_all_six_roles_accepted(self):
        roles = [
            "developer", "tech_lead", "security_reviewer",
            "platform_admin", "engineering_manager", "operator",
        ]
        for role in roles:
            app = _make_app()
            body = {**_VALID_BODY, "email": f"{role}@example.com", "role": role}
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://testserver"
            ) as client:
                resp = await client.post(_REGISTER_URL, json=body, headers=_ADMIN_HEADERS)
            assert resp.status_code == 201, f"role={role}: {resp.json()}"


# ---------------------------------------------------------------------------
# 400 Password policy violation
# ---------------------------------------------------------------------------

class TestPasswordPolicyViolations:
    async def test_short_password_returns_400(self):
        app = _make_app()
        body = {**_VALID_BODY, "password": "Short1!"}
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://testserver"
        ) as client:
            resp = await client.post(_REGISTER_URL, json=body, headers=_ADMIN_HEADERS)
        assert resp.status_code == 400

    async def test_400_contains_violations_list(self):
        app = _make_app()
        body = {**_VALID_BODY, "password": "short"}
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://testserver"
        ) as client:
            resp = await client.post(_REGISTER_URL, json=body, headers=_ADMIN_HEADERS)
        data = resp.json()
        assert "violations" in data
        assert isinstance(data["violations"], list)
        assert len(data["violations"]) > 0

    async def test_400_contains_detail_field(self):
        app = _make_app()
        body = {**_VALID_BODY, "password": "short"}
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://testserver"
        ) as client:
            resp = await client.post(_REGISTER_URL, json=body, headers=_ADMIN_HEADERS)
        assert "detail" in resp.json()

    async def test_missing_uppercase_returns_400(self):
        app = _make_app()
        body = {**_VALID_BODY, "password": "nouppercase1!"}
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://testserver"
        ) as client:
            resp = await client.post(_REGISTER_URL, json=body, headers=_ADMIN_HEADERS)
        assert resp.status_code == 400

    async def test_missing_special_char_returns_400(self):
        app = _make_app()
        body = {**_VALID_BODY, "password": "NoSpecialChar1A"}
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://testserver"
        ) as client:
            resp = await client.post(_REGISTER_URL, json=body, headers=_ADMIN_HEADERS)
        assert resp.status_code == 400

    async def test_all_violations_returned_simultaneously(self):
        app = _make_app()
        body = {**_VALID_BODY, "password": "short"}  # fails length + uppercase + digit + special
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://testserver"
        ) as client:
            resp = await client.post(_REGISTER_URL, json=body, headers=_ADMIN_HEADERS)
        violations = resp.json().get("violations", [])
        assert len(violations) >= 3


# ---------------------------------------------------------------------------
# 403 Forbidden — non-admin caller
# ---------------------------------------------------------------------------

class TestForbiddenForNonAdmin:
    @pytest.mark.parametrize("role", [
        "developer", "tech_lead", "security_reviewer",
        "engineering_manager", "operator", "",
    ])
    async def test_non_admin_role_returns_403(self, role: str):
        app = _make_app()
        headers = {"X-User-Role": role} if role else {}
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://testserver"
        ) as client:
            resp = await client.post(_REGISTER_URL, json=_VALID_BODY, headers=headers)
        assert resp.status_code == 403

    async def test_missing_role_header_returns_403(self):
        app = _make_app()
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://testserver"
        ) as client:
            resp = await client.post(_REGISTER_URL, json=_VALID_BODY)
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# 409 Conflict — duplicate email
# ---------------------------------------------------------------------------

class TestDuplicateEmail:
    async def test_duplicate_email_returns_409(self):
        app = _make_app(existing_email="newuser@example.com")
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://testserver"
        ) as client:
            resp = await client.post(_REGISTER_URL, json=_VALID_BODY, headers=_ADMIN_HEADERS)
        assert resp.status_code == 409

    async def test_409_body_mentions_email(self):
        app = _make_app(existing_email="newuser@example.com")
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://testserver"
        ) as client:
            resp = await client.post(_REGISTER_URL, json=_VALID_BODY, headers=_ADMIN_HEADERS)
        body_text = str(resp.json()).lower()
        assert "email" in body_text


# ---------------------------------------------------------------------------
# 422 Unprocessable Entity — schema validation
# ---------------------------------------------------------------------------

class TestSchemaValidation:
    async def test_invalid_role_returns_422(self):
        app = _make_app()
        body = {**_VALID_BODY, "role": "superuser"}
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://testserver"
        ) as client:
            resp = await client.post(_REGISTER_URL, json=body, headers=_ADMIN_HEADERS)
        assert resp.status_code == 422

    async def test_missing_email_returns_422(self):
        app = _make_app()
        body = {k: v for k, v in _VALID_BODY.items() if k != "email"}
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://testserver"
        ) as client:
            resp = await client.post(_REGISTER_URL, json=body, headers=_ADMIN_HEADERS)
        assert resp.status_code == 422

    async def test_invalid_email_format_returns_422(self):
        app = _make_app()
        body = {**_VALID_BODY, "email": "not-an-email"}
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://testserver"
        ) as client:
            resp = await client.post(_REGISTER_URL, json=body, headers=_ADMIN_HEADERS)
        assert resp.status_code == 422

    async def test_missing_password_returns_422(self):
        app = _make_app()
        body = {k: v for k, v in _VALID_BODY.items() if k != "password"}
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://testserver"
        ) as client:
            resp = await client.post(_REGISTER_URL, json=body, headers=_ADMIN_HEADERS)
        assert resp.status_code == 422

    async def test_missing_name_returns_422(self):
        app = _make_app()
        body = {k: v for k, v in _VALID_BODY.items() if k != "name"}
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://testserver"
        ) as client:
            resp = await client.post(_REGISTER_URL, json=body, headers=_ADMIN_HEADERS)
        assert resp.status_code == 422

    async def test_extra_field_returns_422(self):
        app = _make_app()
        body = {**_VALID_BODY, "unexpected_field": "value"}
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://testserver"
        ) as client:
            resp = await client.post(_REGISTER_URL, json=body, headers=_ADMIN_HEADERS)
        assert resp.status_code == 422
