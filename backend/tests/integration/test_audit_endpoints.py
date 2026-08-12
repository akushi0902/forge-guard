"""Integration tests for GET /api/v1/audit-logs endpoints (WO-031).

Tests:
  - Platform Admin gets 200 on list, get-by-id, and export endpoints
  - Developer gets 403 on all three endpoints
  - Security Reviewer gets 403 (audit.view is Platform Admin only)
  - Unauthenticated request gets 401
  - list: filters forwarded to repository (action, actor_id, resource_type,
    resource_id, date range)
  - list: cursor pagination — next_cursor set when has_more, null on last page
  - list: empty result set returns {data: [], pagination: {cursor: null, ...}}
  - get-by-id: 200 for existing record
  - get-by-id: 404 for missing UUID
  - export: 200 with Content-Disposition header and JSON array body
  - Corrupt cursor returns 400

No real database — uses FastAPI dependency overrides.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient

import forgeguard.core.config as _config_module
from forgeguard.core.config import Settings
from forgeguard.core.permissions import UserRole
from forgeguard.data.repositories.audit_logs import AuditLogRepository
from forgeguard.main import create_app
from tests.fixtures.audit_fixtures import (
    SEEDED_AUDIT_RECORDS,
    generate_diverse_audit_records,
    make_audit_record,
)
from tests.fixtures.tokens import TEST_JWT_SECRET, make_access_token

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_ADMIN_ID = uuid.uuid4()
_DEV_ID = uuid.uuid4()
_REVIEWER_ID = uuid.uuid4()


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

    from forgeguard.api.routes.audit import _get_audit_repo  # noqa: PLC0415

    app.dependency_overrides[_get_audit_repo] = lambda: mock_repo
    return app


def _make_mock_repo(
    rows: list[dict] | None = None,
    total: int = 0,
    single_row: dict | None = None,
) -> MagicMock:
    repo = MagicMock(spec=AuditLogRepository)
    repo.query_with_filters = AsyncMock(return_value=rows or [])
    repo.count_query = AsyncMock(return_value=total)
    repo.get_by_id = AsyncMock(return_value=single_row)

    async def _stream(*args, **kwargs) -> AsyncGenerator[dict, None]:
        for r in rows or []:
            yield r

    repo.stream_records = _stream
    return repo


# ---------------------------------------------------------------------------
# Authorization — list endpoint
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_list_200_platform_admin():
    now = datetime.now(tz=timezone.utc)
    rows = [{**make_audit_record(), "created_at": now, "id": uuid.uuid4()}]
    mock_repo = _make_mock_repo(rows=rows, total=1)
    app = _make_app_with_mock_repo(mock_repo)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get(
            "/api/v1/audit-logs",
            cookies={"access_token": _token(_ADMIN_ID, UserRole.platform_admin.value)},
        )

    assert resp.status_code == 200
    body = resp.json()
    assert "data" in body
    assert "pagination" in body
    assert body["pagination"]["total_estimate"] == 1


@pytest.mark.asyncio
async def test_list_403_developer():
    mock_repo = _make_mock_repo()
    app = _make_app_with_mock_repo(mock_repo)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get(
            "/api/v1/audit-logs",
            cookies={"access_token": _token(_DEV_ID, UserRole.developer.value)},
        )

    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_list_403_security_reviewer():
    mock_repo = _make_mock_repo()
    app = _make_app_with_mock_repo(mock_repo)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get(
            "/api/v1/audit-logs",
            cookies={"access_token": _token(_REVIEWER_ID, UserRole.security_reviewer.value)},
        )

    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_list_401_unauthenticated():
    mock_repo = _make_mock_repo()
    app = _make_app_with_mock_repo(mock_repo)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/v1/audit-logs")

    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# list endpoint — filters
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_list_filter_by_action():
    now = datetime.now(tz=timezone.utc)
    rows = [{**make_audit_record(action="auth.login"), "created_at": now, "id": uuid.uuid4()}]
    mock_repo = _make_mock_repo(rows=rows, total=1)
    app = _make_app_with_mock_repo(mock_repo)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get(
            "/api/v1/audit-logs",
            params={"action": "auth.login"},
            cookies={"access_token": _token(_ADMIN_ID, UserRole.platform_admin.value)},
        )

    assert resp.status_code == 200
    call_kwargs = mock_repo.query_with_filters.call_args.kwargs
    assert call_kwargs["action"] == "auth.login"


@pytest.mark.asyncio
async def test_list_filter_by_actor_id():
    actor = uuid.uuid4()
    now = datetime.now(tz=timezone.utc)
    rows = [{**make_audit_record(), "created_at": now, "id": uuid.uuid4()}]
    mock_repo = _make_mock_repo(rows=rows, total=1)
    app = _make_app_with_mock_repo(mock_repo)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get(
            "/api/v1/audit-logs",
            params={"actor_id": str(actor)},
            cookies={"access_token": _token(_ADMIN_ID, UserRole.platform_admin.value)},
        )

    assert resp.status_code == 200
    call_kwargs = mock_repo.query_with_filters.call_args.kwargs
    assert str(call_kwargs["actor_id"]) == str(actor)


@pytest.mark.asyncio
async def test_list_filter_by_resource_type():
    now = datetime.now(tz=timezone.utc)
    rows = [{**make_audit_record(resource_type="services"), "created_at": now, "id": uuid.uuid4()}]
    mock_repo = _make_mock_repo(rows=rows, total=1)
    app = _make_app_with_mock_repo(mock_repo)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get(
            "/api/v1/audit-logs",
            params={"resource_type": "services"},
            cookies={"access_token": _token(_ADMIN_ID, UserRole.platform_admin.value)},
        )

    assert resp.status_code == 200
    call_kwargs = mock_repo.query_with_filters.call_args.kwargs
    assert call_kwargs["resource_type"] == "services"


@pytest.mark.asyncio
async def test_list_filter_by_resource_id():
    res_id = uuid.uuid4()
    now = datetime.now(tz=timezone.utc)
    rows = [{**make_audit_record(), "created_at": now, "id": uuid.uuid4()}]
    mock_repo = _make_mock_repo(rows=rows, total=1)
    app = _make_app_with_mock_repo(mock_repo)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get(
            "/api/v1/audit-logs",
            params={"resource_id": str(res_id)},
            cookies={"access_token": _token(_ADMIN_ID, UserRole.platform_admin.value)},
        )

    assert resp.status_code == 200
    call_kwargs = mock_repo.query_with_filters.call_args.kwargs
    assert str(call_kwargs["resource_id"]) == str(res_id)


# ---------------------------------------------------------------------------
# list endpoint — pagination
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_list_next_cursor_set_on_has_more():
    """When the repo returns limit+1 rows, next_cursor is set."""
    now = datetime.now(tz=timezone.utc)
    rows = [
        {**make_audit_record(), "created_at": now, "id": uuid.uuid4()}
        for _ in range(51)  # limit=50 → has_more
    ]
    mock_repo = _make_mock_repo(rows=rows, total=100)
    app = _make_app_with_mock_repo(mock_repo)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get(
            "/api/v1/audit-logs",
            params={"limit": 50},
            cookies={"access_token": _token(_ADMIN_ID, UserRole.platform_admin.value)},
        )

    assert resp.status_code == 200
    body = resp.json()
    assert len(body["data"]) == 50
    assert body["pagination"]["has_more"] is True
    assert body["pagination"]["cursor"] is not None


@pytest.mark.asyncio
async def test_list_null_cursor_on_last_page():
    """When the repo returns ≤ limit rows, has_more is False and cursor is null."""
    now = datetime.now(tz=timezone.utc)
    rows = [
        {**make_audit_record(), "created_at": now, "id": uuid.uuid4()}
        for _ in range(3)
    ]
    mock_repo = _make_mock_repo(rows=rows, total=3)
    app = _make_app_with_mock_repo(mock_repo)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get(
            "/api/v1/audit-logs",
            cookies={"access_token": _token(_ADMIN_ID, UserRole.platform_admin.value)},
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["pagination"]["has_more"] is False
    assert body["pagination"]["cursor"] is None


@pytest.mark.asyncio
async def test_list_empty_result():
    """Empty result set returns {data: [], pagination: {cursor: null, has_more: false, total_estimate: 0}}."""
    mock_repo = _make_mock_repo(rows=[], total=0)
    app = _make_app_with_mock_repo(mock_repo)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get(
            "/api/v1/audit-logs",
            cookies={"access_token": _token(_ADMIN_ID, UserRole.platform_admin.value)},
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["data"] == []
    assert body["pagination"]["cursor"] is None
    assert body["pagination"]["has_more"] is False
    assert body["pagination"]["total_estimate"] == 0


@pytest.mark.asyncio
async def test_list_corrupt_cursor_returns_400():
    mock_repo = _make_mock_repo()
    app = _make_app_with_mock_repo(mock_repo)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get(
            "/api/v1/audit-logs",
            params={"cursor": "this-is-not-valid-base64!!!"},
            cookies={"access_token": _token(_ADMIN_ID, UserRole.platform_admin.value)},
        )

    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# get-by-id endpoint
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_by_id_200():
    record_id = uuid.uuid4()
    now = datetime.now(tz=timezone.utc)
    row = {**make_audit_record(), "created_at": now, "id": record_id}
    mock_repo = _make_mock_repo(single_row=row)
    app = _make_app_with_mock_repo(mock_repo)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get(
            f"/api/v1/audit-logs/{record_id}",
            cookies={"access_token": _token(_ADMIN_ID, UserRole.platform_admin.value)},
        )

    assert resp.status_code == 200
    body = resp.json()
    assert "data" in body
    assert body["data"]["id"] == str(record_id)


@pytest.mark.asyncio
async def test_get_by_id_404():
    mock_repo = _make_mock_repo(single_row=None)
    app = _make_app_with_mock_repo(mock_repo)
    missing_id = uuid.uuid4()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get(
            f"/api/v1/audit-logs/{missing_id}",
            cookies={"access_token": _token(_ADMIN_ID, UserRole.platform_admin.value)},
        )

    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_get_by_id_403_developer():
    mock_repo = _make_mock_repo(single_row=make_audit_record())
    app = _make_app_with_mock_repo(mock_repo)
    rid = uuid.uuid4()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get(
            f"/api/v1/audit-logs/{rid}",
            cookies={"access_token": _token(_DEV_ID, UserRole.developer.value)},
        )

    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# export endpoint
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_export_200_platform_admin():
    now = datetime.now(tz=timezone.utc)
    rows = [{**make_audit_record(), "created_at": now, "id": uuid.uuid4()} for _ in range(5)]
    mock_repo = _make_mock_repo(rows=rows)
    app = _make_app_with_mock_repo(mock_repo)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get(
            "/api/v1/audit-logs/export",
            cookies={"access_token": _token(_ADMIN_ID, UserRole.platform_admin.value)},
        )

    assert resp.status_code == 200
    assert "Content-Disposition" in resp.headers
    assert "attachment" in resp.headers["Content-Disposition"]
    assert "audit-export" in resp.headers["Content-Disposition"]


@pytest.mark.asyncio
async def test_export_returns_valid_json_array():
    now = datetime.now(tz=timezone.utc)
    rows = [{**make_audit_record(), "created_at": now, "id": uuid.uuid4()} for _ in range(3)]
    mock_repo = _make_mock_repo(rows=rows)
    app = _make_app_with_mock_repo(mock_repo)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get(
            "/api/v1/audit-logs/export",
            cookies={"access_token": _token(_ADMIN_ID, UserRole.platform_admin.value)},
        )

    assert resp.status_code == 200
    parsed = json.loads(resp.content)
    assert isinstance(parsed, list)
    assert len(parsed) == 3


@pytest.mark.asyncio
async def test_export_403_developer():
    mock_repo = _make_mock_repo()
    app = _make_app_with_mock_repo(mock_repo)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get(
            "/api/v1/audit-logs/export",
            cookies={"access_token": _token(_DEV_ID, UserRole.developer.value)},
        )

    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_export_empty_returns_empty_json_array():
    mock_repo = _make_mock_repo(rows=[])
    app = _make_app_with_mock_repo(mock_repo)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get(
            "/api/v1/audit-logs/export",
            cookies={"access_token": _token(_ADMIN_ID, UserRole.platform_admin.value)},
        )

    assert resp.status_code == 200
    assert json.loads(resp.content) == []


# ---------------------------------------------------------------------------
# SEEDED_AUDIT_RECORDS fixture sanity check
# ---------------------------------------------------------------------------

def test_seeded_records_count():
    assert len(SEEDED_AUDIT_RECORDS) >= 200


def test_seeded_records_diverse_actions():
    actions = {r["action"] for r in SEEDED_AUDIT_RECORDS}
    assert len(actions) >= 10


def test_seeded_records_span_multiple_months():
    months = {r["created_at"].month for r in SEEDED_AUDIT_RECORDS}
    assert len(months) >= 3


def test_seeded_records_diverse_resource_types():
    resource_types = {r["resource_type"] for r in SEEDED_AUDIT_RECORDS}
    assert len(resource_types) >= 5
