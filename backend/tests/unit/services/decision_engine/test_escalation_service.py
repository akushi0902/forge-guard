"""Unit tests for SecurityEscalationService (WO-050).

Tests check_escalation() covering:
    - Single CRITICAL+SECURITY finding triggers escalation
    - Multiple CRITICAL+SECURITY findings — all captured in escalation_reasons
    - CRITICAL finding with non-SECURITY dimension does NOT trigger
    - HIGH+SECURITY finding does NOT trigger
    - MEDIUM+SECURITY finding does NOT trigger
    - LOW+SECURITY finding does NOT trigger
    - Empty findings list → no escalation
    - escalation overrides APPROVE → BLOCK
    - escalation overrides CONDITIONAL_APPROVE → BLOCK
    - escalation overrides BLOCK → BLOCK (unchanged)
    - was_escalated=False passes original recommendation through unchanged
    - Fail-closed: exception during scan → BLOCK + should_escalate=True
    - Findings with missing severity/dimension fields are skipped
    - Unknown severity string is handled without hard failure
    - Perfect Health Score (100) + zero Risk Score → still escalated
    - EscalationResult is frozen (immutable)

All tests are pure — no database, no network, no I/O.

Run:
    pytest tests/unit/services/decision_engine/test_escalation_service.py -v
"""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest

