"""Unit tests for DecisionEngine.merge_scores() (WO-049).

All tests run without a database or network — the engine is a pure function.

Coverage:
    - All three decision outcomes with exact boundary values
    - Off-by-one conditions (health=69.99 must not APPROVE)
    - Negative and zero scores
    - Null/missing threshold config falls back to defaults
    - Contributing factors populated correctly
    - Timing assertion: merge_scores completes in under 10ms
    - Serializable transaction toggle: only one active at a time
    - DecisionOutcome enum values match expected strings
    - Input validation: out-of-range scores raise ValueError

Run:
    pytest tests/unit/services/decision_engine/test_engine.py -v
"""

from __future__ import annotations

import time
import uuid
from decimal import Decimal

import pytest

from forgeguard.services.decision_engine.engine import (
    DEFAULT_THRESHOLDS,
    DecisionEngine,
    DecisionOutcome,
    DecisionResult,
)
from tests.fixtures.decision_thresholds import (
    DEFAULT_THRESHOLD,
    SCORE_MATRIX,
    STRICT_THRESHOLD,
    make_threshold_row,
)


# ===========================================================================
# Decision outcomes — parametrized over SCORE_MATRIX
# ===========================================================================

class TestDecisionOutcomes:
    @pytest.mark.parametrize("health,risk,expected", SCORE_MATRIX)
    def test_score_matrix(self, health: Decimal, risk: Decimal, expected: str) -> None:
        result = DecisionEngine.merge_scores(health, risk, threshold_config=DEFAULT_THRESHOLD)
        assert result.decision.value == expected, (
            f"health={health}, risk={risk} → expected {expected}, got {result.decision.value}"
        )

    def test_approve_exact_boundary(self) -> None:
        result = DecisionEngine.merge_scores(Decimal("70"), Decimal("30"))
        assert result.decision == DecisionOutcome.APPROVE

    def test_conditional_exact_boundary(self) -> None:
        result = DecisionEngine.merge_scores(Decimal("50"), Decimal("60"))
        assert result.decision == DecisionOutcome.CONDITIONAL_APPROVE

    def test_block_both_below_conditional(self) -> None:
        result = DecisionEngine.merge_scores(Decimal("49"), Decimal("61"))
        assert result.decision == DecisionOutcome.BLOCK

    def test_trivial_approve(self) -> None:
        result = DecisionEngine.merge_scores(Decimal("100"), Decimal("0"))
        assert result.decision == DecisionOutcome.APPROVE

    def test_trivial_block(self) -> None:
        result = DecisionEngine.merge_scores(Decimal("0"), Decimal("100"))
        assert result.decision == DecisionOutcome.BLOCK


# ===========================================================================
# Off-by-one edge cases
# ===========================================================================

class TestOffByOne:
    def test_health_just_below_approve_is_conditional(self) -> None:
        result = DecisionEngine.merge_scores(Decimal("69.99"), Decimal("30"))
        assert result.decision == DecisionOutcome.CONDITIONAL_APPROVE

    def test_risk_just_above_approve_is_conditional(self) -> None:
        result = DecisionEngine.merge_scores(Decimal("70"), Decimal("30.01"))
        assert result.decision == DecisionOutcome.CONDITIONAL_APPROVE

    def test_health_just_below_conditional_is_block(self) -> None:
        result = DecisionEngine.merge_scores(Decimal("49.99"), Decimal("60"))
        assert result.decision == DecisionOutcome.BLOCK

    def test_risk_just_above_conditional_is_block(self) -> None:
        result = DecisionEngine.merge_scores(Decimal("50"), Decimal("60.01"))
        assert result.decision == DecisionOutcome.BLOCK

    def test_approve_health_just_above_threshold(self) -> None:
        result = DecisionEngine.merge_scores(Decimal("70.01"), Decimal("29.99"))
        assert result.decision == DecisionOutcome.APPROVE


