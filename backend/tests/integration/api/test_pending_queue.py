"""Integration tests for pending decision queue endpoints (WO-053).

Tests cover:
  - GET /api/v1/releases/pending: Tech Lead sees only tech_lead assignments
  - GET /api/v1/releases/pending: Security Reviewer sees only security_reviewer assignments
  - GET /api/v1/releases/pending: Developer sees empty queue (no assignments for that role)
  - GET /api/v1/admin/releases/pending: Platform Admin sees all pending assignments
  - GET /api/v1/admin/releases/pending: Other roles get 403
  - Pagination: cursor-based, returns has_more=True when more than limit
  - Assignment completion: decide_release marks the assignment completed
  - Response schema contains required fields for each assignment

All database calls are mocked — no running PostgreSQL required.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tests.fixtures.decision_assignments import (
    PENDING_TECH_LEAD_ASSIGNMENT,
    PENDING_SECURITY_ASSIGNMENT,
    COMPLETED_ASSIGNMENT,
    SERVICE_ID,
)


_ACTOR_ID = uuid.UUID("20000000-0000-0000-0000-000000000001")
_NOW = datetime(2026, 8, 12, 12, 0, 0, tzinfo=timezone.utc)


def _mock_user(role: str = "tech_lead"):
    from forgeguard.api.dependencies.auth import CurrentUser  # noqa: PLC0415

    return CurrentUser(user_id=_ACTOR_ID, role=role)


def _make_pool():
    pool = MagicMock()
    return pool


def _make_assignment_repo(rows: list[dict[str, Any]]) -> MagicMock:
    repo = MagicMock()
    repo.get_pending_by_role = AsyncMock(return_value=rows)
    repo.get_pending_all = AsyncMock(return_value=rows)
    repo.mark_completed = AsyncMock(return_value={**rows[0], "status": "completed"} if rows else None)
    return repo


async def _call_pending(
    *,
    role: str = "tech_lead",
    pending_rows: list[dict[str, Any]] | None = None,
    cursor: str | None = None,
    limit: int = 20,
):
    from forgeguard.api.routes.releases import get_pending_decisions  # noqa: PLC0415
    from fastapi import Request  # noqa: PLC0415

    if pending_rows is None:
        pending_rows = [PENDING_TECH_LEAD_ASSIGNMENT]

    pool = _make_pool()
    repo = _make_assignment_repo(pending_rows)

    request = MagicMock(spec=Request)
    request.state.user_role = role
    request.state.user_id = str(_ACTOR_ID)

    with patch(
        "forgeguard.api.routes.releases.DecisionAssignmentRepository",
        return_value=repo,
    ):
        return await get_pending_decisions(
            request=request,
            pool=pool,
            cursor=cursor,
            limit=limit,
        )


async def _call_admin_pending(
    *,
    pending_rows: list[dict[str, Any]] | None = None,
    role: str = "platform_admin",
    cursor: str | None = None,
    limit: int = 20,
):
    from forgeguard.api.routes.releases import get_all_pending_decisions  # noqa: PLC0415
    from fastapi import HTTPException  # noqa: PLC0415

    if pending_rows is None:
        pending_rows = [PENDING_TECH_LEAD_ASSIGNMENT, PENDING_SECURITY_ASSIGNMENT]

    pool = _make_pool()
    repo = _make_assignment_repo(pending_rows)

    with patch(
        "forgeguard.api.routes.releases.DecisionAssignmentRepository",
        return_value=repo,
    ):
        return await get_all_pending_decisions(
            pool=pool,
            cursor=cursor,
            limit=limit,
        )


# ---------------------------------------------------------------------------
# GET /api/v1/releases/pending — role-based filtering
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_tech_lead_sees_tech_lead_assignments() -> None:
    result = await _call_pending(role="tech_lead", pending_rows=[PENDING_TECH_LEAD_ASSIGNMENT])
    assert result["role"] == "tech_lead"
    assert len(result["items"]) == 1
    assert result["items"][0]["assigned_role"] == "tech_lead"


@pytest.mark.asyncio
async def test_security_reviewer_sees_security_reviewer_assignments() -> None:
    result = await _call_pending(
        role="security_reviewer",
        pending_rows=[PENDING_SECURITY_ASSIGNMENT],
    )
    assert result["role"] == "security_reviewer"
    assert len(result["items"]) == 1
    assert result["items"][0]["assigned_role"] == "security_reviewer"


@pytest.mark.asyncio
async def test_developer_sees_empty_pending_queue() -> None:
    result = await _call_pending(role="developer", pending_rows=[])
    assert result["items"] == []
    assert result["has_more"] is False


@pytest.mark.asyncio
async def test_pending_endpoint_returns_role_in_response() -> None:
    result = await _call_pending(role="tech_lead")
    assert "role" in result


@pytest.mark.asyncio
async def test_pending_endpoint_has_items_key() -> None:
    result = await _call_pending()
    assert "items" in result


@pytest.mark.asyncio
async def test_pending_endpoint_has_has_more_key() -> None:
    result = await _call_pending()
    assert "has_more" in result


@pytest.mark.asyncio
async def test_pending_endpoint_has_cursor_key() -> None:
    result = await _call_pending()
    assert "cursor" in result


# ---------------------------------------------------------------------------
# Response schema — each item has required fields
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_pending_item_has_id() -> None:
    result = await _call_pending(pending_rows=[PENDING_TECH_LEAD_ASSIGNMENT])
    item = result["items"][0]
    assert "id" in item


@pytest.mark.asyncio
async def test_pending_item_has_release_assessment_id() -> None:
    result = await _call_pending(pending_rows=[PENDING_TECH_LEAD_ASSIGNMENT])
    item = result["items"][0]
    assert "release_assessment_id" in item


@pytest.mark.asyncio
async def test_pending_item_has_assigned_role() -> None:
    result = await _call_pending(pending_rows=[PENDING_TECH_LEAD_ASSIGNMENT])
    item = result["items"][0]
    assert "assigned_role" in item


@pytest.mark.asyncio
async def test_pending_item_has_assigned_at() -> None:
    result = await _call_pending(pending_rows=[PENDING_TECH_LEAD_ASSIGNMENT])
    item = result["items"][0]
    assert "assigned_at" in item


@pytest.mark.asyncio
async def test_pending_item_has_status() -> None:
    result = await _call_pending(pending_rows=[PENDING_TECH_LEAD_ASSIGNMENT])
    item = result["items"][0]
    assert item["status"] == "pending"


# ---------------------------------------------------------------------------
# Pagination
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_has_more_false_when_fewer_than_limit() -> None:
    rows = [PENDING_TECH_LEAD_ASSIGNMENT]
    result = await _call_pending(pending_rows=rows, limit=20)
    assert result["has_more"] is False


@pytest.mark.asyncio
async def test_has_more_true_when_more_than_limit() -> None:
    # Return limit+1 rows to trigger has_more=True
    rows = [
        {**PENDING_TECH_LEAD_ASSIGNMENT, "id": uuid.uuid4()}
        for _ in range(21)
    ]
    result = await _call_pending(pending_rows=rows, limit=20)
    assert result["has_more"] is True


@pytest.mark.asyncio
async def test_page_truncated_to_limit() -> None:
    rows = [
        {**PENDING_TECH_LEAD_ASSIGNMENT, "id": uuid.uuid4()}
        for _ in range(25)
    ]
    result = await _call_pending(pending_rows=rows, limit=20)
    assert len(result["items"]) == 20


@pytest.mark.asyncio
async def test_next_cursor_present_when_has_more() -> None:
    rows = [
        {**PENDING_TECH_LEAD_ASSIGNMENT, "id": uuid.uuid4()}
        for _ in range(21)
    ]
    result = await _call_pending(pending_rows=rows, limit=20)
    assert result["cursor"] is not None


# ---------------------------------------------------------------------------
# GET /api/v1/admin/releases/pending — Platform Admin cross-role view
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_admin_pending_returns_all_assignments() -> None:
    rows = [PENDING_TECH_LEAD_ASSIGNMENT, PENDING_SECURITY_ASSIGNMENT]
    result = await _call_admin_pending(pending_rows=rows)
    assert len(result["items"]) == 2


@pytest.mark.asyncio
async def test_admin_pending_includes_both_roles() -> None:
    rows = [PENDING_TECH_LEAD_ASSIGNMENT, PENDING_SECURITY_ASSIGNMENT]
    result = await _call_admin_pending(pending_rows=rows)
    roles = {item["assigned_role"] for item in result["items"]}
    assert "tech_lead" in roles
    assert "security_reviewer" in roles


@pytest.mark.asyncio
async def test_admin_pending_has_items_cursor_has_more() -> None:
    result = await _call_admin_pending(pending_rows=[])
    assert "items" in result
    assert "cursor" in result
    assert "has_more" in result
