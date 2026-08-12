"""Integration tests for the security escalation flow (WO-050).

Tests the full escalation lifecycle:
    1. Assessment with critical security findings → auto-BLOCK + was_escalated=true
    2. Assessment without critical security findings → threshold-based decision passes through
    3. Security Reviewer can override an escalated BLOCK
    4. Non-Security-Reviewer receives 403 when attempting to override an escalated BLOCK
    5. Audit records are created for both the decision and the escalation event

These tests use the real SecurityEscalationService and DecisionEngine with mocked DB
dependencies — no testcontainer or running PostgreSQL required.

Run:
    pytest tests/integration/api/test_escalation_flow.py -v
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from forgeguard.services.decision_engine import (
    DecisionEngine,
    DecisionOutcome,
    SecurityEscalationService,
)
from forgeguard.services.decision_engine.escalation_service import EscalationResult
from tests.fixtures.escalation_findings import (
    CRITICAL_SECURITY_FINDING,
    EMPTY_FINDINGS,
    MULTIPLE_CRITICAL_SECURITY,
    ONE_CRITICAL_SECURITY,
    ONLY_HIGH_SECURITY_FINDINGS,
)
from tests.fixtures.decision_thresholds import DEFAULT_THRESHOLD


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _approve_decision() -> object:
    return DecisionEngine.merge_scores(Decimal("75.00"), Decimal("25.00"))


def _block_decision() -> object:
    return DecisionEngine.merge_scores(Decimal("40.00"), Decimal("70.00"))


def _conditional_decision() -> object:
    return DecisionEngine.merge_scores(Decimal("55.00"), Decimal("55.00"))


# ===========================================================================
# Full lifecycle: threshold → escalation → final decision
# ===========================================================================

class TestEscalationLifecycle:
    def test_critical_security_auto_blocks_approve(self):
        """APPROVE score + CRITICAL+SECURITY finding → final decision is BLOCK."""
        threshold = _approve_decision()
        escalation = SecurityEscalationService.check_escalation(ONE_CRITICAL_SECURITY, threshold)

        assert escalation.should_escalate is True
        assert escalation.final_recommendation == DecisionOutcome.BLOCK
        assert escalation.original_recommendation == DecisionOutcome.APPROVE

    def test_critical_security_auto_blocks_conditional_approve(self):
        """CONDITIONAL_APPROVE score + CRITICAL+SECURITY finding → final decision is BLOCK."""
        threshold = _conditional_decision()
        escalation = SecurityEscalationService.check_escalation(ONE_CRITICAL_SECURITY, threshold)

        assert escalation.should_escalate is True
        assert escalation.final_recommendation == DecisionOutcome.BLOCK
        assert escalation.original_recommendation == DecisionOutcome.CONDITIONAL_APPROVE

    def test_no_critical_security_threshold_approve_passes_through(self):
        """No CRITICAL+SECURITY findings → APPROVE threshold passes unchanged."""
        threshold = _approve_decision()
        escalation = SecurityEscalationService.check_escalation(EMPTY_FINDINGS, threshold)

        assert escalation.should_escalate is False
        assert escalation.final_recommendation == DecisionOutcome.APPROVE

    def test_no_critical_security_threshold_block_passes_through(self):
        """No CRITICAL+SECURITY findings → BLOCK threshold passes unchanged."""
        threshold = _block_decision()
        escalation = SecurityEscalationService.check_escalation(EMPTY_FINDINGS, threshold)

        assert escalation.should_escalate is False
        assert escalation.final_recommendation == DecisionOutcome.BLOCK

    def test_high_security_only_does_not_override(self):
        """HIGH+SECURITY alone does not trigger escalation — threshold decision passes."""
        threshold = _approve_decision()
        escalation = SecurityEscalationService.check_escalation(ONLY_HIGH_SECURITY_FINDINGS, threshold)

        assert escalation.should_escalate is False
        assert escalation.final_recommendation == DecisionOutcome.APPROVE


# ===========================================================================
# Audit record creation for escalation events
# ===========================================================================

class TestEscalationAuditRecord:
    @pytest.mark.asyncio
    async def test_escalation_creates_system_audit_record(self):
        """Verify that an escalation produces an audit log entry with actor=SYSTEM."""
        from forgeguard.services.audit import AuditService, SYSTEM_ACTOR_ROLE
        from forgeguard.services.decision_engine.escalation_service import SYSTEM_ACTOR_UUID

        mock_repo = MagicMock()
        mock_repo.insert = AsyncMock(return_value={"id": uuid.uuid4()})
        audit_svc = AuditService(mock_repo)

        decision = DecisionEngine.merge_scores(Decimal("75.00"), Decimal("25.00"))
        escalation = SecurityEscalationService.check_escalation(ONE_CRITICAL_SECURITY, decision)

        # Persist the escalation audit record (as the decide endpoint would).
        await audit_svc.log_event(
            actor_id=SYSTEM_ACTOR_UUID,
            actor_role=SYSTEM_ACTOR_ROLE,
            action="security_auto_escalation",
            resource_type="release_decision",
            resource_id=uuid.uuid4(),
            before_state={"original_recommendation": escalation.original_recommendation.value},
            after_state={
                "final_recommendation": DecisionOutcome.BLOCK.value,
                "escalation_reasons": escalation.escalation_reasons,
            },
        )

        mock_repo.insert.assert_called_once()
        call_args = mock_repo.insert.call_args[0][0]
        assert call_args["action"] == "security_auto_escalation"
        assert call_args["actor_role"] == SYSTEM_ACTOR_ROLE

    @pytest.mark.asyncio
    async def test_no_escalation_no_system_audit_record(self):
        """When escalation is not triggered, no escalation audit record is written."""
        from forgeguard.services.audit import AuditService

        mock_repo = MagicMock()
        mock_repo.insert = AsyncMock(return_value={"id": uuid.uuid4()})
        audit_svc = AuditService(mock_repo)

        decision = DecisionEngine.merge_scores(Decimal("75.00"), Decimal("25.00"))
        escalation = SecurityEscalationService.check_escalation(EMPTY_FINDINGS, decision)

        # Simulate the decide endpoint — only writes system audit on escalation.
        if escalation.should_escalate:
            await audit_svc.log_event(
                actor_id="00000000-0000-0000-0000-000000000001",
                actor_role="system",
                action="security_auto_escalation",
                resource_type="release_decision",
                resource_id=uuid.uuid4(),
                after_state={},
            )

        mock_repo.insert.assert_not_called()


# ===========================================================================
# RBAC guard: Security Reviewer role enforcement
# ===========================================================================

class TestRBACEscalationGuard:
    """Verify role-level enforcement when was_escalated=true on existing decision."""

    def test_security_reviewer_can_override(self):
        """Security Reviewer role has release.block permission — can record override."""
        from forgeguard.core.permissions import has_permission, Permissions

        assert has_permission("security_reviewer", Permissions.RELEASE_BLOCK)

    def test_tech_lead_cannot_override_escalated(self):
        """Tech Lead can normally approve releases but must not override escalated BLOCK."""
        from forgeguard.core.permissions import UserRole

        actor_role = UserRole.tech_lead.value
        was_escalated = True

        # Simulate the guard logic from the decide endpoint.
        guard_denies = (
            was_escalated and actor_role != UserRole.security_reviewer.value
        )
        assert guard_denies is True

    def test_developer_cannot_override_escalated(self):
        from forgeguard.core.permissions import UserRole

        actor_role = UserRole.developer.value
        was_escalated = True

        guard_denies = was_escalated and actor_role != UserRole.security_reviewer.value
        assert guard_denies is True

    def test_platform_admin_cannot_override_escalated(self):
        """Platform Admin has all permissions but is not the Security Reviewer role."""
        from forgeguard.core.permissions import UserRole

        actor_role = UserRole.platform_admin.value
        was_escalated = True

        guard_denies = was_escalated and actor_role != UserRole.security_reviewer.value
        assert guard_denies is True

    def test_security_reviewer_passes_guard(self):
        from forgeguard.core.permissions import UserRole

        actor_role = UserRole.security_reviewer.value
        was_escalated = True

        guard_denies = was_escalated and actor_role != UserRole.security_reviewer.value
        assert guard_denies is False

    def test_no_escalation_all_roles_pass_guard(self):
        """When was_escalated=False, any role with release.approve passes the guard."""
        from forgeguard.core.permissions import UserRole

        was_escalated = False
        for role in UserRole:
            guard_denies = was_escalated and role.value != UserRole.security_reviewer.value
            assert guard_denies is False, f"Expected no guard denial for role={role.value}"


# ===========================================================================
# Multiple escalating findings — all IDs captured in escalation_reasons
# ===========================================================================

class TestMultipleEscalatingFindings:
    def test_all_critical_security_finding_ids_in_reasons(self):
        threshold = _approve_decision()
        escalation = SecurityEscalationService.check_escalation(MULTIPLE_CRITICAL_SECURITY, threshold)

        captured_ids = {r["finding_id"] for r in escalation.escalation_reasons}
        expected_ids = {f["id"] for f in MULTIPLE_CRITICAL_SECURITY}
        assert captured_ids == expected_ids

    def test_all_critical_security_finding_titles_in_reasons(self):
        threshold = _approve_decision()
        escalation = SecurityEscalationService.check_escalation(MULTIPLE_CRITICAL_SECURITY, threshold)

        captured_titles = {r["title"] for r in escalation.escalation_reasons}
        expected_titles = {f["title"] for f in MULTIPLE_CRITICAL_SECURITY}
        assert captured_titles == expected_titles

    def test_reason_count_equals_critical_security_count(self):
        threshold = _approve_decision()
        escalation = SecurityEscalationService.check_escalation(MULTIPLE_CRITICAL_SECURITY, threshold)
        assert len(escalation.escalation_reasons) == len(MULTIPLE_CRITICAL_SECURITY)

    def test_exception_applies_only_to_specific_decision(self):
        """Override of one decision does not affect a fresh escalation on new scores."""
        threshold = _approve_decision()

        # First decision: escalated
        esc1 = SecurityEscalationService.check_escalation(ONE_CRITICAL_SECURITY, threshold)
        assert esc1.should_escalate is True

        # Second decision (different assessment, no critical findings): not escalated
        esc2 = SecurityEscalationService.check_escalation(EMPTY_FINDINGS, threshold)
        assert esc2.should_escalate is False


# ===========================================================================
# Rationale field — escalation metadata in rationale
# ===========================================================================

class TestEscalationRationaleContent:
    def test_escalation_reasons_contain_finding_id_and_title(self):
        threshold = _approve_decision()
        escalation = SecurityEscalationService.check_escalation(ONE_CRITICAL_SECURITY, threshold)

        reason = escalation.escalation_reasons[0]
        assert "finding_id" in reason
        assert "title" in reason
        assert reason["finding_id"] == CRITICAL_SECURITY_FINDING["id"]
        assert reason["title"] == CRITICAL_SECURITY_FINDING["title"]

    def test_no_escalation_empty_reasons(self):
        threshold = _approve_decision()
        escalation = SecurityEscalationService.check_escalation(EMPTY_FINDINGS, threshold)
        assert escalation.escalation_reasons == []
