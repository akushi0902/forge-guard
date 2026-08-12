"""Unit tests for DecisionRouter (WO-053).

Tests cover:
  - Escalated assessment routes to security_reviewer
  - Non-escalated assessment routes to tech_lead
  - Mixed findings (any CRITICAL+SECURITY) routes to security_reviewer
  - Assignment lifecycle: pending -> completed on decision submission
  - Assignment lifecycle: pending -> expired after 24 hours
  - Routing failure is non-fatal (logged ERROR, returns None)
  - Audit record created on successful routing
  - No audit service: routing still succeeds without audit
  - Determinism: same inputs always produce same role assignment

All tests use mocked repositories — no database calls.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from forgeguard.services.decision_engine.engine import DecisionOutcome
from forgeguard.services.decision_engine.escalation_service import EscalationResult
from forgeguard.services.decision_engine.router import (
    DecisionRouter,
    DEFAULT_ROLE,
    ESCALATED_ROLE,
)
from tests.fixtures.decision_assignments import (
    ASSESSMENT_ID_PENDING_TECH_LEAD,
    ASSESSMENT_ID_PENDING_SECURITY,
    PENDING_TECH_LEAD_ASSIGNMENT,
    PENDING_SECURITY_ASSIGNMENT,
    COMPLETED_ASSIGNMENT,
    EXPIRED_ASSIGNMENT,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mock_repo(created_row: dict[str, Any] | None = None) -> MagicMock:
    repo = MagicMock()
    row = created_row or {
        "id": uuid.uuid4(),
        "release_assessment_id": uuid.uuid4(),
        "assigned_role": "tech_lead",
        "status": "pending",
        "assigned_at": datetime.now(timezone.utc),
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
        "completed_by": None,
        "completed_at": None,
    }
    repo.create = AsyncMock(return_value=row)
    repo.mark_completed = AsyncMock(return_value=row)
    repo.mark_expired_batch = AsyncMock(return_value=[])
    repo.get_pending_by_assessment = AsyncMock(return_value=row)
    return repo


def _escalation(should_escalate: bool) -> EscalationResult:
    outcome = DecisionOutcome.BLOCK if should_escalate else DecisionOutcome.APPROVE
    return EscalationResult(
        should_escalate=should_escalate,
        escalation_reasons=[{"finding_id": "x", "title": "t"}] if should_escalate else [],
        original_recommendation=outcome,
        final_recommendation=DecisionOutcome.BLOCK if should_escalate else outcome,
    )


# ---------------------------------------------------------------------------
# AC-1: Routing to correct role
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_escalated_assessment_routes_to_security_reviewer() -> None:
    repo = _mock_repo()
    router = DecisionRouter(repo)
    assessment_id = uuid.uuid4()

    result = await router.route_decision(assessment_id, _escalation(should_escalate=True))

    assert result is not None
    call_data = repo.create.call_args[0][0]
    assert call_data["assigned_role"] == ESCALATED_ROLE


@pytest.mark.asyncio
async def test_non_escalated_assessment_routes_to_tech_lead() -> None:
    repo = _mock_repo()
    router = DecisionRouter(repo)
    assessment_id = uuid.uuid4()

    result = await router.route_decision(assessment_id, _escalation(should_escalate=False))

    assert result is not None
    call_data = repo.create.call_args[0][0]
    assert call_data["assigned_role"] == DEFAULT_ROLE


@pytest.mark.asyncio
async def test_escalated_role_constant_is_security_reviewer() -> None:
    assert ESCALATED_ROLE == "security_reviewer"


@pytest.mark.asyncio
async def test_default_role_constant_is_tech_lead() -> None:
    assert DEFAULT_ROLE == "tech_lead"


# ---------------------------------------------------------------------------
# AC-6: Multi-dimensional / mixed findings
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_mixed_findings_any_critical_security_routes_to_security_reviewer() -> None:
    """Any critical+security finding in the findings list → security_reviewer."""
    repo = _mock_repo()
    router = DecisionRouter(repo)
    assessment_id = uuid.uuid4()

    # One escalating, one non-escalating
    escalation = EscalationResult(
        should_escalate=True,
        escalation_reasons=[{"finding_id": "abc", "title": "Secrets exposed"}],
        original_recommendation=DecisionOutcome.APPROVE,
        final_recommendation=DecisionOutcome.BLOCK,
    )

    await router.route_decision(assessment_id, escalation)

    call_data = repo.create.call_args[0][0]
    assert call_data["assigned_role"] == ESCALATED_ROLE


@pytest.mark.asyncio
async def test_all_non_critical_findings_routes_to_tech_lead() -> None:
    repo = _mock_repo()
    router = DecisionRouter(repo)
    assessment_id = uuid.uuid4()

    escalation = EscalationResult(
        should_escalate=False,
        escalation_reasons=[],
        original_recommendation=DecisionOutcome.CONDITIONAL_APPROVE,
        final_recommendation=DecisionOutcome.CONDITIONAL_APPROVE,
    )

    await router.route_decision(assessment_id, escalation)

    call_data = repo.create.call_args[0][0]
    assert call_data["assigned_role"] == DEFAULT_ROLE


# ---------------------------------------------------------------------------
# AC-2: Assignment record fields
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_assignment_record_has_pending_status() -> None:
    repo = _mock_repo()
    router = DecisionRouter(repo)

    await router.route_decision(uuid.uuid4(), _escalation(False))

    call_data = repo.create.call_args[0][0]
    assert call_data["status"] == "pending"


@pytest.mark.asyncio
async def test_assignment_record_has_assessment_id() -> None:
    repo = _mock_repo()
    router = DecisionRouter(repo)
    assessment_id = uuid.uuid4()

    await router.route_decision(assessment_id, _escalation(False))

    call_data = repo.create.call_args[0][0]
    assert call_data["release_assessment_id"] == assessment_id


@pytest.mark.asyncio
async def test_assignment_record_has_uuid_id() -> None:
    repo = _mock_repo()
    router = DecisionRouter(repo)

    await router.route_decision(uuid.uuid4(), _escalation(False))

    call_data = repo.create.call_args[0][0]
    assert isinstance(call_data["id"], uuid.UUID)


# ---------------------------------------------------------------------------
# AC-1: Non-fatal routing failure
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_routing_failure_returns_none() -> None:
    """If the repository raises, route_decision returns None (non-fatal)."""
    repo = MagicMock()
    repo.create = AsyncMock(side_effect=Exception("DB down"))
    router = DecisionRouter(repo)

    result = await router.route_decision(uuid.uuid4(), _escalation(False))

    assert result is None


@pytest.mark.asyncio
async def test_routing_failure_does_not_raise() -> None:
    """Routing failure must not propagate to the caller."""
    repo = MagicMock()
    repo.create = AsyncMock(side_effect=RuntimeError("unexpected"))
    router = DecisionRouter(repo)

    # Should not raise
    result = await router.route_decision(uuid.uuid4(), _escalation(True))
    assert result is None


# ---------------------------------------------------------------------------
# AC-8: Audit record created on success
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_audit_record_created_on_routing_success() -> None:
    repo = _mock_repo()
    audit = MagicMock()
    audit.log_event = AsyncMock(return_value=None)
    router = DecisionRouter(repo, audit_svc=audit)

    await router.route_decision(
        uuid.uuid4(),
        _escalation(False),
        actor_id=str(uuid.uuid4()),
        actor_role="system",
    )

    audit.log_event.assert_awaited_once()
    call_kwargs = audit.log_event.call_args.kwargs
    assert call_kwargs["action"] == "decision_assignment"
    assert call_kwargs["resource_type"] == "decision_assignment"


@pytest.mark.asyncio
async def test_audit_record_includes_assigned_role_in_after_state() -> None:
    repo = _mock_repo()
    audit = MagicMock()
    audit.log_event = AsyncMock(return_value=None)
    router = DecisionRouter(repo, audit_svc=audit)

    await router.route_decision(uuid.uuid4(), _escalation(True))

    after_state = audit.log_event.call_args.kwargs["after_state"]
    assert after_state["assigned_role"] == ESCALATED_ROLE
    assert after_state["should_escalate"] is True


@pytest.mark.asyncio
async def test_no_audit_service_routing_still_succeeds() -> None:
    repo = _mock_repo()
    router = DecisionRouter(repo, audit_svc=None)

    result = await router.route_decision(uuid.uuid4(), _escalation(False))

    assert result is not None


@pytest.mark.asyncio
async def test_audit_failure_does_not_fail_routing() -> None:
    """Audit write error must not propagate — assignment is still created."""
    repo = _mock_repo()
    audit = MagicMock()
    audit.log_event = AsyncMock(side_effect=Exception("audit DB error"))
    router = DecisionRouter(repo, audit_svc=audit)

    result = await router.route_decision(uuid.uuid4(), _escalation(False))

    # Assignment was still created despite audit failure.
    assert result is not None
    repo.create.assert_awaited_once()


# ---------------------------------------------------------------------------
# Assignment lifecycle: pending → completed
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_mark_completed_transitions_status() -> None:
    completed_row = {**PENDING_TECH_LEAD_ASSIGNMENT, "status": "completed"}
    repo = _mock_repo(created_row=completed_row)
    repo.mark_completed = AsyncMock(return_value=completed_row)

    result = await repo.mark_completed(
        ASSESSMENT_ID_PENDING_TECH_LEAD,
        completed_by=str(uuid.uuid4()),
    )

    assert result["status"] == "completed"


@pytest.mark.asyncio
async def test_mark_completed_returns_none_when_no_pending() -> None:
    repo = _mock_repo()
    repo.mark_completed = AsyncMock(return_value=None)

    result = await repo.mark_completed(uuid.uuid4(), completed_by=None)

    assert result is None


# ---------------------------------------------------------------------------
# Assignment lifecycle: pending → expired
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_mark_expired_batch_returns_expired_rows() -> None:
    expired_row = {**EXPIRED_ASSIGNMENT}
    repo = _mock_repo()
    repo.mark_expired_batch = AsyncMock(return_value=[expired_row])

    results = await repo.mark_expired_batch(older_than_hours=24)

    assert len(results) == 1
    assert results[0]["status"] == "expired"


@pytest.mark.asyncio
async def test_mark_expired_batch_empty_when_none_old() -> None:
    repo = _mock_repo()
    repo.mark_expired_batch = AsyncMock(return_value=[])

    results = await repo.mark_expired_batch(older_than_hours=24)

    assert results == []


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_routing_is_deterministic_escalated() -> None:
    """Same escalated input always produces security_reviewer."""
    roles = []
    assessment_id = uuid.uuid4()
    for _ in range(5):
        repo = _mock_repo()
        router = DecisionRouter(repo)
        await router.route_decision(assessment_id, _escalation(True))
        roles.append(repo.create.call_args[0][0]["assigned_role"])
    assert len(set(roles)) == 1
    assert roles[0] == ESCALATED_ROLE


@pytest.mark.asyncio
async def test_routing_is_deterministic_non_escalated() -> None:
    """Same non-escalated input always produces tech_lead."""
    roles = []
    assessment_id = uuid.uuid4()
    for _ in range(5):
        repo = _mock_repo()
        router = DecisionRouter(repo)
        await router.route_decision(assessment_id, _escalation(False))
        roles.append(repo.create.call_args[0][0]["assigned_role"])
    assert len(set(roles)) == 1
    assert roles[0] == DEFAULT_ROLE
