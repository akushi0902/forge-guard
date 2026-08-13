"""Integration tests for GDPR data subject rights endpoints (WO-034).

Uses ASGI TestClient with dependency overrides — no real database required.

Routes under test:
  GET    /api/v1/users/me/data              — Article 15: access
  GET    /api/v1/users/me/data?export=true  — Article 20: portability
  PATCH  /api/v1/users/me/data              — Article 16: rectification
  DELETE /api/v1/users/me/data              — Article 17: erasure

Scenarios:
  - GET /data returns 200 with profile and related_records
  - GET /data?export=true returns 200 with attachment Content-Disposition
  - GET /data returns 401 when no access_token cookie
  - PATCH /data returns 200 on valid request
  - PATCH /data returns 400 when no fields supplied
  - PATCH /data returns 409 on duplicate email
  - DELETE /data returns 204 on success
  - DELETE /data returns 409 for last Platform Admin
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient

from forgeguard.api.dependencies.auth import CurrentUser, get_current_user
from forgeguard.core.config import Settings
from forgeguard.core.dependencies import get_data_subject_service
from forgeguard.core.exceptions import BadRequestError, ConflictError
from forgeguard.main import create_app

# ---------------------------------------------------------------------------
# Test constants
# ---------------------------------------------------------------------------

_TEST_USER_ID = uuid.UUID("b1000000-0000-0000-0000-000000000001")
_TEST_USER_ROLE = "developer"
_TEST_JWT_SECRET = "test-jwt-secret-key-for-unit-tests-only-never-production"

_DATA_URL = "/api/v1/users/me/data"


def _utcnow() -> datetime:
    return datetime.now(tz=timezone.utc)


# ---------------------------------------------------------------------------
# App factory helpers
# ---------------------------------------------------------------------------

def _make_settings() -> Settings:
    import forgeguard.core.config as config_module  # noqa: PLC0415

    settings = Settings(
        database_url="postgresql+asyncpg://postgres:postgres@localhost:5432/forgeguard_test",
        jwt_secret_key=_TEST_JWT_SECRET,
        log_level="DEBUG",
        app_env="testing",
        llm_api_key="",
        forge_catalog_url="http://localhost:9999/catalog",
    )
    config_module._settings_cache = settings
    return settings


def _make_profile_dict(
    *,
    user_id: uuid.UUID = _TEST_USER_ID,
    email: str = "alice@example.com",
    name: str = "Alice",
    role: str = _TEST_USER_ROLE,
) -> dict:
    return {
        "id": user_id,
        "email": email,
        "name": name,
        "role": role,
        "created_at": _utcnow(),
        "related_records": {
            "audit_log_count": 3,
            "assessments_count": 1,
            "decisions_count": 0,
        },
    }


def _make_app(*, service_mock=None, user: CurrentUser | None = None):
    """Return a test FastAPI application with mocked data subject service.

    Args:
        service_mock: Optional mock DataSubjectService. Created empty if None.
        user:         CurrentUser to inject. Defaults to _TEST_USER_ID / developer.
    """
    _make_settings()
    app = create_app()

    current_user = user or CurrentUser(user_id=_TEST_USER_ID, role=_TEST_USER_ROLE)
    app.dependency_overrides[get_current_user] = lambda: current_user

    if service_mock is not None:
        app.dependency_overrides[get_data_subject_service] = lambda: service_mock

    return app


# ---------------------------------------------------------------------------
# GET /api/v1/users/me/data — Article 15 (access)
# ---------------------------------------------------------------------------

class TestGetUserData:
    async def test_returns_200_with_profile(self):
        profile = _make_profile_dict()
        svc = AsyncMock()
        svc.access_data = AsyncMock(return_value=profile)
        app = _make_app(service_mock=svc)

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as c:
            resp = await c.get(_DATA_URL)

        assert resp.status_code == 200
        body = resp.json()
        assert body["data"]["email"] == "alice@example.com"
        assert body["data"]["related_records"]["audit_log_count"] == 3

    async def test_calls_access_data_with_user_id(self):
        profile = _make_profile_dict()
        svc = AsyncMock()
        svc.access_data = AsyncMock(return_value=profile)
        app = _make_app(service_mock=svc)

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as c:
            await c.get(_DATA_URL)

        svc.access_data.assert_called_once_with(_TEST_USER_ID)

    async def test_returns_401_when_unauthenticated(self):
        app = _make_app()
        # Remove the auth override to exercise the real dependency path
        del app.dependency_overrides[get_current_user]

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as c:
            resp = await c.get(_DATA_URL)

        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# GET /api/v1/users/me/data?export=true — Article 20 (portability)
# ---------------------------------------------------------------------------

class TestExportUserData:
    async def test_returns_200_with_attachment(self):
        export_payload = {
            "profile": {
                "id": str(_TEST_USER_ID),
                "email": "alice@example.com",
                "name": "Alice",
                "role": "developer",
                "created_at": _utcnow().isoformat(),
            },
            "audit_logs": [],
            "assessments": [],
            "decisions": [],
        }
        svc = AsyncMock()
        svc.export_data = AsyncMock(return_value=export_payload)
        app = _make_app(service_mock=svc)

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as c:
            resp = await c.get(_DATA_URL, params={"export": "true"})

        assert resp.status_code == 200
        assert "attachment" in resp.headers.get("content-disposition", "")
        assert "user-data-export" in resp.headers.get("content-disposition", "")

    async def test_export_calls_export_data_with_user_id(self):
        svc = AsyncMock()
        svc.export_data = AsyncMock(return_value={
            "profile": {"id": str(_TEST_USER_ID), "email": "x@x.com", "name": None, "role": "developer", "created_at": "2026-01-01T00:00:00"},
            "audit_logs": [],
            "assessments": [],
            "decisions": [],
        })
        app = _make_app(service_mock=svc)

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as c:
            await c.get(_DATA_URL, params={"export": "true"})

        svc.export_data.assert_called_once_with(_TEST_USER_ID)


# ---------------------------------------------------------------------------
# PATCH /api/v1/users/me/data — Article 16 (rectification)
# ---------------------------------------------------------------------------

class TestRectifyUserData:
    def _make_rectify_result(self, email="new@example.com", name="Alice Updated") -> dict:
        return {
            "id": _TEST_USER_ID,
            "email": email,
            "name": name,
            "role": _TEST_USER_ROLE,
            "updated_at": _utcnow(),
        }

    async def test_returns_200_on_valid_email_update(self):
        svc = AsyncMock()
        svc.rectify_data = AsyncMock(return_value=self._make_rectify_result())
        app = _make_app(service_mock=svc)

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as c:
            resp = await c.patch(_DATA_URL, json={"email": "new@example.com"})

        assert resp.status_code == 200
        body = resp.json()
        assert body["email"] == "new@example.com"

    async def test_returns_400_when_no_fields(self):
        svc = AsyncMock()
        svc.rectify_data = AsyncMock(side_effect=BadRequestError("At least one field"))
        app = _make_app(service_mock=svc)

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as c:
            resp = await c.patch(_DATA_URL, json={})

        assert resp.status_code == 400

    async def test_returns_409_on_duplicate_email(self):
        svc = AsyncMock()
        svc.rectify_data = AsyncMock(
            side_effect=ConflictError("Email address is already in use by another account.")
        )
        app = _make_app(service_mock=svc)

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as c:
            resp = await c.patch(_DATA_URL, json={"email": "taken@example.com"})

        assert resp.status_code == 409

    async def test_passes_role_to_service(self):
        svc = AsyncMock()
        svc.rectify_data = AsyncMock(return_value=self._make_rectify_result())
        app = _make_app(service_mock=svc)

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as c:
            await c.patch(_DATA_URL, json={"name": "Bob"})

        _, role, *_ = svc.rectify_data.call_args.args
        assert role == _TEST_USER_ROLE


# ---------------------------------------------------------------------------
# DELETE /api/v1/users/me/data — Article 17 (erasure)
# ---------------------------------------------------------------------------

class TestEraseUserData:
    async def test_returns_204_on_success(self):
        svc = AsyncMock()
        svc.erase_data = AsyncMock(return_value=None)
        app = _make_app(service_mock=svc)

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as c:
            resp = await c.delete(_DATA_URL)

        assert resp.status_code == 204

    async def test_returns_409_for_last_admin(self):
        svc = AsyncMock()
        svc.erase_data = AsyncMock(
            side_effect=ConflictError("Cannot erase the last active Platform Admin.")
        )
        app = _make_app(service_mock=svc)

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as c:
            resp = await c.delete(_DATA_URL)

        assert resp.status_code == 409

    async def test_returns_401_when_unauthenticated(self):
        app = _make_app()
        del app.dependency_overrides[get_current_user]

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as c:
            resp = await c.delete(_DATA_URL)

        assert resp.status_code == 401

    async def test_calls_erase_with_user_id_and_role(self):
        svc = AsyncMock()
        svc.erase_data = AsyncMock(return_value=None)
        user = CurrentUser(user_id=_TEST_USER_ID, role="tech_lead")
        app = _make_app(service_mock=svc, user=user)

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as c:
            await c.delete(_DATA_URL)

        svc.erase_data.assert_called_once_with(_TEST_USER_ID, "tech_lead")