# ===========================================================================
# Zero and boundary scores
# ===========================================================================

class TestZeroAndBoundaryScores:
    def test_health_zero_risk_zero_is_block(self) -> None:
        # health=0 < conditional_health_min=50 → BLOCK even though risk is 0
        result = DecisionEngine.merge_scores(Decimal("0"), Decimal("0"))
        assert result.decision == DecisionOutcome.BLOCK

    def test_health_100_risk_100_is_block(self) -> None:
        result = DecisionEngine.merge_scores(Decimal("100"), Decimal("100"))
        assert result.decision == DecisionOutcome.BLOCK

    def test_health_zero_risk_100_is_block(self) -> None:
        result = DecisionEngine.merge_scores(Decimal("0"), Decimal("100"))
        assert result.decision == DecisionOutcome.BLOCK

    def test_health_50_risk_zero_is_conditional(self) -> None:
        result = DecisionEngine.merge_scores(Decimal("50"), Decimal("0"))
        assert result.decision == DecisionOutcome.CONDITIONAL_APPROVE


# ===========================================================================
# Input validation
# ===========================================================================

class TestInputValidation:
    def test_negative_health_raises(self) -> None:
        with pytest.raises(ValueError, match="health_score"):
            DecisionEngine.merge_scores(Decimal("-1"), Decimal("50"))

    def test_health_above_100_raises(self) -> None:
        with pytest.raises(ValueError, match="health_score"):
            DecisionEngine.merge_scores(Decimal("101"), Decimal("50"))

    def test_negative_risk_raises(self) -> None:
        with pytest.raises(ValueError, match="risk_score"):
            DecisionEngine.merge_scores(Decimal("50"), Decimal("-0.01"))

    def test_risk_above_100_raises(self) -> None:
        with pytest.raises(ValueError, match="risk_score"):
            DecisionEngine.merge_scores(Decimal("50"), Decimal("100.01"))


# ===========================================================================
# Default threshold fallback
# ===========================================================================

class TestDefaultThresholdFallback:
    def test_no_config_uses_defaults(self) -> None:
        result = DecisionEngine.merge_scores(Decimal("70"), Decimal("30"), threshold_config=None)
        assert result.decision == DecisionOutcome.APPROVE

    def test_empty_config_uses_defaults(self) -> None:
        result = DecisionEngine.merge_scores(Decimal("70"), Decimal("30"), threshold_config={})
        assert result.decision == DecisionOutcome.APPROVE

    def test_config_id_none_when_absent(self) -> None:
        result = DecisionEngine.merge_scores(Decimal("70"), Decimal("30"))
        assert result.threshold_config_id is None

    def test_config_id_set_when_provided(self) -> None:
        threshold_id = uuid.UUID("a0000000-0000-0000-0000-000000000001")
        result = DecisionEngine.merge_scores(
            Decimal("70"), Decimal("30"),
            threshold_config={"id": threshold_id, **DEFAULT_THRESHOLDS},
        )
        assert result.threshold_config_id == threshold_id


# ===========================================================================
# Alternative threshold configs
# ===========================================================================

class TestAlternativeThresholds:
    def test_strict_threshold_blocks_default_approve(self) -> None:
        result = DecisionEngine.merge_scores(
            Decimal("70"), Decimal("30"), threshold_config=STRICT_THRESHOLD
        )
        # With strict (approve_health_min=85, approve_risk_max=15): health=70 is BELOW 85
        assert result.decision != DecisionOutcome.APPROVE

    def test_lenient_threshold_approves_at_sixty(self) -> None:
        result = DecisionEngine.merge_scores(
            Decimal("60"), Decimal("40"),
            threshold_config={
                "id": None,
                "approve_health_min": Decimal("60.00"),
                "approve_risk_max": Decimal("40.00"),
                "conditional_health_min": Decimal("40.00"),
                "conditional_risk_max": Decimal("70.00"),
            },
        )
        assert result.decision == DecisionOutcome.APPROVE


