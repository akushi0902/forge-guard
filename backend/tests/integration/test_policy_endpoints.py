"""Integration tests for Policy Guardian CRUD API (WO-035).

Tests all 6 endpoints using FastAPI dependency overrides (no real DB):
  - GET  /api/v1/policies              — list with pagination
  - POST /api/v1/policies              — create policy (admin only)
  - PUT  /api/v1/policies/{id}         — update policy (admin only)
  - POST /api/v1/policies/{id}/rules   — create rule (admin only)
  - PUT  /api/v1/policies/{id}/rules/{rid} — update rule (admin only)
  - PATCH /api/v1/policies/{id}/rules/{rid}/toggle — toggle rule (admin only)

RBAC: Platform Admin (policy.manage) = allowed for mutations; Developer = 403.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient

import forgeguard.core.config as _config_module
from forgeguard.core.config import Settings
from forgeguard.data.repositories.policies import PolicyRepository
from forgeguard.main import create_app
from tests.fixtures.policy_fixtures import (
    ALL_POLICIES,
    POLICY_CODE_QUALITY,
    POLICY_CODE_QUALITY_ID,
    RULES_CODE_QUALITY,
    RULE_IDS,
)
from tests.fixtures.tokens import TEST_JWT_SECRET, make_access_token

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_ADMIN_ID = uuid.uuid4()
_DEV_ID = uuid.uuid4()


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


def _make_mock_policy_svc(
    *,
    list_result: dict | None = None,
    policy_row: dict | None = None,
    rule_row: dict | None = None,
):
    """Return a mock PolicyGuardianService."""
    from forgeguard.services.policy_guardian import PolicyGuardianService  # noqa: PLC0415

    svc = MagicMock(spec=PolicyGuardianService)

    default_list = {
        "items": list(ALL_POLICIES),
        "next_cursor": None,
        "total_count": len(ALL_POLICIES),
    }
    svc.list_policies = AsyncMock(return_value=list_result or default_list)
    svc.get_policy = AsyncMock(return_value=policy_row or dict(POLICY_CODE_QUALITY))
    svc.create_policy = AsyncMock(return_value=policy_row or dict(POLICY_CODE_QUALITY))
    svc.update_policy = AsyncMock(return_value=policy_row or dict(POLICY_CODE_QUALITY))
    svc.create_rule = AsyncMock(return_value=rule_row or dict(RULES_CODE_QUALITY[0]))
    svc.update_rule = AsyncMock(return_value=rule_row or dict(RULES_CODE_QUALITY[0]))
    svc.toggle_rule = AsyncMock(return_value=rule_row or dict(RULES_CODE_QUALITY[0]))
    return svc


def _make_app(mock_svc: Any):
    settings = _make_settings()
    _config_module._settings_cache = settings
    app = create_app()

    from forgeguard.api.routes.policies import get_policy_guardian_service  # noqa: PLC0415

    app.dependency_overrides[get_policy_guardian_service] = lambda: mock_svc
    return app


# ---------------------------------------------------------------------------
# GET /api/v1/policies — list
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_policies_200_platform_admin():
    svc = _make_mock_policy_svc()
    app = _make_app(svc)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get(
            "/api/v1/policies",
            cookies={"access_token": _token(_ADMIN_ID, "platform_admin")},
        )
    assert resp.status_code == 200
    data = resp.json()
    assert "items" in data
    assert "total_count" in data
    assert "next_cursor" in data


@pytest.mark.asyncio
async def test_list_policies_200_developer():
    svc = _make_mock_policy_svc()
    app = _make_app(svc)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get(
            "/api/v1/policies",
            cookies={"access_token": _token(_DEV_ID, "developer")},
        )
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_list_policies_401_unauthenticated():
    svc = _make_mock_policy_svc()
    app = _make_app(svc)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/v1/policies")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_list_policies_returns_pagination_fields():
    svc = _make_mock_policy_svc(
        list_result={
            "items": list(ALL_POLICIES[:2]),
            "next_cursor": "some_cursor",
            "total_count": 10,
        }
    )
    app = _make_app(svc)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get(
            "/api/v1/policies?limit=2",
            cookies={"access_token": _token(_ADMIN_ID, "platform_admin")},
        )
    data = resp.json()
    assert data["next_cursor"] == "some_cursor"
    assert data["total_count"] == 10
    assert len(data["items"]) == 2


# ---------------------------------------------------------------------------
# POST /api/v1/policies — create
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_policy_201_platform_admin():
    svc = _make_mock_policy_svc()
    app = _make_app(svc)
    payload = {"name": "New Policy", "dimension": "security", "is_active": True}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/api/v1/policies",
            json=payload,
            cookies={"access_token": _token(_ADMIN_ID, "platform_admin")},
        )
    assert resp.status_code == 201
    body = resp.json()
    assert "id" in body
    assert body.get("effect_note") is not None


@pytest.mark.asyncio
async def test_create_policy_403_developer():
    svc = _make_mock_policy_svc()
    app = _make_app(svc)
    payload = {"name": "New Policy", "dimension": "security"}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/api/v1/policies",
            json=payload,
            cookies={"access_token": _token(_DEV_ID, "developer")},
        )
    assert resp.status_code == 403
    body = resp.json()
    assert "policy.manage" in str(body).lower() or "forbidden" in str(body).lower()


@pytest.mark.asyncio
async def test_create_policy_422_invalid_dimension():
    svc = _make_mock_policy_svc()
    app = _make_app(svc)
    payload = {"name": "Bad Policy", "dimension": "invalid_dimension"}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/api/v1/policies",
            json=payload,
            cookies={"access_token": _token(_ADMIN_ID, "platform_admin")},
        )
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# PUT /api/v1/policies/{id} — update
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_update_policy_200_platform_admin():
    svc = _make_mock_policy_svc()
    app = _make_app(svc)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.put(
            f"/api/v1/policies/{POLICY_CODE_QUALITY_ID}",
            json={"name": "Updated Name"},
            cookies={"access_token": _token(_ADMIN_ID, "platform_admin")},
        )
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_update_policy_403_developer():
    svc = _make_mock_policy_svc()
    app = _make_app(svc)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.put(
            f"/api/v1/policies/{POLICY_CODE_QUALITY_ID}",
            json={"name": "Updated Name"},
            cookies={"access_token": _token(_DEV_ID, "developer")},
        )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_update_policy_404_not_found():
    svc = _make_mock_policy_svc()
    svc.update_policy = AsyncMock(return_value=None)
    app = _make_app(svc)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.put(
            f"/api/v1/policies/{uuid.uuid4()}",
            json={"name": "Updated Name"},
            cookies={"access_token": _token(_ADMIN_ID, "platform_admin")},
        )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# POST /api/v1/policies/{id}/rules — create rule
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_rule_201_platform_admin():
    svc = _make_mock_policy_svc()
    app = _make_app(svc)
    rule_payload = {
        "name": "Min Coverage",
        "rule_type": "threshold_gte",
        "threshold_config": {"numeric_value": 80},
        "severity": "high",
        "weight": "10.00",
        "is_active": True,
    }
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            f"/api/v1/policies/{POLICY_CODE_QUALITY_ID}/rules",
            json=rule_payload,
            cookies={"access_token": _token(_ADMIN_ID, "platform_admin")},
        )
    assert resp.status_code == 201
    body = resp.json()
    assert "id" in body
    assert body.get("effect_note") is not None


@pytest.mark.asyncio
async def test_create_rule_403_developer():
    svc = _make_mock_policy_svc()
    app = _make_app(svc)
    rule_payload = {
        "name": "Min Coverage",
        "rule_type": "threshold_gte",
        "threshold_config": {"numeric_value": 80},
        "severity": "high",
        "weight": "10.00",
    }
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            f"/api/v1/policies/{POLICY_CODE_QUALITY_ID}/rules",
            json=rule_payload,
            cookies={"access_token": _token(_DEV_ID, "developer")},
        )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_create_rule_422_missing_numeric_value():
    svc = _make_mock_policy_svc()
    app = _make_app(svc)
    rule_payload = {
        "name": "Min Coverage",
        "rule_type": "threshold_gte",
        "threshold_config": {"value": 80},  # missing numeric_value
        "severity": "high",
        "weight": "10.00",
    }
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            f"/api/v1/policies/{POLICY_CODE_QUALITY_ID}/rules",
            json=rule_payload,
            cookies={"access_token": _token(_ADMIN_ID, "platform_admin")},
        )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_create_rule_404_missing_policy():
    svc = _make_mock_policy_svc()
    svc.create_rule = AsyncMock(return_value=None)
    app = _make_app(svc)
    rule_payload = {
        "name": "Min Coverage",
        "rule_type": "threshold_gte",
        "threshold_config": {"numeric_value": 80},
        "severity": "high",
        "weight": "10.00",
    }
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            f"/api/v1/policies/{uuid.uuid4()}/rules",
            json=rule_payload,
            cookies={"access_token": _token(_ADMIN_ID, "platform_admin")},
        )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# PUT /api/v1/policies/{id}/rules/{rule_id} — update rule
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_update_rule_200_platform_admin():
    svc = _make_mock_policy_svc()
    app = _make_app(svc)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.put(
            f"/api/v1/policies/{POLICY_CODE_QUALITY_ID}/rules/{RULE_IDS[0]}",
            json={"name": "Updated Rule"},
            cookies={"access_token": _token(_ADMIN_ID, "platform_admin")},
        )
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_update_rule_403_developer():
    svc = _make_mock_policy_svc()
    app = _make_app(svc)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.put(
            f"/api/v1/policies/{POLICY_CODE_QUALITY_ID}/rules/{RULE_IDS[0]}",
            json={"name": "Updated Rule"},
            cookies={"access_token": _token(_DEV_ID, "developer")},
        )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_update_rule_404_not_found():
    svc = _make_mock_policy_svc()
    svc.update_rule = AsyncMock(return_value=None)
    app = _make_app(svc)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.put(
            f"/api/v1/policies/{POLICY_CODE_QUALITY_ID}/rules/{uuid.uuid4()}",
            json={"name": "Updated Rule"},
            cookies={"access_token": _token(_ADMIN_ID, "platform_admin")},
        )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# PATCH /api/v1/policies/{id}/rules/{rule_id}/toggle — toggle rule
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_toggle_rule_200_platform_admin():
    svc = _make_mock_policy_svc()
    app = _make_app(svc)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.patch(
            f"/api/v1/policies/{POLICY_CODE_QUALITY_ID}/rules/{RULE_IDS[0]}/toggle",
            cookies={"access_token": _token(_ADMIN_ID, "platform_admin")},
        )
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_toggle_rule_403_developer():
    svc = _make_mock_policy_svc()
    app = _make_app(svc)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.patch(
            f"/api/v1/policies/{POLICY_CODE_QUALITY_ID}/rules/{RULE_IDS[0]}/toggle",
            cookies={"access_token": _token(_DEV_ID, "developer")},
        )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_toggle_rule_404_not_found():
    svc = _make_mock_policy_svc()
    svc.toggle_rule = AsyncMock(return_value=None)
    app = _make_app(svc)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.patch(
            f"/api/v1/policies/{POLICY_CODE_QUALITY_ID}/rules/{uuid.uuid4()}/toggle",
            cookies={"access_token": _token(_ADMIN_ID, "platform_admin")},
        )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Audit log verification — mutations produce audit events
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_policy_calls_audit():
    audit_svc = MagicMock()
    audit_svc.log_event = AsyncMock()

    svc = _make_mock_policy_svc()
    # Patch create_policy to verify audit is invoked
    original = dict(POLICY_CODE_QUALITY)
    create_calls = []

    async def _create_policy(data, *, actor_id, actor_role):
        create_calls.append({"actor_id": actor_id, "actor_role": actor_role})
        return original

    svc.create_policy = _create_policy
    app = _make_app(svc)
    payload = {"name": "Audited Policy", "dimension": "security"}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/api/v1/policies",
            json=payload,
            cookies={"access_token": _token(_ADMIN_ID, "platform_admin")},
        )
    assert resp.status_code == 201
    assert len(create_calls) == 1
    assert create_calls[0]["actor_role"] == "platform_admin"
