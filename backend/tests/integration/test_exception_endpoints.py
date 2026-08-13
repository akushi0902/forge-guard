"""Integration tests for exception request API endpoints (WO-062).

Tests all endpoints using FastAPI dependency overrides (no real DB):
  - POST /api/v1/findings/{finding_id}/exceptions — submit exception request
  - GET  /api/v1/exceptions/{exception_id}        — retrieve exception

RBAC: Developer and Tech Lead (exception.request) = allowed for POST.
      Security Reviewer / Engineering Manager = 403 for POST.
      All authenticated roles = 200 for GET.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient

import forgeguard.core.config as _config_module
from forgeguard.core.config import Settings
from forgeguard.core.exceptions import BadRequestError, ConflictError, NotFoundError
from forgeguard.main import create_app
from tests.fixtures.exception_fixtures import (
    EXCEPTION_ROW,
    FINDING_CODE_QUALITY_ROW,
    FINDING_SECURITY_ROW,
    VALID_EXCEPTION_PAYLOAD,
    INVALID_JUSTIFICATION_TOO_SHORT,
    INVALID_EXPIRES_AT_PAST,
    INVALID_EXPIRES_AT_TOO_FAR,
)
from tests.fixtures.tokens import TEST_JWT_SECRET, make_access_token

_ADMIN_ID = uuid.uuid4()
_DEV_ID = uuid.uuid4()
_TECH_LEAD_ID = uuid.uuid4()
_REVIEWER_ID = uuid.uuid4()
_MANAGER_ID = uuid.uuid4()


def _make_settings() -> Settings:
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


def _make_mock_svc(
    *,
    submit_result: Any = None,
    submit_raises: Exception | None = None,
    get_result: Any = None,
):
    from forgeguard.services.remediation.exception_service import ExceptionService  # noqa: PLC0415

    svc = MagicMock(spec=ExceptionService)

    if submit_raises is not None:
        svc.submit_request = AsyncMock(side_effect=submit_raises)
    else:
        svc.submit_request = AsyncMock(return_value=submit_result or dict(EXCEPTION_ROW))

    svc.get_exception = AsyncMock(return_value=get_result or dict(EXCEPTION_ROW))
    return svc


def _make_app(mock_svc: Any):
    settings = _make_settings()
    _config_module._settings_cache = settings
    app = create_app()

    from forgeguard.api.routes.remediation import get_exception_service  # noqa: PLC0415

    app.dependency_overrides[get_exception_service] = lambda: mock_svc
    return app


# ---------------------------------------------------------------------------
# POST /api/v1/findings/{finding_id}/exceptions
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_submit_exception_201_developer():
    svc = _make_mock_svc()
    app = _make_app(svc)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            f"/api/v1/findings/{FINDING_SECURITY_ROW['id']}/exceptions",
            json=VALID_EXCEPTION_PAYLOAD,
            cookies={"access_token": _token(_DEV_ID, "developer")},
        )
    assert resp.status_code == 201
    body = resp.json()
    assert "id" in body
    assert "approver_role" in body
    assert "status" in body


@pytest.mark.asyncio
async def test_submit_exception_201_tech_lead():
    svc = _make_mock_svc()
    app = _make_app(svc)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            f"/api/v1/findings/{FINDING_SECURITY_ROW['id']}/exceptions",
            json=VALID_EXCEPTION_PAYLOAD,
            cookies={"access_token": _token(_TECH_LEAD_ID, "tech_lead")},
        )
    assert resp.status_code == 201


@pytest.mark.asyncio
async def test_submit_exception_403_security_reviewer():
    svc = _make_mock_svc()
    app = _make_app(svc)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            f"/api/v1/findings/{FINDING_CODE_QUALITY_ROW['id']}/exceptions",
            json=VALID_EXCEPTION_PAYLOAD,
            cookies={"access_token": _token(_REVIEWER_ID, "security_reviewer")},
        )
    assert resp.status_code == 403
    assert "exception.request" in str(resp.json()).lower()


@pytest.mark.asyncio
async def test_submit_exception_403_engineering_manager():
    svc = _make_mock_svc()
    app = _make_app(svc)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            f"/api/v1/findings/{FINDING_CODE_QUALITY_ROW['id']}/exceptions",
            json=VALID_EXCEPTION_PAYLOAD,
            cookies={"access_token": _token(_MANAGER_ID, "engineering_manager")},
        )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_submit_exception_401_unauthenticated():
    svc = _make_mock_svc()
    app = _make_app(svc)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            f"/api/v1/findings/{FINDING_CODE_QUALITY_ROW['id']}/exceptions",
            json=VALID_EXCEPTION_PAYLOAD,
        )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_submit_exception_422_justification_too_short():
    svc = _make_mock_svc()
    app = _make_app(svc)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            f"/api/v1/findings/{FINDING_CODE_QUALITY_ROW['id']}/exceptions",
            json=INVALID_JUSTIFICATION_TOO_SHORT,
            cookies={"access_token": _token(_DEV_ID, "developer")},
        )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_submit_exception_422_expires_at_past():
    svc = _make_mock_svc()
    app = _make_app(svc)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            f"/api/v1/findings/{FINDING_CODE_QUALITY_ROW['id']}/exceptions",
            json=INVALID_EXPIRES_AT_PAST,
            cookies={"access_token": _token(_DEV_ID, "developer")},
        )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_submit_exception_422_expires_at_too_far():
    svc = _make_mock_svc()
    app = _make_app(svc)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            f"/api/v1/findings/{FINDING_CODE_QUALITY_ROW['id']}/exceptions",
            json=INVALID_EXPIRES_AT_TOO_FAR,
            cookies={"access_token": _token(_DEV_ID, "developer")},
        )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_submit_exception_404_finding_not_found():
    svc = _make_mock_svc(
        submit_raises=NotFoundError("Finding not found.")
    )
    app = _make_app(svc)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            f"/api/v1/findings/{uuid.uuid4()}/exceptions",
            json=VALID_EXCEPTION_PAYLOAD,
            cookies={"access_token": _token(_DEV_ID, "developer")},
        )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_submit_exception_400_resolved_finding():
    svc = _make_mock_svc(
        submit_raises=BadRequestError(
            "Finding is in 'resolved' status.",
            details={"error_code": "FINDING_ALREADY_RESOLVED"},
        )
    )
    app = _make_app(svc)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            f"/api/v1/findings/{uuid.uuid4()}/exceptions",
            json=VALID_EXCEPTION_PAYLOAD,
            cookies={"access_token": _token(_DEV_ID, "developer")},
        )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_submit_exception_409_duplicate_pending():
    svc = _make_mock_svc(
        submit_raises=ConflictError("An exception request is already pending.")
    )
    app = _make_app(svc)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            f"/api/v1/findings/{uuid.uuid4()}/exceptions",
            json=VALID_EXCEPTION_PAYLOAD,
            cookies={"access_token": _token(_DEV_ID, "developer")},
        )
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_submit_exception_security_finding_response_has_security_reviewer():
    security_row = {
        **EXCEPTION_ROW,
        "approver_role": "security_reviewer",
    }
    svc = _make_mock_svc(submit_result=security_row)
    app = _make_app(svc)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            f"/api/v1/findings/{FINDING_SECURITY_ROW['id']}/exceptions",
            json=VALID_EXCEPTION_PAYLOAD,
            cookies={"access_token": _token(_DEV_ID, "developer")},
        )
    assert resp.status_code == 201
    assert resp.json()["approver_role"] == "security_reviewer"


# ---------------------------------------------------------------------------
# GET /api/v1/exceptions/{exception_id}
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_exception_200_developer():
    svc = _make_mock_svc(get_result=dict(EXCEPTION_ROW))
    app = _make_app(svc)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get(
            f"/api/v1/exceptions/{EXCEPTION_ROW['id']}",
            cookies={"access_token": _token(_DEV_ID, "developer")},
        )
    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == str(EXCEPTION_ROW["id"])
    assert "approver_role" in body
    assert "justification" in body


@pytest.mark.asyncio
async def test_get_exception_200_platform_admin():
    svc = _make_mock_svc(get_result=dict(EXCEPTION_ROW))
    app = _make_app(svc)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get(
            f"/api/v1/exceptions/{EXCEPTION_ROW['id']}",
            cookies={"access_token": _token(_ADMIN_ID, "platform_admin")},
        )
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_get_exception_404_not_found():
    svc = _make_mock_svc(get_result=None)
    app = _make_app(svc)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get(
            f"/api/v1/exceptions/{uuid.uuid4()}",
            cookies={"access_token": _token(_DEV_ID, "developer")},
        )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_get_exception_401_unauthenticated():
    svc = _make_mock_svc(get_result=dict(EXCEPTION_ROW))
    app = _make_app(svc)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get(f"/api/v1/exceptions/{EXCEPTION_ROW['id']}")
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Audit log verification
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_submit_exception_calls_service_with_actor_info():
    captured_calls = []

    async def _submit(**kwargs):
        captured_calls.append(kwargs)
        return dict(EXCEPTION_ROW)

    svc = _make_mock_svc()
    svc.submit_request = _submit
    app = _make_app(svc)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            f"/api/v1/findings/{FINDING_CODE_QUALITY_ROW['id']}/exceptions",
            json=VALID_EXCEPTION_PAYLOAD,
            cookies={"access_token": _token(_DEV_ID, "developer")},
        )

    assert resp.status_code == 201
    assert len(captured_calls) == 1
    assert captured_calls[0]["actor_role"] == "developer"
    assert str(captured_calls[0]["actor_id"]) == str(_DEV_ID)
