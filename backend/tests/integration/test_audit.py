"""Integration tests for Audit Logging and Admin Audit API (WO-029).

Tests:
  - GET /api/v1/admin/audit-logs returns 200 for Platform Admin
  - GET /api/v1/admin/audit-logs returns 200 for Security Reviewer
  - GET /api/v1/admin/audit-logs returns 403 for Developer
  - Audit query accepts filters (event_type, actor_id, resource_type)
  - Pagination (limit, next_cursor)
  - AuthService audit calls produce records for login, login_failed,
    token_refresh, logout, password_changed
  - AuditService write failure does not block primary auth operation

No real database required — uses FastAPI dependency overrides.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

import forgeguard.core.config as _config_module
from forgeguard.core.config import Settings
from forgeguard.core.exceptions import NotFoundError
from forgeguard.core.permissions import Permissions, UserRole
from forgeguard.data.repositories.audit_logs import AuditLogRepository
from forgeguard.main import create_app
from forgeguard.services.audit import AuditService
from forgeguard.services.auth import AuthService
from tests.fixtures.audit import (
    ALL_EVENT_TYPES,
    login_event,
    login_failed_event,
    role_change_event,
)
from tests.fixtures.tokens import TEST_JWT_SECRET, make_access_token

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_ADMIN_ID = uuid.uuid4()
_REVIEWER_ID = uuid.uuid4()
_DEV_ID = uuid.uuid4()


def _make_test_settings() -> Settings:
    return Settings(
        database_url="postgresql+asyncpg://postgres:postgres@localhost:5432/forgeguard_test",
        jwt_secret_key=TEST_JWT_SECRET,
        log_level="DEBUG",
        app_env="testing",
        llm_api_key="",
        forge_catalog_url="http://localhost:9999/catalog",
    )


def _token(user_id: uuid.UUID, role: str) -> str:
    return make_access_token(user_id=user_id, role=role, jwt_secret=TEST_JWT_SECRET)


def _make_app_with_mock_repo(mock_repo: AuditLogRepository):
    settings = _make_test_settings()
    _config_module._settings_cache = settings
    app = create_app()

    from forgeguard.api.routes.admin_audit import _get_audit_repo  # noqa: PLC0415

    app.dependency_overrides[_get_audit_repo] = lambda: mock_repo
    return app


def _make_mock_repo(rows: list[dict] | None = None, total: int = 0) -> MagicMock:
    repo = MagicMock(spec=AuditLogRepository)
    repo.query_page = AsyncMock(return_value=rows or [])
    repo.count_query = AsyncMock(return_value=total)
    return repo


# ---------------------------------------------------------------------------
# Tests: GET /api/v1/admin/audit-logs — authorization
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_audit_logs_200_platform_admin():
    """Platform Admin receives audit log results."""
    mock_repo = _make_mock_repo(rows=[login_event()], total=1)
    app = _make_app_with_mock_repo(mock_repo)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get(
            "/api/v1/admin/audit-logs",
            cookies={"access_token": _token(_ADMIN_ID, UserRole.platform_admin.value)},
        )

    assert resp.status_code == 200
    data = resp.json()
    assert "audit_logs" in data
    assert "total_count" in data
    assert data["total_count"] == 1


@pytest.mark.asyncio
async def test_audit_logs_200_security_reviewer():
    """Security Reviewer also has access to audit logs."""
    mock_repo = _make_mock_repo(rows=[role_change_event()], total=1)
    app = _make_app_with_mock_repo(mock_repo)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get(
            "/api/v1/admin/audit-logs",
            cookies={"access_token": _token(_REVIEWER_ID, UserRole.security_reviewer.value)},
        )

    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_audit_logs_403_developer():
    """Developer role is denied access to audit logs."""
    mock_repo = _make_mock_repo()
    app = _make_app_with_mock_repo(mock_repo)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get(
            "/api/v1/admin/audit-logs",
            cookies={"access_token": _token(_DEV_ID, UserRole.developer.value)},
        )

    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Tests: Filtering and pagination
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_audit_logs_filter_by_event_type():
    """event_type query param is forwarded to repository."""
    mock_repo = _make_mock_repo(rows=[login_event()], total=1)
    app = _make_app_with_mock_repo(mock_repo)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get(
            "/api/v1/admin/audit-logs",
            params={"event_type": "auth.login"},
            cookies={"access_token": _token(_ADMIN_ID, UserRole.platform_admin.value)},
        )

    assert resp.status_code == 200
    mock_repo.query_page.assert_awaited_once()
    call_kwargs = mock_repo.query_page.call_args.kwargs
    assert call_kwargs["action"] == "auth.login"


@pytest.mark.asyncio
async def test_audit_logs_pagination_next_cursor():
    """next_cursor is set when more records exist beyond the requested page."""
    now = datetime.now(tz=timezone.utc)
    many_rows = [
        {**login_event(), "created_at": now}
        for _ in range(51)  # limit=50, fetches 51 rows → has_more=True
    ]
    mock_repo = _make_mock_repo(rows=many_rows, total=100)
    app = _make_app_with_mock_repo(mock_repo)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get(
            "/api/v1/admin/audit-logs",
            params={"limit": 50},
            cookies={"access_token": _token(_ADMIN_ID, UserRole.platform_admin.value)},
        )

    assert resp.status_code == 200
    data = resp.json()
    assert len(data["audit_logs"]) == 50
    assert data["next_cursor"] is not None


@pytest.mark.asyncio
async def test_audit_logs_no_cursor_on_last_page():
    """next_cursor is null when all records fit in a single page."""
    rows = [login_event() for _ in range(3)]
    mock_repo = _make_mock_repo(rows=rows, total=3)
    app = _make_app_with_mock_repo(mock_repo)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get(
            "/api/v1/admin/audit-logs",
            cookies={"access_token": _token(_ADMIN_ID, UserRole.platform_admin.value)},
        )

    assert resp.status_code == 200
    assert resp.json()["next_cursor"] is None


@pytest.mark.asyncio
async def test_audit_logs_filter_by_actor_id():
    """actor_id query param is forwarded to repository query."""
    actor = uuid.uuid4()
    mock_repo = _make_mock_repo(rows=[login_event(user_id=actor)], total=1)
    app = _make_app_with_mock_repo(mock_repo)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get(
            "/api/v1/admin/audit-logs",
            params={"actor_id": str(actor)},
            cookies={"access_token": _token(_ADMIN_ID, UserRole.platform_admin.value)},
        )

    assert resp.status_code == 200
    call_kwargs = mock_repo.query_page.call_args.kwargs
    assert str(call_kwargs["actor_id"]) == str(actor)


# ---------------------------------------------------------------------------
# Tests: Auth service audit integration
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_auth_service_login_success_writes_audit():
    """Successful authenticate_user produces an auth.login audit record."""
    import uuid as _uuid  # noqa: PLC0415
    from datetime import datetime as _dt, timezone as _tz  # noqa: PLC0415

    audit_repo = AsyncMock()
    audit_svc = AuditService(audit_repo)
    audit_repo.insert = AsyncMock(return_value={"id": _uuid.uuid4()})

    user_repo = AsyncMock()
    rt_repo = AsyncMock()

    uid = _uuid.uuid4()
    user_row = {
        "id": uid,
        "email": "user@test.com",
        "name_encrypted": b"Test User",
        "password_hash": "$2b$12$GE1YH4mFxBW8yBCwqGBrDuF1K7X4dPkX6FjX5OJw.mWPbHysMQjXK",
        "role": "developer",
        "is_active": True,
        "failed_login_attempts": 0,
        "locked_until": None,
        "created_at": _dt.now(tz=_tz.utc),
    }

    from forgeguard.core.security import hash_password  # noqa: PLC0415
    raw_pw = "Str0ng!Password12"
    user_row["password_hash"] = hash_password(raw_pw)
    user_repo.find_by_email = AsyncMock(return_value=user_row)
    user_repo.reset_failed_attempts = AsyncMock()
    rt_repo.create = AsyncMock(return_value={"id": _uuid.uuid4()})

    from forgeguard.core.config import get_settings  # noqa: PLC0415
    settings = get_settings()

    svc = AuthService(user_repo, rt_repo, jwt_secret=settings.jwt_secret_key, audit_service=audit_svc)
    await svc.authenticate_user("user@test.com", raw_pw, ip_address="192.168.1.1")

    audit_repo.insert.assert_awaited_once()
    inserted = audit_repo.insert.call_args[0][0]
    assert inserted["action"] == "auth.login"
    assert inserted["ip_address_masked"] is not None
    assert "192.168.1" in inserted["ip_address_masked"]


@pytest.mark.asyncio
async def test_auth_service_login_failed_writes_audit():
    """Failed authenticate_user (wrong password) produces auth.login_failed record."""
    import uuid as _uuid  # noqa: PLC0415
    from datetime import datetime as _dt, timezone as _tz  # noqa: PLC0415

    audit_repo = AsyncMock()
    audit_repo.insert = AsyncMock(return_value={"id": _uuid.uuid4()})
    audit_svc = AuditService(audit_repo)

    user_repo = AsyncMock()
    rt_repo = AsyncMock()

    uid = _uuid.uuid4()
    from forgeguard.core.security import hash_password  # noqa: PLC0415
    user_row = {
        "id": uid,
        "email": "user@test.com",
        "name_encrypted": b"Test User",
        "password_hash": hash_password("correctpassword!"),
        "role": "developer",
        "is_active": True,
        "failed_login_attempts": 0,
        "locked_until": None,
        "created_at": _dt.now(tz=_tz.utc),
    }
    user_repo.find_by_email = AsyncMock(return_value=user_row)
    user_repo.increment_failed_attempts = AsyncMock(return_value=1)

    from forgeguard.core.config import get_settings  # noqa: PLC0415
    settings = get_settings()
    svc = AuthService(user_repo, rt_repo, jwt_secret=settings.jwt_secret_key, audit_service=audit_svc)

    from forgeguard.core.exceptions import UnauthorizedError  # noqa: PLC0415
    with pytest.raises(UnauthorizedError):
        await svc.authenticate_user("user@test.com", "wrongpassword!")

    audit_repo.insert.assert_awaited_once()
    inserted = audit_repo.insert.call_args[0][0]
    assert inserted["action"] == "auth.login_failed"


@pytest.mark.asyncio
async def test_auth_service_audit_failure_does_not_block_login():
    """AuditService write error does not cause login to fail."""
    import uuid as _uuid  # noqa: PLC0415
    from datetime import datetime as _dt, timezone as _tz  # noqa: PLC0415

    audit_repo = AsyncMock()
    audit_repo.insert = AsyncMock(side_effect=RuntimeError("DB is down"))
    audit_svc = AuditService(audit_repo)

    user_repo = AsyncMock()
    rt_repo = AsyncMock()

    uid = _uuid.uuid4()
    from forgeguard.core.security import hash_password  # noqa: PLC0415
    raw_pw = "GoodPassword12!"
    user_row = {
        "id": uid,
        "email": "user@test.com",
        "name_encrypted": b"Test User",
        "password_hash": hash_password(raw_pw),
        "role": "developer",
        "is_active": True,
        "failed_login_attempts": 0,
        "locked_until": None,
        "created_at": _dt.now(tz=_tz.utc),
    }
    user_repo.find_by_email = AsyncMock(return_value=user_row)
    user_repo.reset_failed_attempts = AsyncMock()
    rt_repo.create = AsyncMock(return_value={"id": _uuid.uuid4()})

    from forgeguard.core.config import get_settings  # noqa: PLC0415
    settings = get_settings()
    svc = AuthService(user_repo, rt_repo, jwt_secret=settings.jwt_secret_key, audit_service=audit_svc)

    # Login should succeed even though audit write fails
    result = await svc.authenticate_user("user@test.com", raw_pw)
    assert result is not None  # returns (LoginResponse, access_token, refresh_token)
