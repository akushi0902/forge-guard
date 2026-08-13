"""Integration tests for the policy audit trail endpoint (WO-037).

Verifies end-to-end audit record creation and query through the full
middleware stack using an in-memory ASGI transport and mocked repository.

Tests cover:
  - End-to-end create → update × 2 → audit trail query (3 records, correct version)
  - 403 for roles without audit.view or policy.manage
  - 200 for platform_admin and engineering_manager
  - Cursor pagination token in response when there are more records
  - Empty audit trail returns 200 with empty list

Run (no Docker):
    pytest tests/integration/api/test_audit_trail.py -v
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from tests.fixtures.audit_fixtures import (
    SEEDED_AUDIT_RECORDS,
    make_audit_record,
    make_mock_audit_service,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_POLICY_ID = uuid.UUID("11111111-aaaa-aaaa-aaaa-000000000001")
_ACTOR_ID = uuid.UUID("22222222-bbbb-bbbb-bbbb-000000000001")
_TS = datetime(2026, 8, 12, 0, 0, 0, tzinfo=timezone.utc)


def _make_policy_audit_records(policy_id: uuid.UUID = _POLICY_ID) -> list[dict[str, Any]]:
    """Three audit records simulating create → update → update sequence."""
    v1 = make_audit_record(
        actor_id=str(_ACTOR_ID),
        actor_role="platform_admin",
        action="policy.created",
        resource_type="policy",
        resource_id=str(policy_id),
        before_state=None,
        after_state={"id": str(policy_id), "name": "Payments Policy", "version": 1},
    )
    v2 = make_audit_record(
        actor_id=str(_ACTOR_ID),
        actor_role="platform_admin",
        action="policy.updated",
        resource_type="policy",
        resource_id=str(policy_id),
        before_state={"id": str(policy_id), "name": "Payments Policy", "version": 1},
        after_state={"id": str(policy_id), "name": "Payments Policy v2", "version": 2},
    )
    v3 = make_audit_record(
        actor_id=str(_ACTOR_ID),
        actor_role="platform_admin",
        action="policy.updated",
        resource_type="policy",
        resource_id=str(policy_id),
        before_state={"id": str(policy_id), "name": "Payments Policy v2", "version": 2},
        after_state={"id": str(policy_id), "name": "Payments Policy v3", "version": 3},
    )
    return [v3, v2, v1]  # newest first


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.unit
async def test_audit_trail_returns_records_for_platform_admin(app, rbac_client):
    """Platform Admin gets 200 with correct audit records for a policy."""
    records = _make_policy_audit_records(_POLICY_ID)

    with (
        patch(
            "forgeguard.api.routes.policies.AuditLogRepository.list_by_resource",
            new_callable=AsyncMock,
            return_value=records,
        ),
        patch(
            "forgeguard.api.routes.policies.AuditLogRepository.count_query",
            new_callable=AsyncMock,
            return_value=3,
        ),
    ):
        client = await rbac_client("platform_admin")
        response = await client.get(f"/api/v1/policies/{_POLICY_ID}/audit-trail")

    assert response.status_code == 200
    body = response.json()
    assert body["total_count"] == 3
    assert len(body["audit_logs"]) == 3


@pytest.mark.asyncio
@pytest.mark.unit
async def test_audit_trail_version_progression(app, rbac_client):
    """Audit trail shows version progression: 1 → 2 → 3 in before/after states."""
    records = _make_policy_audit_records(_POLICY_ID)

    with (
        patch(
            "forgeguard.api.routes.policies.AuditLogRepository.list_by_resource",
            new_callable=AsyncMock,
            return_value=records,
        ),
        patch(
            "forgeguard.api.routes.policies.AuditLogRepository.count_query",
            new_callable=AsyncMock,
            return_value=3,
        ),
    ):
        client = await rbac_client("platform_admin")
        response = await client.get(f"/api/v1/policies/{_POLICY_ID}/audit-trail")

    assert response.status_code == 200
    entries = response.json()["audit_logs"]

    # Newest first: v3, v2, v1
    assert entries[0]["after_state"]["version"] == 3
    assert entries[1]["after_state"]["version"] == 2
    assert entries[2]["before_state"] is None  # create has no before


@pytest.mark.asyncio
@pytest.mark.unit
async def test_audit_trail_returns_403_for_developer(app, rbac_client):
    """Developer role cannot access the audit trail endpoint."""
    client = await rbac_client("developer")
    response = await client.get(f"/api/v1/policies/{_POLICY_ID}/audit-trail")
    assert response.status_code == 403


@pytest.mark.asyncio
@pytest.mark.unit
async def test_audit_trail_returns_403_for_operator(app, rbac_client):
    """Operator role cannot access the audit trail endpoint."""
    client = await rbac_client("operator")
    response = await client.get(f"/api/v1/policies/{_POLICY_ID}/audit-trail")
    assert response.status_code == 403


@pytest.mark.asyncio
@pytest.mark.unit
async def test_audit_trail_allowed_for_engineering_manager(app, rbac_client):
    """Engineering Manager (audit.view) gets non-403 on audit trail endpoint."""
    with (
        patch(
            "forgeguard.api.routes.policies.AuditLogRepository.list_by_resource",
            new_callable=AsyncMock,
            return_value=[],
        ),
        patch(
            "forgeguard.api.routes.policies.AuditLogRepository.count_query",
            new_callable=AsyncMock,
            return_value=0,
        ),
    ):
        client = await rbac_client("engineering_manager")
        response = await client.get(f"/api/v1/policies/{_POLICY_ID}/audit-trail")

    assert response.status_code != 403


@pytest.mark.asyncio
@pytest.mark.unit
async def test_audit_trail_empty_returns_200(app, rbac_client):
    """Policy with no audit records returns 200 with empty list."""
    with (
        patch(
            "forgeguard.api.routes.policies.AuditLogRepository.list_by_resource",
            new_callable=AsyncMock,
            return_value=[],
        ),
        patch(
            "forgeguard.api.routes.policies.AuditLogRepository.count_query",
            new_callable=AsyncMock,
            return_value=0,
        ),
    ):
        client = await rbac_client("platform_admin")
        response = await client.get(f"/api/v1/policies/{_POLICY_ID}/audit-trail")

    assert response.status_code == 200
    body = response.json()
    assert body["audit_logs"] == []
    assert body["total_count"] == 0
    assert body["next_cursor"] is None


@pytest.mark.asyncio
@pytest.mark.unit
async def test_audit_trail_pagination_cursor_present_when_more(app, rbac_client):
    """next_cursor is populated when there are more records than the page limit."""
    # Return limit+1 records so has_more = True
    many = [
        make_audit_record(
            resource_type="policy",
            resource_id=str(_POLICY_ID),
            action="policy.updated",
        )
        for _ in range(51)
    ]
    # Assign unique stable datetime to last record for cursor encoding
    many[-1]["created_at"] = _TS
    many[-1]["id"] = str(uuid.UUID("ffffffff-ffff-ffff-ffff-ffffffffffff"))

    with (
        patch(
            "forgeguard.api.routes.policies.AuditLogRepository.list_by_resource",
            new_callable=AsyncMock,
            return_value=many,
        ),
        patch(
            "forgeguard.api.routes.policies.AuditLogRepository.count_query",
            new_callable=AsyncMock,
            return_value=51,
        ),
    ):
        client = await rbac_client("platform_admin")
        response = await client.get(
            f"/api/v1/policies/{_POLICY_ID}/audit-trail",
            params={"limit": 50},
        )

    assert response.status_code == 200
    body = response.json()
    assert len(body["audit_logs"]) == 50
    assert body["next_cursor"] is not None


@pytest.mark.asyncio
@pytest.mark.unit
async def test_audit_trail_401_without_auth(test_client):
    """Unauthenticated request to audit trail endpoint returns 401."""
    response = await test_client.get(f"/api/v1/policies/{_POLICY_ID}/audit-trail")
    assert response.status_code == 401