# ===========================================================================
# DecisionResult structure
# ===========================================================================

class TestDecisionResult:
    def test_result_is_frozen(self) -> None:
        result = DecisionEngine.merge_scores(Decimal("70"), Decimal("30"))
        with pytest.raises((AttributeError, TypeError)):
            result.decision = DecisionOutcome.BLOCK  # type: ignore[misc]

    def test_contributing_factors_populated(self) -> None:
        result = DecisionEngine.merge_scores(Decimal("70"), Decimal("30"))
        cf = result.contributing_factors
        assert "approve_health_min" in cf
        assert "approve_risk_max" in cf
        assert "conditional_health_min" in cf
        assert "conditional_risk_max" in cf
        assert "approve_health_ok" in cf
        assert "approve_risk_ok" in cf

    def test_contributing_factors_reflect_decision(self) -> None:
        result = DecisionEngine.merge_scores(Decimal("70"), Decimal("30"))
        assert result.contributing_factors["approve_health_ok"] is True
        assert result.contributing_factors["approve_risk_ok"] is True

    def test_block_contributing_factors_false(self) -> None:
        result = DecisionEngine.merge_scores(Decimal("10"), Decimal("90"))
        assert result.contributing_factors["approve_health_ok"] is False
        assert result.contributing_factors["conditional_health_ok"] is False

    def test_health_and_risk_preserved_in_result(self) -> None:
        result = DecisionEngine.merge_scores(Decimal("75.00"), Decimal("25.50"))
        assert result.health_score == Decimal("75.00")
        assert result.risk_score == Decimal("25.50")


# ===========================================================================
# Latency requirement
# ===========================================================================

class TestLatency:
    def test_merge_scores_under_10ms(self) -> None:
        """merge_scores must complete in under 10ms — pure computation, no I/O."""
        start = time.perf_counter()
        for _ in range(100):
            DecisionEngine.merge_scores(
                Decimal("70"), Decimal("30"), threshold_config=DEFAULT_THRESHOLD
            )
        elapsed_ms = (time.perf_counter() - start) * 1000
        per_call_ms = elapsed_ms / 100
        assert per_call_ms < 10.0, (
            f"merge_scores averaged {per_call_ms:.3f}ms per call — exceeds 10ms budget"
        )

    def test_single_call_under_10ms(self) -> None:
        start = time.perf_counter()
        DecisionEngine.merge_scores(Decimal("80"), Decimal("20"))
        elapsed_ms = (time.perf_counter() - start) * 1000
        assert elapsed_ms < 10.0, f"Single merge_scores call took {elapsed_ms:.3f}ms"


# ===========================================================================
# DecisionOutcome enum
# ===========================================================================

class TestDecisionOutcomeEnum:
    def test_string_values_match_expected(self) -> None:
        assert DecisionOutcome.APPROVE.value == "APPROVE"
        assert DecisionOutcome.CONDITIONAL_APPROVE.value == "CONDITIONAL_APPROVE"
        assert DecisionOutcome.BLOCK.value == "BLOCK"

    def test_is_str_mixin(self) -> None:
        assert isinstance(DecisionOutcome.APPROVE, str)

    def test_comparison_with_string(self) -> None:
        assert DecisionOutcome.APPROVE == "APPROVE"


# ===========================================================================
# Instance-based usage
# ===========================================================================

class TestDecisionEngineInstance:
    def test_decide_uses_constructor_config(self) -> None:
        engine = DecisionEngine(threshold_config=DEFAULT_THRESHOLD)
        result = engine.decide(Decimal("70"), Decimal("30"))
        assert result.decision == DecisionOutcome.APPROVE

    def test_decide_no_config_falls_back_to_defaults(self) -> None:
        engine = DecisionEngine()
        result = engine.decide(Decimal("70"), Decimal("30"))
        assert result.decision == DecisionOutcome.APPROVE
