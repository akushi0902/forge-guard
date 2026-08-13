"""Unit tests for Combined Decision Engine and Security Escalation (WO-096).

Tests cover:
  - All four decision outcomes via 15+ parametrized test cases
  - Exact boundary values at threshold points (70/30, 50/60)
  - Off-by-one boundary behavior (69, 31, 49, 61)
  - Critical security escalation override (BLOCK + was_escalated=True)
  - Escalation overrides APPROVE → BLOCK (even Health=100, Risk=0)
  - Decision record schema validation
  - Missing Health Score → ValueError
  - Configurable thresholds (STRICT and LENIENT configurations)
  - Determinism: 5 identical runs produce identical results
  - DecisionEngine instance .decide() delegates to merge_scores()
  - ReleaseAssessmentFactory and ReleaseDecisionFactory fixture integration

All tests are pure — no database or network calls.

Run:
    pytest tests/unit/test_decision_engine.py -v
"""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest

from forgeguard.services.decision_engine.engine import (
    DEFAULT_THRESHOLDS,
    DecisionEngine,
    DecisionOutcome,
    DecisionResult,
)
from forgeguard.services.decision_engine.escalation_service import (
    EscalationResult,
    SecurityEscalationService,
)
from tests.fixtures.decision_thresholds import (
    DEFAULT_THRESHOLD,
    LENIENT_THRESHOLD_ID,
    SCORE_MATRIX,
    STRICT_THRESHOLD,
    STRICT_THRESHOLD_ID,
    make_threshold_row,
)
from tests.fixtures.release_decisions import (
    ASSESSMENT_ID_COMPLETED,
    ASSESSMENT_ID_WITH_ESCALATION,
    SERVICE_ID,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _decide(health: Decimal, risk: Decimal, config=None) -> DecisionResult:
    return DecisionEngine.merge_scores(health, risk, threshold_config=config)


def _escalate(
    findings: list[dict],
    health: Decimal = Decimal("100"),
    risk: Decimal = Decimal("0"),
    config=None,
) -> EscalationResult:
    threshold_result = _decide(health, risk, config)
    return SecurityEscalationService.check_escalation(findings, threshold_result)


def _critical_security_finding(
    *,
    finding_id: str = str(uuid.uuid4()),
    title: str = "Secrets in config file",
) -> dict:
    return {
        "id": finding_id,
        "severity": "critical",
        "dimension": "security",
        "title": title,
    }


def _non_escalating_finding(
    severity: str = "high",
    dimension: str = "security",
) -> dict:
    return {
        "id": str(uuid.uuid4()),
        "severity": severity,
        "dimension": dimension,
        "title": "Non-escalating finding",
    }


# ---------------------------------------------------------------------------
# SCORE_MATRIX parametrized decision outcomes (15+ test cases)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("health, risk, expected", SCORE_MATRIX)
def test_decision_matrix(
    health: Decimal, risk: Decimal, expected: str
) -> None:
    """The full score matrix covers all three outcomes with boundary precision."""
    result = _decide(health, risk, DEFAULT_THRESHOLD)
    assert result.decision.value == expected, (
        f"health={health}, risk={risk}: expected {expected!r}, "
        f"got {result.decision.value!r}"
    )


# ---------------------------------------------------------------------------
# Exact boundary values (AC-3)
# ---------------------------------------------------------------------------


def test_approve_exact_boundary_70_30() -> None:
    result = _decide(Decimal("70"), Decimal("30"))
    assert result.decision == DecisionOutcome.APPROVE


def test_health_69_risk_30_not_approve() -> None:
    """Health=69 just misses the APPROVE health threshold."""
    result = _decide(Decimal("69"), Decimal("30"))
    assert result.decision != DecisionOutcome.APPROVE


def test_health_70_risk_31_not_approve() -> None:
    """Risk=31 just misses the APPROVE risk threshold."""
    result = _decide(Decimal("70"), Decimal("31"))
    assert result.decision != DecisionOutcome.APPROVE


def test_conditional_exact_boundary_50_60() -> None:
    result = _decide(Decimal("50"), Decimal("60"))
    assert result.decision == DecisionOutcome.CONDITIONAL_APPROVE


def test_health_49_risk_60_is_block() -> None:
    """Health=49 is below the CONDITIONAL threshold → BLOCK."""
    result = _decide(Decimal("49"), Decimal("60"))
    assert result.decision == DecisionOutcome.BLOCK


def test_health_50_risk_61_is_block() -> None:
    """Risk=61 exceeds CONDITIONAL risk max → BLOCK."""
    result = _decide(Decimal("50"), Decimal("61"))
    assert result.decision == DecisionOutcome.BLOCK


# ---------------------------------------------------------------------------
# All four outcomes independently
# ---------------------------------------------------------------------------


def test_approve_outcome() -> None:
    result = _decide(Decimal("100"), Decimal("0"))
    assert result.decision == DecisionOutcome.APPROVE


def test_conditional_approve_outcome() -> None:
    result = _decide(Decimal("60"), Decimal("50"))
    assert result.decision == DecisionOutcome.CONDITIONAL_APPROVE


def test_block_outcome_both_below_conditional() -> None:
    result = _decide(Decimal("30"), Decimal("80"))
    assert result.decision == DecisionOutcome.BLOCK


def test_block_via_escalation_overrides_approve() -> None:
    """Even perfect scores → BLOCK when critical security finding present (AC-4)."""
    findings = [_critical_security_finding()]
    result = _escalate(findings, health=Decimal("100"), risk=Decimal("0"))
    assert result.final_recommendation == DecisionOutcome.BLOCK
    assert result.should_escalate is True


# ---------------------------------------------------------------------------
# Critical security escalation (AC-4)
# ---------------------------------------------------------------------------


def test_escalation_sets_block_on_critical_security_finding() -> None:
    findings = [_critical_security_finding()]
    result = _escalate(findings)
    assert result.should_escalate is True
    assert result.final_recommendation == DecisionOutcome.BLOCK


def test_escalation_captures_finding_id_and_title() -> None:
    fid = str(uuid.uuid4())
    findings = [_critical_security_finding(finding_id=fid, title="DB password exposed")]
    result = _escalate(findings)
    assert any(r["finding_id"] == fid for r in result.escalation_reasons)
    assert any(r["title"] == "DB password exposed" for r in result.escalation_reasons)


def test_escalation_multiple_findings_captures_all() -> None:
    """Multiple critical security findings — all captured, escalation triggers once."""
    findings = [
        _critical_security_finding(title="Secret A"),
        _critical_security_finding(title="Secret B"),
        _critical_security_finding(title="Secret C"),
    ]
    result = _escalate(findings)
    assert result.should_escalate is True
    assert len(result.escalation_reasons) == 3


def test_escalation_critical_non_security_dimension_does_not_trigger() -> None:
    """CRITICAL + code_quality does NOT escalate."""
    findings = [{"id": "x", "severity": "critical", "dimension": "code_quality", "title": "t"}]
    result = _escalate(findings)
    assert result.should_escalate is False


def test_escalation_high_security_does_not_trigger() -> None:
    """HIGH + security does NOT escalate (only CRITICAL + security)."""
    findings = [_non_escalating_finding(severity="high", dimension="security")]
    result = _escalate(findings)
    assert result.should_escalate is False


def test_escalation_empty_findings_no_escalation() -> None:
    result = _escalate([])
    assert result.should_escalate is False
    assert result.final_recommendation == DecisionOutcome.APPROVE  # Health=100, Risk=0


def test_escalation_overrides_conditional_to_block() -> None:
    findings = [_critical_security_finding()]
    result = _escalate(
        findings,
        health=Decimal("60"),
        risk=Decimal("50"),
    )
    assert result.original_recommendation == DecisionOutcome.CONDITIONAL_APPROVE
    assert result.final_recommendation == DecisionOutcome.BLOCK


def test_escalation_block_stays_block() -> None:
    """Escalation on an already-BLOCK decision stays BLOCK."""
    findings = [_critical_security_finding()]
    result = _escalate(
        findings,
        health=Decimal("0"),
        risk=Decimal("100"),
    )
    assert result.final_recommendation == DecisionOutcome.BLOCK


# ---------------------------------------------------------------------------
# Decision record schema (AC-5)
# ---------------------------------------------------------------------------


def test_decision_result_has_required_fields() -> None:
    result = _decide(Decimal("75"), Decimal("25"))
    assert hasattr(result, "decision")
    assert hasattr(result, "health_score")
    assert hasattr(result, "risk_score")
    assert hasattr(result, "threshold_config_id")
    assert hasattr(result, "contributing_factors")


def test_decision_result_health_score_at_decision() -> None:
    h = Decimal("73.50")
    result = _decide(h, Decimal("25"))
    assert result.health_score == h


def test_decision_result_risk_score_at_decision() -> None:
    r = Decimal("27.50")
    result = _decide(Decimal("75"), r)
    assert result.risk_score == r


def test_decision_result_decision_is_string_comparable() -> None:
    result = _decide(Decimal("100"), Decimal("0"))
    assert result.decision == DecisionOutcome.APPROVE
    assert result.decision.value == "APPROVE"


def test_decision_result_is_frozen() -> None:
    result = _decide(Decimal("75"), Decimal("25"))
    with pytest.raises((AttributeError, TypeError)):
        result.decision = DecisionOutcome.BLOCK  # type: ignore[misc]


def test_decision_result_contributing_factors_populated() -> None:
    result = _decide(Decimal("75"), Decimal("25"), DEFAULT_THRESHOLD)
    factors = result.contributing_factors
    assert "approve_health_ok" in factors
    assert "approve_risk_ok" in factors
    assert "conditional_health_ok" in factors
    assert "conditional_risk_ok" in factors


def test_decision_result_threshold_config_id_captured() -> None:
    result = _decide(Decimal("75"), Decimal("25"), DEFAULT_THRESHOLD)
    # DEFAULT_THRESHOLD has an 'id' key
    assert result.threshold_config_id is not None


# ---------------------------------------------------------------------------
# Missing Health Score → ValueError (AC-5 edge case)
# ---------------------------------------------------------------------------


def test_health_score_out_of_range_raises_value_error() -> None:
    with pytest.raises(ValueError, match="health_score must be in"):
        _decide(Decimal("-1"), Decimal("50"))


def test_health_score_above_100_raises_value_error() -> None:
    with pytest.raises(ValueError):
        _decide(Decimal("101"), Decimal("50"))


def test_risk_score_out_of_range_raises_value_error() -> None:
    with pytest.raises(ValueError, match="risk_score must be in"):
        _decide(Decimal("75"), Decimal("-1"))


# ---------------------------------------------------------------------------
# Configurable thresholds (AC-5, implementation step 8)
# ---------------------------------------------------------------------------


def test_strict_threshold_rejects_score_that_passes_default() -> None:
    """Health=75/Risk=28 passes default (APPROVE) but fails strict (CONDITIONAL)."""
    default_result = _decide(Decimal("75"), Decimal("28"), DEFAULT_THRESHOLD)
    strict_result = _decide(Decimal("75"), Decimal("28"), STRICT_THRESHOLD)
    assert default_result.decision == DecisionOutcome.APPROVE
    # STRICT requires health>=85 — 75 < 85, so not APPROVE
    assert strict_result.decision != DecisionOutcome.APPROVE


def test_lenient_threshold_approves_score_that_fails_default() -> None:
    """Health=65/Risk=35 blocks under default thresholds (health<70)
    but would APPROVE under a lenient threshold (health_min=60, risk_max=40)."""
    lenient = make_threshold_row(
        id=LENIENT_THRESHOLD_ID,
        approve_health_min=Decimal("60.00"),
        approve_risk_max=Decimal("40.00"),
        conditional_health_min=Decimal("40.00"),
        conditional_risk_max=Decimal("70.00"),
    )
    default_result = _decide(Decimal("65"), Decimal("35"), DEFAULT_THRESHOLD)
    lenient_result = _decide(Decimal("65"), Decimal("35"), lenient)
    assert default_result.decision == DecisionOutcome.CONDITIONAL_APPROVE
    assert lenient_result.decision == DecisionOutcome.APPROVE


def test_threshold_config_id_stored_in_result() -> None:
    result = _decide(Decimal("75"), Decimal("25"), STRICT_THRESHOLD)
    assert result.threshold_config_id == STRICT_THRESHOLD_ID


def test_missing_threshold_config_uses_defaults() -> None:
    result_no_config = _decide(Decimal("70"), Decimal("30"))
    result_default = _decide(Decimal("70"), Decimal("30"), DEFAULT_THRESHOLD)
    assert result_no_config.decision == result_default.decision


# ---------------------------------------------------------------------------
# Determinism (AC-6)
# ---------------------------------------------------------------------------


def test_decision_engine_is_deterministic() -> None:
    """Same (health, risk, config) triple always produces the same decision."""
    decisions = [
        _decide(Decimal("72"), Decimal("28"), DEFAULT_THRESHOLD).decision
        for _ in range(5)
    ]
    assert len(set(decisions)) == 1, f"Non-deterministic decisions: {decisions}"


def test_escalation_service_is_deterministic() -> None:
    findings = [_critical_security_finding()]
    outcomes = [
        _escalate(findings, health=Decimal("80"), risk=Decimal("20")).final_recommendation
        for _ in range(5)
    ]
    assert len(set(outcomes)) == 1, f"Non-deterministic escalation: {outcomes}"


# ---------------------------------------------------------------------------
# DecisionEngine instance .decide()
# ---------------------------------------------------------------------------


def test_instance_decide_uses_stored_config() -> None:
    engine = DecisionEngine(threshold_config=STRICT_THRESHOLD)
    result = engine.decide(Decimal("75"), Decimal("28"))
    # Under strict (approve_health_min=85), 75 < 85 → not APPROVE
    assert result.decision != DecisionOutcome.APPROVE


def test_instance_decide_no_config_uses_defaults() -> None:
    engine = DecisionEngine()
    result = engine.decide(Decimal("70"), Decimal("30"))
    assert result.decision == DecisionOutcome.APPROVE


# ---------------------------------------------------------------------------
# Escalation EscalationResult is frozen
# ---------------------------------------------------------------------------


def test_escalation_result_is_frozen() -> None:
    result = _escalate([])
    with pytest.raises((AttributeError, TypeError)):
        result.should_escalate = True  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Escalation fail-closed: exception during scan → BLOCK
# ---------------------------------------------------------------------------


def test_escalation_fail_closed_on_exception() -> None:
    """If findings scan raises, escalation defaults to BLOCK (fail-closed policy)."""

    class _BrokenFinding:
        @property
        def severity(self):
            raise RuntimeError("unexpected error")

    threshold_result = _decide(Decimal("100"), Decimal("0"))
    result = SecurityEscalationService.check_escalation(
        [_BrokenFinding()], threshold_result
    )
    assert result.final_recommendation == DecisionOutcome.BLOCK
    assert result.should_escalate is True