from forgeguard.services.decision_engine.engine import (
    DecisionEngine,
    DecisionOutcome,
    DecisionResult,
)
from forgeguard.services.decision_engine.escalation_service import (
    EscalationResult,
    SecurityEscalationService,
    SYSTEM_ACTOR_UUID,
)
from tests.fixtures.escalation_findings import (
    ALL_SEVERITIES_SECURITY_ONLY,
    CRITICAL_SECURITY_FINDING,
    EMPTY_FINDINGS,
    FINDINGS_WITH_MISSING_FIELDS,
    FINDINGS_WITH_UNKNOWN_SEVERITY,
    HIGH_SECURITY_FINDING,
    LOW_SECURITY_FINDING,
    MEDIUM_SECURITY_FINDING,
    MIXED_WITH_CRITICAL_SECURITY,
    MULTIPLE_CRITICAL_SECURITY,
    NON_SECURITY_DIMENSIONS,
    ONE_CRITICAL_SECURITY,
    ONLY_HIGH_SECURITY_FINDINGS,
    PERFECT_SCORE_WITH_CRITICAL_SECURITY,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _threshold_decision(
    health: str = "70.00",
    risk: str = "30.00",
) -> DecisionResult:
    """Build a DecisionResult via the real engine (no mocking needed)."""
    return DecisionEngine.merge_scores(Decimal(health), Decimal(risk))


def _approve() -> DecisionResult:
    return _threshold_decision("70.00", "30.00")


def _conditional() -> DecisionResult:
    return _threshold_decision("50.00", "60.00")


def _block() -> DecisionResult:
    return _threshold_decision("49.00", "61.00")


# ===========================================================================
# Escalation triggers — critical+security combinations
# ===========================================================================

class TestEscalationTriggered:
    def test_single_critical_security_finding_triggers(self):
        result = SecurityEscalationService.check_escalation(ONE_CRITICAL_SECURITY, _approve())
        assert result.should_escalate is True

    def test_single_critical_security_final_recommendation_is_block(self):
        result = SecurityEscalationService.check_escalation(ONE_CRITICAL_SECURITY, _approve())
        assert result.final_recommendation == DecisionOutcome.BLOCK

    def test_single_critical_security_original_recommendation_preserved(self):
        result = SecurityEscalationService.check_escalation(ONE_CRITICAL_SECURITY, _approve())
        assert result.original_recommendation == DecisionOutcome.APPROVE

    def test_single_critical_security_escalation_reason_captured(self):
        result = SecurityEscalationService.check_escalation(ONE_CRITICAL_SECURITY, _approve())
        assert len(result.escalation_reasons) == 1
        assert result.escalation_reasons[0]["finding_id"] == CRITICAL_SECURITY_FINDING["id"]
        assert result.escalation_reasons[0]["title"] == CRITICAL_SECURITY_FINDING["title"]

    def test_multiple_critical_security_all_captured(self):
        result = SecurityEscalationService.check_escalation(MULTIPLE_CRITICAL_SECURITY, _approve())
        assert result.should_escalate is True
        assert len(result.escalation_reasons) == 3

    def test_multiple_critical_security_all_finding_ids_present(self):
        result = SecurityEscalationService.check_escalation(MULTIPLE_CRITICAL_SECURITY, _approve())
        captured_ids = {r["finding_id"] for r in result.escalation_reasons}
        expected_ids = {f["id"] for f in MULTIPLE_CRITICAL_SECURITY}
        assert captured_ids == expected_ids


# ===========================================================================
# Escalation NOT triggered — wrong severity or dimension
# ===========================================================================

class TestEscalationNotTriggered:
    def test_empty_findings_no_escalation(self):
        result = SecurityEscalationService.check_escalation(EMPTY_FINDINGS, _approve())
        assert result.should_escalate is False

    def test_empty_findings_passthrough_approve(self):
        result = SecurityEscalationService.check_escalation(EMPTY_FINDINGS, _approve())
        assert result.final_recommendation == DecisionOutcome.APPROVE

    def test_empty_findings_passthrough_conditional(self):
        result = SecurityEscalationService.check_escalation(EMPTY_FINDINGS, _conditional())
        assert result.final_recommendation == DecisionOutcome.CONDITIONAL_APPROVE

    def test_empty_findings_passthrough_block(self):
        result = SecurityEscalationService.check_escalation(EMPTY_FINDINGS, _block())
        assert result.final_recommendation == DecisionOutcome.BLOCK

    def test_high_security_finding_does_not_escalate(self):
        result = SecurityEscalationService.check_escalation(ONLY_HIGH_SECURITY_FINDINGS, _approve())
        assert result.should_escalate is False

    def test_medium_security_finding_does_not_escalate(self):
        result = SecurityEscalationService.check_escalation([MEDIUM_SECURITY_FINDING], _approve())
        assert result.should_escalate is False

    def test_low_security_finding_does_not_escalate(self):
        result = SecurityEscalationService.check_escalation([LOW_SECURITY_FINDING], _approve())
        assert result.should_escalate is False

    def test_critical_non_security_dimensions_do_not_escalate(self):
        for finding in NON_SECURITY_DIMENSIONS:
            result = SecurityEscalationService.check_escalation([finding], _approve())
            assert result.should_escalate is False, (
                f"Expected no escalation for dimension={finding['dimension']} "
                f"severity={finding['severity']}"
            )

    def test_all_non_security_criticals_no_escalation(self):
        result = SecurityEscalationService.check_escalation(NON_SECURITY_DIMENSIONS, _approve())
        assert result.should_escalate is False
        assert result.escalation_reasons == []

    def test_high_security_no_escalation_reasons(self):
        result = SecurityEscalationService.check_escalation(ONLY_HIGH_SECURITY_FINDINGS, _approve())
        assert result.escalation_reasons == []

    def test_no_escalation_original_equals_final(self):
        result = SecurityEscalationService.check_escalation(EMPTY_FINDINGS, _approve())
        assert result.original_recommendation == result.final_recommendation


# ===========================================================================
# Override behaviour — escalation always wins over any threshold outcome
# ===========================================================================

class TestEscalationOverridesThreshold:
    def test_escalation_overrides_approve_to_block(self):
        result = SecurityEscalationService.check_escalation(ONE_CRITICAL_SECURITY, _approve())
        assert result.final_recommendation == DecisionOutcome.BLOCK

    def test_escalation_overrides_conditional_to_block(self):
        result = SecurityEscalationService.check_escalation(ONE_CRITICAL_SECURITY, _conditional())
        assert result.final_recommendation == DecisionOutcome.BLOCK
        assert result.original_recommendation == DecisionOutcome.CONDITIONAL_APPROVE

    def test_escalation_leaves_block_as_block(self):
        result = SecurityEscalationService.check_escalation(ONE_CRITICAL_SECURITY, _block())
        assert result.final_recommendation == DecisionOutcome.BLOCK
        assert result.original_recommendation == DecisionOutcome.BLOCK

    def test_perfect_health_score_still_escalated(self):
        perfect_approve = DecisionEngine.merge_scores(Decimal("100.00"), Decimal("0.00"))
        result = SecurityEscalationService.check_escalation(
            PERFECT_SCORE_WITH_CRITICAL_SECURITY, perfect_approve
        )
        assert result.should_escalate is True
        assert result.final_recommendation == DecisionOutcome.BLOCK

    def test_mixed_findings_only_critical_security_escalates(self):
        result = SecurityEscalationService.check_escalation(MIXED_WITH_CRITICAL_SECURITY, _approve())
        assert result.should_escalate is True
        # Only the CRITICAL+SECURITY finding should appear
        assert len(result.escalation_reasons) == 1
        assert result.escalation_reasons[0]["finding_id"] == CRITICAL_SECURITY_FINDING["id"]

    def test_all_severity_security_only_critical_in_reasons(self):
        result = SecurityEscalationService.check_escalation(ALL_SEVERITIES_SECURITY_ONLY, _approve())
        assert result.should_escalate is True
        # Only the CRITICAL severity finding should be in escalation_reasons
        assert len(result.escalation_reasons) == 1
        assert result.escalation_reasons[0]["finding_id"] == CRITICAL_SECURITY_FINDING["id"]


# ===========================================================================
# Fail-closed behaviour
# ===========================================================================

class TestFailClosed:
    def test_exception_during_scan_returns_block(self):
        class BrokenFindings:
            def __iter__(self):
                raise RuntimeError("Simulated findings query failure")

        result = SecurityEscalationService.check_escalation(BrokenFindings(), _approve())
        assert result.final_recommendation == DecisionOutcome.BLOCK

    def test_exception_during_scan_should_escalate_true(self):
        class BrokenFindings:
            def __iter__(self):
                raise RuntimeError("Simulated findings query failure")

        result = SecurityEscalationService.check_escalation(BrokenFindings(), _approve())
        assert result.should_escalate is True

    def test_exception_preserves_original_recommendation(self):
        class BrokenFindings:
            def __iter__(self):
                raise RuntimeError("Simulated findings query failure")

        decision = _approve()
        result = SecurityEscalationService.check_escalation(BrokenFindings(), decision)
        assert result.original_recommendation == DecisionOutcome.APPROVE


# ===========================================================================
# Robustness — edge cases with malformed or partial findings
# ===========================================================================

class TestMalformedFindings:
    def test_missing_severity_field_skipped(self):
        findings = [{"id": str(uuid.uuid4()), "dimension": "security", "title": "No severity"}]
        result = SecurityEscalationService.check_escalation(findings, _approve())
        assert result.should_escalate is False

    def test_missing_dimension_field_skipped(self):
        findings = [{"id": str(uuid.uuid4()), "severity": "critical", "title": "No dimension"}]
        result = SecurityEscalationService.check_escalation(findings, _approve())
        assert result.should_escalate is False

    def test_empty_dict_finding_skipped(self):
        result = SecurityEscalationService.check_escalation([{}], _approve())
        assert result.should_escalate is False

    def test_all_missing_field_findings_no_escalation(self):
        result = SecurityEscalationService.check_escalation(FINDINGS_WITH_MISSING_FIELDS, _approve())
        assert result.should_escalate is False

    def test_unknown_severity_does_not_hard_fail(self):
        result = SecurityEscalationService.check_escalation(FINDINGS_WITH_UNKNOWN_SEVERITY, _approve())
        # Should not raise; unknown severity is skipped
        assert isinstance(result, EscalationResult)

    def test_unknown_severity_no_escalation(self):
        result = SecurityEscalationService.check_escalation(FINDINGS_WITH_UNKNOWN_SEVERITY, _approve())
        assert result.should_escalate is False

    def test_finding_without_id_still_escalates(self):
        finding = {"severity": "critical", "dimension": "security", "title": "No ID"}
        result = SecurityEscalationService.check_escalation([finding], _approve())
        assert result.should_escalate is True
        assert result.escalation_reasons[0]["title"] == "No ID"

    def test_finding_without_title_uses_default(self):
        finding = {"id": str(uuid.uuid4()), "severity": "critical", "dimension": "security"}
        result = SecurityEscalationService.check_escalation([finding], _approve())
        assert result.escalation_reasons[0]["title"] == "Critical security finding"


# ===========================================================================
# Object-based findings (not dicts)
# ===========================================================================

class TestObjectFindings:
    def test_object_with_attributes_escalates(self):
        class MockFinding:
            id = str(uuid.uuid4())
            severity = "critical"
            dimension = "security"
            title = "Object-based critical finding"

        result = SecurityEscalationService.check_escalation([MockFinding()], _approve())
        assert result.should_escalate is True

    def test_object_high_security_no_escalation(self):
        class MockFinding:
            id = str(uuid.uuid4())
            severity = "high"
            dimension = "security"
            title = "Object-based high finding"

        result = SecurityEscalationService.check_escalation([MockFinding()], _approve())
        assert result.should_escalate is False


# ===========================================================================
# EscalationResult structural correctness
# ===========================================================================

class TestEscalationResultStructure:
    def test_result_is_frozen(self):
        result = SecurityEscalationService.check_escalation(EMPTY_FINDINGS, _approve())
        with pytest.raises((AttributeError, TypeError)):
            result.should_escalate = True  # type: ignore[misc]

    def test_no_escalation_empty_reasons(self):
        result = SecurityEscalationService.check_escalation(EMPTY_FINDINGS, _approve())
        assert result.escalation_reasons == []

    def test_escalation_reasons_are_dicts_with_finding_id_and_title(self):
        result = SecurityEscalationService.check_escalation(ONE_CRITICAL_SECURITY, _approve())
        for reason in result.escalation_reasons:
            assert "finding_id" in reason
            assert "title" in reason


# ===========================================================================
# SYSTEM_ACTOR_UUID constant
# ===========================================================================

class TestSystemActorUUID:
    def test_system_actor_uuid_is_valid_uuid(self):
        import uuid as uuid_module
        parsed = uuid_module.UUID(SYSTEM_ACTOR_UUID)
        assert str(parsed) == SYSTEM_ACTOR_UUID
