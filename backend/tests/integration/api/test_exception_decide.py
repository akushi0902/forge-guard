"""Integration tests for exception decision endpoints (WO-064).

Tests cover:
  - POST /api/v1/exceptions/{id}/decide — approve flow
  - POST /api/v1/exceptions/{id}/decide — deny flow
  - POST /api/v1/exceptions/{id}/decide — 403 wrong role
  - POST /api/v1/exceptions/{id}/decide — 409 already decided
  - POST /api/v1/exceptions/{id}/decide — 404 exception not found
  - POST /api/v1/exceptions/{id}/decide — 400 finding already resolved
  - GET /api/v1/exceptions — list with status/approver_role filters
  - GET /api/v1/exceptions — pagination (cursor, total)

All database calls are mocked — no running PostgreSQL required.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tests.fixtures.exception_fixtures import (
    EXCEPTION_ID_1,
    EXCEPTION_ROW,
    FINDING_SECURITY_ID,
    FINDING_SECURITY_ROW,
)
from tests.fixtures.exception_users import (
    PLATFORM_ADMIN_ID,
    SECURITY_REVIEWER_ID,
    PLATFORM_ADMIN_USER,
    SECURITY_REVIEWER_USER,
)

APPROVER_ID = SECURITY_REVIEWER_ID

_NOW = datetime(2026, 8, 12, 12, 0, 0, tzinfo=timezone.utc)
_FUTURE = _NOW + timedelta(days=30)

DECISION_COMMENT = "Approved after security review — no exploitable vector found."
DENY_COMMENT = "Risk accepted at the board level; patch scheduled for Q4."


def _make_non_security_exception() -> dict[str, Any]:
    return {
        **EXCEPTION_ROW,
        "id": uuid.UUID("44444444-0002-0002-0002-000000000002"),
        "finding_id": uuid.UUID("33333333-0002-0002-0002-000000000002"),
        "approver_role": "platform_admin",
        "status": "pending",
    }


def _make_approved_exception() -> dict[str, Any]:
    return {
        **EXCEPTION_ROW,
        "status": "approved",
        "decided_by": SECURITY_REVIEWER_ID,
        "decided_at": _NOW,
        "decision_comment": DECISION_COMMENT,
    }


def _make_denied_exception() -> dict[str, Any]:
    return {
        **EXCEPTION_ROW,
        "status": "denied",
        "decided_by": SECURITY_REVIEWER_ID,
        "decided_at": _NOW,
        "decision_comment": DENY_COMMENT,
    }


def _make_service(
    exception_row: dict | None = None,
    finding_row: dict | None = None,
    updated_exception: dict | None = None,
    updated_finding: dict | None = None,
):
    from forgeguard.services.remediation.exception_service import ExceptionService  # noqa: PLC0415

    exc_repo = MagicMock()
    exc_row = exception_row or EXCEPTION_ROW
    exc_repo.get_by_id = AsyncMock(return_value=exc_row)
    decided = {
        **(updated_exception or exc_row),
        "status": updated_exception["status"] if updated_exception else "approved",
    }
    exc_repo.update_decision = AsyncMock(return_value=decided)

    find_repo = MagicMock()
    fnd_row = finding_row or FINDING_SECURITY_ROW
    find_repo.get_by_id = AsyncMock(return_value=fnd_row)
    find_repo.update_status = AsyncMock(
        return_value=updated_finding or {**fnd_row, "status": "exception_granted"}
    )

    return ExceptionService(exc_repo, find_repo, None)


# ---------------------------------------------------------------------------
# POST /api/v1/exceptions/{id}/decide — approve flow
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_approve_decision_returns_200() -> None:
    from forgeguard.api.routes.remediation import decide_exception  # noqa: PLC0415
    from forgeguard.api.schemas.exception import ExceptionDecisionRequest  # noqa: PLC0415

    svc = _make_service()
    body = ExceptionDecisionRequest(decision="approved", decision_comment=DECISION_COMMENT)

    with patch("forgeguard.api.routes.remediation.get_exception_service", return_value=svc):
        result = await decide_exception(
            exception_id=EXCEPTION_ID_1,
            body=body,
            current_user=SECURITY_REVIEWER_USER,
            svc=svc,
        )

    assert result.status == "approved"


@pytest.mark.asyncio
async def test_approve_response_includes_finding_status() -> None:
    from forgeguard.api.routes.remediation import decide_exception  # noqa: PLC0415
    from forgeguard.api.schemas.exception import ExceptionDecisionRequest  # noqa: PLC0415

    svc = _make_service()
    body = ExceptionDecisionRequest(decision="approved", decision_comment=DECISION_COMMENT)

    result = await decide_exception(
        exception_id=EXCEPTION_ID_1,
        body=body,
        current_user=SECURITY_REVIEWER_USER,
        svc=svc,
    )

    assert result.finding_status == "exception_granted"


@pytest.mark.asyncio
async def test_approve_response_includes_decided_by() -> None:
    from forgeguard.api.routes.remediation import decide_exception  # noqa: PLC0415
    from forgeguard.api.schemas.exception import ExceptionDecisionRequest  # noqa: PLC0415

    svc = _make_service()
    body = ExceptionDecisionRequest(decision="approved", decision_comment=DECISION_COMMENT)

    result = await decide_exception(
        exception_id=EXCEPTION_ID_1,
        body=body,
        current_user=SECURITY_REVIEWER_USER,
        svc=svc,
    )

    assert result.decided_by == SECURITY_REVIEWER_ID


@pytest.mark.asyncio
async def test_approve_response_health_score_impact_is_null() -> None:
    from forgeguard.api.routes.remediation import decide_exception  # noqa: PLC0415
    from forgeguard.api.schemas.exception import ExceptionDecisionRequest  # noqa: PLC0415

    svc = _make_service()
    body = ExceptionDecisionRequest(decision="approved", decision_comment=DECISION_COMMENT)

    result = await decide_exception(
        exception_id=EXCEPTION_ID_1,
        body=body,
        current_user=SECURITY_REVIEWER_USER,
        svc=svc,
    )

    assert result.health_score_impact is None


# ---------------------------------------------------------------------------
# POST /api/v1/exceptions/{id}/decide — deny flow
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_deny_decision_returns_denied_status() -> None:
    from forgeguard.api.routes.remediation import decide_exception  # noqa: PLC0415
    from forgeguard.api.schemas.exception import ExceptionDecisionRequest  # noqa: PLC0415

    svc = _make_service(updated_exception={**EXCEPTION_ROW, "status": "denied"})
    body = ExceptionDecisionRequest(decision="denied", decision_comment=DENY_COMMENT)

    result = await decide_exception(
        exception_id=EXCEPTION_ID_1,
        body=body,
        current_user=SECURITY_REVIEWER_USER,
        svc=svc,
    )

    assert result.status == "denied"


@pytest.mark.asyncio
async def test_deny_response_finding_status_is_open() -> None:
    from forgeguard.api.routes.remediation import decide_exception  # noqa: PLC0415
    from forgeguard.api.schemas.exception import ExceptionDecisionRequest  # noqa: PLC0415

    svc = _make_service(updated_exception={**EXCEPTION_ROW, "status": "denied"})
    body = ExceptionDecisionRequest(decision="denied", decision_comment=DENY_COMMENT)

    result = await decide_exception(
        exception_id=EXCEPTION_ID_1,
        body=body,
        current_user=SECURITY_REVIEWER_USER,
        svc=svc,
    )

    assert result.finding_status == "open"


# ---------------------------------------------------------------------------
# POST /api/v1/exceptions/{id}/decide — 403 wrong role
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_wrong_role_raises_http_403() -> None:
    from fastapi import HTTPException  # noqa: PLC0415
    from forgeguard.api.routes.remediation import decide_exception  # noqa: PLC0415
    from forgeguard.api.schemas.exception import ExceptionDecisionRequest  # noqa: PLC0415

    svc = _make_service()
    body = ExceptionDecisionRequest(decision="approved", decision_comment=DECISION_COMMENT)

    with pytest.raises(HTTPException) as exc_info:
        await decide_exception(
            exception_id=EXCEPTION_ID_1,
            body=body,
            current_user=PLATFORM_ADMIN_USER,  # wrong role for security exception
            svc=svc,
        )

    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_wrong_role_error_includes_required_role() -> None:
    from fastapi import HTTPException  # noqa: PLC0415
    from forgeguard.api.routes.remediation import decide_exception  # noqa: PLC0415
    from forgeguard.api.schemas.exception import ExceptionDecisionRequest  # noqa: PLC0415

    svc = _make_service()
    body = ExceptionDecisionRequest(decision="approved", decision_comment=DECISION_COMMENT)

    with pytest.raises(HTTPException) as exc_info:
        await decide_exception(
            exception_id=EXCEPTION_ID_1,
            body=body,
            current_user=PLATFORM_ADMIN_USER,
            svc=svc,
        )

    assert "security_reviewer" in str(exc_info.value.detail)


# ---------------------------------------------------------------------------
# POST /api/v1/exceptions/{id}/decide — 409 already decided
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_already_decided_raises_http_409() -> None:
    from fastapi import HTTPException  # noqa: PLC0415
    from forgeguard.api.routes.remediation import decide_exception  # noqa: PLC0415
    from forgeguard.api.schemas.exception import ExceptionDecisionRequest  # noqa: PLC0415

    svc = _make_service(exception_row={**EXCEPTION_ROW, "status": "approved"})
    body = ExceptionDecisionRequest(decision="approved", decision_comment=DECISION_COMMENT)

    with pytest.raises(HTTPException) as exc_info:
        await decide_exception(
            exception_id=EXCEPTION_ID_1,
            body=body,
            current_user=SECURITY_REVIEWER_USER,
            svc=svc,
        )

    assert exc_info.value.status_code == 409


# ---------------------------------------------------------------------------
# POST /api/v1/exceptions/{id}/decide — 404 exception not found
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_exception_not_found_raises_http_404() -> None:
    from fastapi import HTTPException  # noqa: PLC0415
    from forgeguard.api.routes.remediation import decide_exception  # noqa: PLC0415
    from forgeguard.api.schemas.exception import ExceptionDecisionRequest  # noqa: PLC0415

    exc_repo = MagicMock()
    exc_repo.get_by_id = AsyncMock(return_value=None)
    find_repo = MagicMock()

    from forgeguard.services.remediation.exception_service import ExceptionService  # noqa: PLC0415
    svc = ExceptionService(exc_repo, find_repo, None)
    body = ExceptionDecisionRequest(decision="approved", decision_comment=DECISION_COMMENT)

    with pytest.raises(HTTPException) as exc_info:
        await decide_exception(
            exception_id=uuid.uuid4(),
            body=body,
            current_user=SECURITY_REVIEWER_USER,
            svc=svc,
        )

    assert exc_info.value.status_code == 404


# ---------------------------------------------------------------------------
# POST /api/v1/exceptions/{id}/decide — 400 finding already resolved
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_finding_resolved_raises_http_400() -> None:
    from fastapi import HTTPException  # noqa: PLC0415
    from forgeguard.api.routes.remediation import decide_exception  # noqa: PLC0415
    from forgeguard.api.schemas.exception import ExceptionDecisionRequest  # noqa: PLC0415

    svc = _make_service(finding_row={**FINDING_SECURITY_ROW, "status": "remediated"})
    body = ExceptionDecisionRequest(decision="approved", decision_comment=DECISION_COMMENT)

    with pytest.raises(HTTPException) as exc_info:
        await decide_exception(
            exception_id=EXCEPTION_ID_1,
            body=body,
            current_user=SECURITY_REVIEWER_USER,
            svc=svc,
        )

    assert exc_info.value.status_code == 400


# ---------------------------------------------------------------------------
# GET /api/v1/exceptions — list with filters
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_exceptions_returns_items() -> None:
    from forgeguard.api.routes.remediation import list_exceptions  # noqa: PLC0415

    exc_repo = MagicMock()
    exc_repo.list_by_status_and_role = AsyncMock(return_value=[EXCEPTION_ROW])
    exc_repo.count_by_status_and_role = AsyncMock(return_value=1)

    result = await list_exceptions(
        current_user=SECURITY_REVIEWER_USER,
        exception_repo=exc_repo,
        status="pending",
        approver_role="security_reviewer",
        cursor=None,
        limit=20,
    )

    assert len(result.items) == 1
    assert result.total == 1


@pytest.mark.asyncio
async def test_list_exceptions_total_matches_count() -> None:
    from forgeguard.api.routes.remediation import list_exceptions  # noqa: PLC0415

    exc_repo = MagicMock()
    exc_repo.list_by_status_and_role = AsyncMock(return_value=[EXCEPTION_ROW])
    exc_repo.count_by_status_and_role = AsyncMock(return_value=5)

    result = await list_exceptions(
        current_user=SECURITY_REVIEWER_USER,
        exception_repo=exc_repo,
        status="pending",
        approver_role="security_reviewer",
        cursor=None,
        limit=20,
    )

    assert result.total == 5


@pytest.mark.asyncio
async def test_list_exceptions_cursor_present_when_rows() -> None:
    from forgeguard.api.routes.remediation import list_exceptions  # noqa: PLC0415

    exc_repo = MagicMock()
    exc_repo.list_by_status_and_role = AsyncMock(return_value=[EXCEPTION_ROW])
    exc_repo.count_by_status_and_role = AsyncMock(return_value=1)

    result = await list_exceptions(
        current_user=SECURITY_REVIEWER_USER,
        exception_repo=exc_repo,
        status=None,
        approver_role=None,
        cursor=None,
        limit=20,
    )

    assert result.cursor is not None


@pytest.mark.asyncio
async def test_list_exceptions_empty_returns_no_cursor() -> None:
    from forgeguard.api.routes.remediation import list_exceptions  # noqa: PLC0415

    exc_repo = MagicMock()
    exc_repo.list_by_status_and_role = AsyncMock(return_value=[])
    exc_repo.count_by_status_and_role = AsyncMock(return_value=0)

    result = await list_exceptions(
        current_user=SECURITY_REVIEWER_USER,
        exception_repo=exc_repo,
        status="pending",
        approver_role=None,
        cursor=None,
        limit=20,
    )

    assert result.cursor is None
    assert result.total == 0
    assert result.items == []


@pytest.mark.asyncio
async def test_list_exceptions_passes_filters_to_repo() -> None:
    from forgeguard.api.routes.remediation import list_exceptions  # noqa: PLC0415

    exc_repo = MagicMock()
    exc_repo.list_by_status_and_role = AsyncMock(return_value=[])
    exc_repo.count_by_status_and_role = AsyncMock(return_value=0)

    await list_exceptions(
        current_user=PLATFORM_ADMIN_USER,
        exception_repo=exc_repo,
        status="pending",
        approver_role="security_reviewer",
        cursor=None,
        limit=10,
    )

    exc_repo.list_by_status_and_role.assert_awaited_once_with(
        status="pending",
        approver_role="security_reviewer",
        cursor=None,
        limit=10,
    )
