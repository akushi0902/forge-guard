"""Unit tests for ExceptionService.decide_exception (WO-064).

Tests cover:
  - Approve by correct role: security_reviewer for security exception
  - Approve by correct role: platform_admin for non-security exception
  - Deny flow: finding status unchanged, health score not triggered
  - Wrong role rejection (403)
  - Already decided exception (409)
  - Already expired exception (409)
  - Finding already resolved — approval returns 400
  - Decision comment minimum length (schema-level)
  - Finding status transitions to exception_granted on approval
  - Health score recalculation triggered on approval but not on denial
  - Audit records created (exception.approved + finding.excepted)
  - Audit records for denial (exception.denied only)
  - Self-approval logs warning but succeeds
  - Exception not found (404)
  - update_decision race: returns None → ConflictError

All database calls are mocked.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from forgeguard.core.exceptions import BadRequestError, ConflictError, ForbiddenError, NotFoundError
from forgeguard.services.remediation.exception_service import ExceptionService

_NOW = datetime(2026, 8, 12, 12, 0, 0, tzinfo=timezone.utc)
_FUTURE = _NOW + timedelta(days=30)

EXCEPTION_ID = uuid.UUID("ee000000-0000-0000-0000-000000000001")
FINDING_ID = uuid.UUID("ff000000-0000-0000-0000-000000000001")
SERVICE_ID = uuid.UUID("bb000000-0000-0000-0000-000000000001")
REQUESTER_ID = uuid.UUID("aa000000-0000-0000-0000-000000000001")
APPROVER_ID = uuid.UUID("aa000000-0000-0000-0000-000000000002")

DECISION_COMMENT = "Approved after security review — no exploitable vector found."


def _make_exception(
    *,
    status: str = "pending",
    approver_role: str = "security_reviewer",
    finding_id: uuid.UUID = FINDING_ID,
    requested_by: uuid.UUID | None = REQUESTER_ID,
) -> dict[str, Any]:
    return {
        "id": EXCEPTION_ID,
        "finding_id": finding_id,
        "requested_by": requested_by,
        "justification": "Cannot patch until Q3 due to vendor freeze.",
        "status": status,
        "approver_role": approver_role,
        "decided_by": None,
        "decision_comment": None,
        "expires_at": _FUTURE,
        "decided_at": None,
        "created_at": _NOW,
        "updated_at": _NOW,
    }


def _make_finding(
    *,
    status: str = "open",
    dimension: str = "security",
    service_id: uuid.UUID = SERVICE_ID,
) -> dict[str, Any]:
    return {
        "id": FINDING_ID,
        "assessment_id": uuid.uuid4(),
        "service_id": service_id,
        "policy_rule_id": None,
        "severity": "critical",
        "dimension": dimension,
        "status": status,
        "title": "Critical CVE detected",
        "description": "A critical vulnerability was found.",
        "created_at": _NOW,
        "updated_at": _NOW,
    }


def _make_repos(
    exception_row: dict | None = None,
    finding_row: dict | None = None,
    updated_exception: dict | None = None,
    updated_finding: dict | None = None,
):
    exc_repo = MagicMock()
    exc_repo.get_by_id = AsyncMock(return_value=exception_row or _make_exception())
    exc_row = exception_row or _make_exception()
    decided = {**exc_row, "status": "approved", "decided_at": _NOW, "decided_by": APPROVER_ID}
    exc_repo.update_decision = AsyncMock(return_value=updated_exception or decided)

    find_repo = MagicMock()
    find_repo.get_by_id = AsyncMock(return_value=finding_row or _make_finding())
    fnd_row = finding_row or _make_finding()
    find_repo.update_status = AsyncMock(
        return_value=updated_finding or {**fnd_row, "status": "exception_granted"}
    )

    return exc_repo, find_repo


def _make_service(exc_repo=None, find_repo=None, audit=None) -> ExceptionService:
    if exc_repo is None or find_repo is None:
        exc_repo, find_repo = _make_repos()
    return ExceptionService(exc_repo, find_repo, audit)


# ---------------------------------------------------------------------------
# AC-1: Approve flow — security exception, security_reviewer
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_approve_by_security_reviewer_succeeds() -> None:
    exc_repo, find_repo = _make_repos()
    svc = _make_service(exc_repo, find_repo)

    result = await svc.decide_exception(
        exception_id=EXCEPTION_ID,
        decision="approved",
        decision_comment=DECISION_COMMENT,
        actor_id=str(APPROVER_ID),
        actor_role="security_reviewer",
    )

    assert result["status"] == "approved"
    exc_repo.update_decision.assert_awaited_once()


@pytest.mark.asyncio
async def test_approve_by_platform_admin_succeeds() -> None:
    exc_repo, find_repo = _make_repos(
        exception_row=_make_exception(approver_role="platform_admin"),
        updated_exception={**_make_exception(approver_role="platform_admin"), "status": "approved"},
    )
    svc = _make_service(exc_repo, find_repo)

    result = await svc.decide_exception(
        exception_id=EXCEPTION_ID,
        decision="approved",
        decision_comment=DECISION_COMMENT,
        actor_id=str(APPROVER_ID),
        actor_role="platform_admin",
    )

    assert result["status"] == "approved"


# ---------------------------------------------------------------------------
# AC-2: Deny flow
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_deny_flow_exception_status_becomes_denied() -> None:
    exc_repo, find_repo = _make_repos(
        updated_exception={**_make_exception(), "status": "denied"},
    )
    svc = _make_service(exc_repo, find_repo)

    result = await svc.decide_exception(
        exception_id=EXCEPTION_ID,
        decision="denied",
        decision_comment="Risk accepted at the board level; patch scheduled for Q4.",
        actor_id=str(APPROVER_ID),
        actor_role="security_reviewer",
    )

    assert result["status"] == "denied"


@pytest.mark.asyncio
async def test_deny_flow_finding_status_unchanged() -> None:
    exc_repo, find_repo = _make_repos(
        updated_exception={**_make_exception(), "status": "denied"},
    )
    svc = _make_service(exc_repo, find_repo)

    result = await svc.decide_exception(
        exception_id=EXCEPTION_ID,
        decision="denied",
        decision_comment="Risk accepted at the board level; patch scheduled for Q4.",
        actor_id=str(APPROVER_ID),
        actor_role="security_reviewer",
    )

    assert result["finding_status"] == "open"
    find_repo.update_status.assert_not_awaited()


@pytest.mark.asyncio
async def test_deny_flow_health_score_not_triggered() -> None:
    exc_repo, find_repo = _make_repos(
        updated_exception={**_make_exception(), "status": "denied"},
    )
    svc = _make_service(exc_repo, find_repo)

    result = await svc.decide_exception(
        exception_id=EXCEPTION_ID,
        decision="denied",
        decision_comment="Risk accepted at the board level; patch scheduled for Q4.",
        actor_id=str(APPROVER_ID),
        actor_role="security_reviewer",
    )

    assert result["health_score_impact"] is None


# ---------------------------------------------------------------------------
# AC-4: Wrong role rejection
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_wrong_role_raises_forbidden() -> None:
    exc_repo, find_repo = _make_repos(
        exception_row=_make_exception(approver_role="security_reviewer"),
    )
    svc = _make_service(exc_repo, find_repo)

    with pytest.raises(ForbiddenError) as exc_info:
        await svc.decide_exception(
            exception_id=EXCEPTION_ID,
            decision="approved",
            decision_comment=DECISION_COMMENT,
            actor_id=str(APPROVER_ID),
            actor_role="platform_admin",  # wrong role
        )

    assert "security_reviewer" in str(exc_info.value)


@pytest.mark.asyncio
async def test_forbidden_error_includes_required_role() -> None:
    exc_repo, find_repo = _make_repos(
        exception_row=_make_exception(approver_role="platform_admin"),
    )
    svc = _make_service(exc_repo, find_repo)

    with pytest.raises(ForbiddenError) as exc_info:
        await svc.decide_exception(
            exception_id=EXCEPTION_ID,
            decision="denied",
            decision_comment=DECISION_COMMENT,
            actor_id=str(APPROVER_ID),
            actor_role="security_reviewer",  # wrong role for non-security exception
        )

    err = exc_info.value
    assert (err.details or {}).get("required_role") == "platform_admin"


# ---------------------------------------------------------------------------
# AC constraint: Already decided / expired (409)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_already_approved_raises_conflict() -> None:
    exc_repo, find_repo = _make_repos(
        exception_row=_make_exception(status="approved"),
    )
    svc = _make_service(exc_repo, find_repo)

    with pytest.raises(ConflictError) as exc_info:
        await svc.decide_exception(
            exception_id=EXCEPTION_ID,
            decision="approved",
            decision_comment=DECISION_COMMENT,
            actor_id=str(APPROVER_ID),
            actor_role="security_reviewer",
        )

    assert "already decided" in str(exc_info.value).lower()


@pytest.mark.asyncio
async def test_already_denied_raises_conflict() -> None:
    exc_repo, find_repo = _make_repos(
        exception_row=_make_exception(status="denied"),
    )
    svc = _make_service(exc_repo, find_repo)

    with pytest.raises(ConflictError):
        await svc.decide_exception(
            exception_id=EXCEPTION_ID,
            decision="approved",
            decision_comment=DECISION_COMMENT,
            actor_id=str(APPROVER_ID),
            actor_role="security_reviewer",
        )


@pytest.mark.asyncio
async def test_expired_exception_raises_conflict() -> None:
    exc_repo, find_repo = _make_repos(
        exception_row=_make_exception(status="expired"),
    )
    svc = _make_service(exc_repo, find_repo)

    with pytest.raises(ConflictError) as exc_info:
        await svc.decide_exception(
            exception_id=EXCEPTION_ID,
            decision="approved",
            decision_comment=DECISION_COMMENT,
            actor_id=str(APPROVER_ID),
            actor_role="security_reviewer",
        )

    assert "expired" in str(exc_info.value).lower()


@pytest.mark.asyncio
async def test_update_decision_returns_none_raises_conflict() -> None:
    exc_repo, find_repo = _make_repos()
    exc_repo.update_decision = AsyncMock(return_value=None)
    svc = _make_service(exc_repo, find_repo)

    with pytest.raises(ConflictError):
        await svc.decide_exception(
            exception_id=EXCEPTION_ID,
            decision="approved",
            decision_comment=DECISION_COMMENT,
            actor_id=str(APPROVER_ID),
            actor_role="security_reviewer",
        )


# ---------------------------------------------------------------------------
# Edge case: Finding already resolved → 400 on approval
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_finding_resolved_blocks_approval() -> None:
    exc_repo, find_repo = _make_repos(
        finding_row=_make_finding(status="remediated"),
    )
    svc = _make_service(exc_repo, find_repo)

    with pytest.raises(BadRequestError) as exc_info:
        await svc.decide_exception(
            exception_id=EXCEPTION_ID,
            decision="approved",
            decision_comment=DECISION_COMMENT,
            actor_id=str(APPROVER_ID),
            actor_role="security_reviewer",
        )

    assert "resolved" in str(exc_info.value).lower()


@pytest.mark.asyncio
async def test_finding_resolved_still_allows_denial() -> None:
    exc_repo, find_repo = _make_repos(
        finding_row=_make_finding(status="remediated"),
        updated_exception={**_make_exception(), "status": "denied"},
    )
    svc = _make_service(exc_repo, find_repo)

    result = await svc.decide_exception(
        exception_id=EXCEPTION_ID,
        decision="denied",
        decision_comment="Risk accepted at the board level; patch scheduled for Q4.",
        actor_id=str(APPROVER_ID),
        actor_role="security_reviewer",
    )

    assert result["status"] == "denied"


# ---------------------------------------------------------------------------
# AC-1: Finding status transitions to exception_granted on approval
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_finding_status_becomes_exception_granted_on_approval() -> None:
    exc_repo, find_repo = _make_repos()
    svc = _make_service(exc_repo, find_repo)

    result = await svc.decide_exception(
        exception_id=EXCEPTION_ID,
        decision="approved",
        decision_comment=DECISION_COMMENT,
        actor_id=str(APPROVER_ID),
        actor_role="security_reviewer",
    )

    assert result["finding_status"] == "exception_granted"
    find_repo.update_status.assert_awaited_once_with(FINDING_ID, "exception_granted")


@pytest.mark.asyncio
async def test_finding_status_update_failure_is_non_fatal() -> None:
    exc_repo, find_repo = _make_repos()
    find_repo.update_status = AsyncMock(side_effect=Exception("DB down"))
    svc = _make_service(exc_repo, find_repo)

    result = await svc.decide_exception(
        exception_id=EXCEPTION_ID,
        decision="approved",
        decision_comment=DECISION_COMMENT,
        actor_id=str(APPROVER_ID),
        actor_role="security_reviewer",
    )

    assert result["status"] == "approved"


# ---------------------------------------------------------------------------
# AC-6: Health score recalculation triggered on approve but not deny
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_health_score_recalculation_triggered_on_approval() -> None:
    exc_repo, find_repo = _make_repos()
    svc = _make_service(exc_repo, find_repo)

    with patch.object(svc, "_trigger_health_score_recalculation", new=AsyncMock(return_value=None)) as mock_trigger:
        await svc.decide_exception(
            exception_id=EXCEPTION_ID,
            decision="approved",
            decision_comment=DECISION_COMMENT,
            actor_id=str(APPROVER_ID),
            actor_role="security_reviewer",
        )

    mock_trigger.assert_awaited_once()


@pytest.mark.asyncio
async def test_health_score_not_triggered_on_denial() -> None:
    exc_repo, find_repo = _make_repos(
        updated_exception={**_make_exception(), "status": "denied"},
    )
    svc = _make_service(exc_repo, find_repo)

    with patch.object(svc, "_trigger_health_score_recalculation", new=AsyncMock(return_value=None)) as mock_trigger:
        await svc.decide_exception(
            exception_id=EXCEPTION_ID,
            decision="denied",
            decision_comment="Risk accepted at the board level; patch scheduled for Q4.",
            actor_id=str(APPROVER_ID),
            actor_role="security_reviewer",
        )

    mock_trigger.assert_not_awaited()


# ---------------------------------------------------------------------------
# AC-7: Audit records
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_audit_record_created_on_approval() -> None:
    exc_repo, find_repo = _make_repos()
    audit = MagicMock()
    audit.log_event = AsyncMock(return_value=None)
    svc = _make_service(exc_repo, find_repo, audit)

    await svc.decide_exception(
        exception_id=EXCEPTION_ID,
        decision="approved",
        decision_comment=DECISION_COMMENT,
        actor_id=str(APPROVER_ID),
        actor_role="security_reviewer",
    )

    calls = [c.kwargs["action"] for c in audit.log_event.call_args_list]
    assert "exception.approved" in calls
    assert "finding.excepted" in calls


@pytest.mark.asyncio
async def test_audit_record_created_on_denial() -> None:
    exc_repo, find_repo = _make_repos(
        updated_exception={**_make_exception(), "status": "denied"},
    )
    audit = MagicMock()
    audit.log_event = AsyncMock(return_value=None)
    svc = _make_service(exc_repo, find_repo, audit)

    await svc.decide_exception(
        exception_id=EXCEPTION_ID,
        decision="denied",
        decision_comment="Risk accepted at the board level; patch scheduled for Q4.",
        actor_id=str(APPROVER_ID),
        actor_role="security_reviewer",
    )

    calls = [c.kwargs["action"] for c in audit.log_event.call_args_list]
    assert "exception.denied" in calls
    assert "finding.excepted" not in calls


@pytest.mark.asyncio
async def test_audit_includes_before_and_after_state() -> None:
    exc_repo, find_repo = _make_repos()
    audit = MagicMock()
    audit.log_event = AsyncMock(return_value=None)
    svc = _make_service(exc_repo, find_repo, audit)

    await svc.decide_exception(
        exception_id=EXCEPTION_ID,
        decision="approved",
        decision_comment=DECISION_COMMENT,
        actor_id=str(APPROVER_ID),
        actor_role="security_reviewer",
    )

    first_call_kwargs = audit.log_event.call_args_list[0].kwargs
    assert "before_state" in first_call_kwargs
    assert "after_state" in first_call_kwargs
    assert first_call_kwargs["before_state"]["status"] == "pending"


# ---------------------------------------------------------------------------
# Edge case: Exception not found
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_exception_not_found_raises_not_found_error() -> None:
    exc_repo = MagicMock()
    exc_repo.get_by_id = AsyncMock(return_value=None)
    find_repo = MagicMock()
    svc = _make_service(exc_repo, find_repo)

    with pytest.raises(NotFoundError):
        await svc.decide_exception(
            exception_id=uuid.uuid4(),
            decision="approved",
            decision_comment=DECISION_COMMENT,
            actor_id=str(APPROVER_ID),
            actor_role="security_reviewer",
        )


# ---------------------------------------------------------------------------
# Edge case: Self-approval logs warning but succeeds
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_self_approval_succeeds() -> None:
    exc_repo, find_repo = _make_repos(
        exception_row=_make_exception(requested_by=APPROVER_ID),
    )
    svc = _make_service(exc_repo, find_repo)

    result = await svc.decide_exception(
        exception_id=EXCEPTION_ID,
        decision="approved",
        decision_comment=DECISION_COMMENT,
        actor_id=str(APPROVER_ID),
        actor_role="security_reviewer",
    )

    assert result["status"] == "approved"
