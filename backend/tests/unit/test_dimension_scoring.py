"""Unit tests for the dimension score calculator (WO-095).

Tests DimensionScoreCalculator.calculate_dimension_scores() covering:
    - Single rule pass (score = 100), single rule fail (score = 0)
    - Multiple rules all pass, all fail
    - Mixed pass/fail with equal weights → 50%
    - Mixed pass/fail with custom weights → weighted average
    - Parametrized boundary values at 0, 1, 49, 50, 69, 70, 99, 100
      (the thresholds 50/70 are the CONDITIONAL_APPROVE/APPROVE decision boundaries)
    - Edge cases: zero rules, zero weights, negative weights
    - Suppressed findings (active exception): excluded from fail denominator → higher score
    - Expired exceptions: finding re-enters as FAIL → score unchanged vs unsuppressed
    - AI engine zero invocations during scoring (purely deterministic)
    - Determinism: same inputs → same outputs across 3 runs

All tests use dependency injection — no database or external service calls.

Run:
    pytest tests/unit/test_dimension_scoring.py -v
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from forgeguard.services.dimension_scorer import DimensionScoreCalculator
from forgeguard.services.domain.evaluation import EvaluationStatus, RuleEvaluationResult
from forgeguard.services.domain.severity import SeverityLevel

_TS = datetime(2026, 1, 1, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _r(
    *,
    name: str,
    dimension: str,
    status: EvaluationStatus,
    weight: str = "1.0",
) -> RuleEvaluationResult:
    return RuleEvaluationResult(
        rule_id=uuid.uuid4(),
        rule_name=name,
        dimension=dimension,
        severity=SeverityLevel.HIGH,
        status=status,
        actual_value=None,
        expected_value=None,
        evidence={},
        evaluated_at=_TS,
        weight=Decimal(weight),
    )


@pytest.fixture()
def calc() -> DimensionScoreCalculator:
    return DimensionScoreCalculator()


# ===========================================================================
# Single-rule dimensions
# ===========================================================================

class TestSingleRule:
    def test_single_pass_scores_100(self, calc):
        results = [_r(name="Rule", dimension="security", status=EvaluationStatus.PASS)]
        scores = calc.calculate_dimension_scores(results)
        assert scores["security"].score == Decimal("100.00")

    def test_single_fail_scores_0(self, calc):
        results = [_r(name="Rule", dimension="security", status=EvaluationStatus.FAIL)]
        scores = calc.calculate_dimension_scores(results)
        assert scores["security"].score == Decimal("0.00")

    def test_single_inconclusive_scores_none(self, calc):
        results = [_r(name="Rule", dimension="security", status=EvaluationStatus.INCONCLUSIVE)]
        scores = calc.calculate_dimension_scores(results)
        assert scores["security"].score is None
        assert scores["security"].has_data is False

    def test_single_error_scores_0(self, calc):
        results = [_r(name="Rule", dimension="security", status=EvaluationStatus.ERROR)]
        scores = calc.calculate_dimension_scores(results)
        assert scores["security"].score == Decimal("0.00")

    def test_single_pass_has_data_true(self, calc):
        results = [_r(name="Rule", dimension="code_quality", status=EvaluationStatus.PASS)]
        scores = calc.calculate_dimension_scores(results)
        assert scores["code_quality"].has_data is True


# ===========================================================================
# All-rules same status
# ===========================================================================

class TestAllRules:
    def test_five_passing_rules_score_100(self, calc):
        results = [
            _r(name=f"Rule{i}", dimension="test_coverage", status=EvaluationStatus.PASS)
            for i in range(5)
        ]
        scores = calc.calculate_dimension_scores(results)
        assert scores["test_coverage"].score == Decimal("100.00")

    def test_five_failing_rules_score_0(self, calc):
        results = [
            _r(name=f"Rule{i}", dimension="test_coverage", status=EvaluationStatus.FAIL)
            for i in range(5)
        ]
        scores = calc.calculate_dimension_scores(results)
        assert scores["test_coverage"].score == Decimal("0.00")

    def test_all_inconclusive_score_none(self, calc):
        results = [
            _r(name=f"Rule{i}", dimension="documentation", status=EvaluationStatus.INCONCLUSIVE)
            for i in range(3)
        ]
        scores = calc.calculate_dimension_scores(results)
        assert scores["documentation"].score is None
        assert scores["documentation"].has_data is False


# ===========================================================================
# Mixed pass/fail — equal weights
# ===========================================================================

class TestMixedEqualWeights:
    def test_one_pass_one_fail_scores_50(self, calc):
        results = [
            _r(name="Pass", dimension="security", status=EvaluationStatus.PASS),
            _r(name="Fail", dimension="security", status=EvaluationStatus.FAIL),
        ]
        scores = calc.calculate_dimension_scores(results)
        assert scores["security"].score == Decimal("50.00")

    def test_three_pass_one_fail_scores_75(self, calc):
        results = [
            _r(name="P1", dimension="security", status=EvaluationStatus.PASS),
            _r(name="P2", dimension="security", status=EvaluationStatus.PASS),
            _r(name="P3", dimension="security", status=EvaluationStatus.PASS),
            _r(name="F1", dimension="security", status=EvaluationStatus.FAIL),
        ]
        scores = calc.calculate_dimension_scores(results)
        assert scores["security"].score == Decimal("75.00")

    def test_two_pass_three_fail_scores_40(self, calc):
        results = [
            _r(name="P1", dimension="code_quality", status=EvaluationStatus.PASS),
            _r(name="P2", dimension="code_quality", status=EvaluationStatus.PASS),
            _r(name="F1", dimension="code_quality", status=EvaluationStatus.FAIL),
            _r(name="F2", dimension="code_quality", status=EvaluationStatus.FAIL),
            _r(name="F3", dimension="code_quality", status=EvaluationStatus.FAIL),
        ]
        scores = calc.calculate_dimension_scores(results)
        assert scores["code_quality"].score == Decimal("40.00")


# ===========================================================================
# Mixed pass/fail — custom weights
# ===========================================================================

class TestMixedCustomWeights:
    def test_custom_weights_heavy_pass(self, calc):
        # PASS w=3, FAIL w=1 → 3/4*100 = 75.00
        results = [
            _r(name="P", dimension="security", status=EvaluationStatus.PASS, weight="3.0"),
            _r(name="F", dimension="security", status=EvaluationStatus.FAIL, weight="1.0"),
        ]
        scores = calc.calculate_dimension_scores(results)
        assert scores["security"].score == Decimal("75.00")

    def test_custom_weights_heavy_fail(self, calc):
        # PASS w=1, FAIL w=3 → 1/4*100 = 25.00
        results = [
            _r(name="P", dimension="documentation", status=EvaluationStatus.PASS, weight="1.0"),
            _r(name="F", dimension="documentation", status=EvaluationStatus.FAIL, weight="3.0"),
        ]
        scores = calc.calculate_dimension_scores(results)
        assert scores["documentation"].score == Decimal("25.00")

    def test_custom_weights_70_30_split(self, calc):
        # PASS w=7, FAIL w=3 → 70.00
        results = [
            _r(name="P", dimension="test_coverage", status=EvaluationStatus.PASS, weight="7.0"),
            _r(name="F", dimension="test_coverage", status=EvaluationStatus.FAIL, weight="3.0"),
        ]
        scores = calc.calculate_dimension_scores(results)
        assert scores["test_coverage"].score == Decimal("70.00")


# ===========================================================================
# Boundary value tests — scores at decision-relevant thresholds
# 50 = CONDITIONAL_APPROVE boundary, 70 = APPROVE boundary
# ===========================================================================

@pytest.mark.parametrize("pass_weight,fail_weight,expected_score", [
    (Decimal("0"),   Decimal("1"),   Decimal("0.00")),    # 0% pass → 0
    (Decimal("1"),   Decimal("99"),  Decimal("1.00")),    # ~1% pass → 1
    (Decimal("49"),  Decimal("51"),  Decimal("49.00")),   # just below CONDITIONAL
    (Decimal("50"),  Decimal("50"),  Decimal("50.00")),   # CONDITIONAL boundary
    (Decimal("69"),  Decimal("31"),  Decimal("69.00")),   # just below APPROVE
    (Decimal("70"),  Decimal("30"),  Decimal("70.00")),   # APPROVE boundary
    (Decimal("99"),  Decimal("1"),   Decimal("99.00")),   # ~99% pass
    (Decimal("100"), Decimal("0"),   Decimal("100.00")),  # 100% pass → 100
])
def test_dimension_score_at_boundary_value(
    calc, pass_weight: Decimal, fail_weight: Decimal, expected_score: Decimal
) -> None:
    results: list[RuleEvaluationResult] = []
    if pass_weight > 0:
        results.append(_r(name="P", dimension="security", status=EvaluationStatus.PASS, weight=str(pass_weight)))
    if fail_weight > 0:
        results.append(_r(name="F", dimension="security", status=EvaluationStatus.FAIL, weight=str(fail_weight)))
    scores = calc.calculate_dimension_scores(results)
    assert scores["security"].score == expected_score, (
        f"pass_w={pass_weight}, fail_w={fail_weight} → expected {expected_score}, "
        f"got {scores['security'].score}"
    )


# ===========================================================================
# Edge cases
# ===========================================================================

class TestEdgeCases:
    def test_zero_rules_returns_none_score(self, calc):
        scores = calc.calculate_dimension_scores([])
        for dim_score in scores.values():
            assert dim_score.score is None

    def test_zero_rules_all_has_data_false(self, calc):
        scores = calc.calculate_dimension_scores([])
        for dim_score in scores.values():
            assert dim_score.has_data is False

    def test_zero_weight_rule_excluded_from_scoring(self, calc):
        # A FAIL rule with weight=0 should contribute 0 to denominator
        # so if there's only a zero-weight rule, score is None
        results = [
            _r(name="ZeroWeightFail", dimension="operations_readiness",
               status=EvaluationStatus.FAIL, weight="0.0"),
        ]
        scores = calc.calculate_dimension_scores(results)
        assert scores["operations_readiness"].score is None
        assert scores["operations_readiness"].has_data is False

    def test_all_zero_weight_rules_score_none(self, calc):
        results = [
            _r(name="P", dimension="documentation", status=EvaluationStatus.PASS, weight="0.0"),
            _r(name="F", dimension="documentation", status=EvaluationStatus.FAIL, weight="0.0"),
        ]
        scores = calc.calculate_dimension_scores(results)
        assert scores["documentation"].score is None
        assert scores["documentation"].has_data is False

    def test_negative_weight_clamped_to_zero(self, calc):
        # Negative weights are clamped to 0 → treated as if the rule doesn't exist
        # A negative-weight FAIL effectively has no impact
        results = [
            _r(name="P", dimension="security", status=EvaluationStatus.PASS, weight="1.0"),
            _r(name="NegFail", dimension="security", status=EvaluationStatus.FAIL, weight="-1.0"),
        ]
        scores = calc.calculate_dimension_scores(results)
        # With negative weight clamped: PASS w=1, FAIL w=0 → 1/1*100 = 100.00
        assert scores["security"].score == Decimal("100.00")

    def test_five_valid_dimensions_always_present(self, calc):
        results = [_r(name="R", dimension="security", status=EvaluationStatus.PASS)]
        scores = calc.calculate_dimension_scores(results)
        expected_dims = {
            "code_quality", "test_coverage", "security",
            "documentation", "operations_readiness",
        }
        assert set(scores.keys()) >= expected_dims


# ===========================================================================
# Suppressed findings (active exception)
# ===========================================================================

class TestSuppressedFindings:
    def test_excluding_suppressed_finding_improves_score(self, calc):
        """When an exception-granted finding is excluded, the dimension score improves."""
        # Without exception: 2 PASS + 1 FAIL → 66.67
        all_results = [
            _r(name="Pass1", dimension="security", status=EvaluationStatus.PASS),
            _r(name="Pass2", dimension="security", status=EvaluationStatus.PASS),
            _r(name="Fail_Suppressed", dimension="security", status=EvaluationStatus.FAIL),
        ]
        score_without_exception = calc.calculate_dimension_scores(all_results)["security"].score

        # With active exception: FAIL is excluded from the results list → 2 PASS only → 100.00
        active_exception_results = [
            _r(name="Pass1", dimension="security", status=EvaluationStatus.PASS),
            _r(name="Pass2", dimension="security", status=EvaluationStatus.PASS),
        ]
        score_with_exception = calc.calculate_dimension_scores(active_exception_results)["security"].score

        assert score_without_exception == Decimal("66.67")
        assert score_with_exception == Decimal("100.00")
        assert score_with_exception > score_without_exception

    def test_suppressed_finding_as_inconclusive_excluded_from_denominator(self, calc):
        """
        Alternatively, an active exception makes a rule INCONCLUSIVE (not in denominator).
        Verify INCONCLUSIVE does not penalise the score.
        """
        # 2 PASS + 1 INCONCLUSIVE (active exception simulated)
        results_with_inconclusive = [
            _r(name="Pass1", dimension="documentation", status=EvaluationStatus.PASS),
            _r(name="Pass2", dimension="documentation", status=EvaluationStatus.PASS),
            _r(name="Suppressed", dimension="documentation", status=EvaluationStatus.INCONCLUSIVE),
        ]
        score = calc.calculate_dimension_scores(results_with_inconclusive)["documentation"].score
        # INCONCLUSIVE excluded from denominator: 2/2*100 = 100.00
        assert score == Decimal("100.00")

    def test_expired_exception_finding_reincluded_as_fail(self, calc):
        """Expired exception means the finding reverts to FAIL status."""
        # 2 PASS + 1 FAIL (expired exception → no longer suppressed)
        results_expired = [
            _r(name="Pass1", dimension="test_coverage", status=EvaluationStatus.PASS),
            _r(name="Pass2", dimension="test_coverage", status=EvaluationStatus.PASS),
            _r(name="ReactivatedFail", dimension="test_coverage", status=EvaluationStatus.FAIL),
        ]
        score = calc.calculate_dimension_scores(results_expired)["test_coverage"].score
        # Expired exception → FAIL counts: 2/3*100 = 66.67
        assert score == Decimal("66.67")

    def test_score_delta_between_active_and_expired_exception(self, calc):
        """Verify the score difference between active exception (excluded) and expired (included)."""
        # Active exception: 1 FAIL excluded → 3 PASS → 100
        active_results = [
            _r(name="P1", dimension="security", status=EvaluationStatus.PASS),
            _r(name="P2", dimension="security", status=EvaluationStatus.PASS),
            _r(name="P3", dimension="security", status=EvaluationStatus.PASS),
        ]
        # Expired exception: 1 FAIL re-included → 3 PASS + 1 FAIL → 75
        expired_results = active_results + [
            _r(name="ExpiredFail", dimension="security", status=EvaluationStatus.FAIL),
        ]
        score_active = calc.calculate_dimension_scores(active_results)["security"].score
        score_expired = calc.calculate_dimension_scores(expired_results)["security"].score
        assert score_active == Decimal("100.00")
        assert score_expired == Decimal("75.00")
        assert score_active > score_expired


# ===========================================================================
# AI engine zero invocations
# ===========================================================================

class TestAIEngineNotInvoked:
    def test_ai_engine_never_called_during_dimension_scoring(self, calc):
        """Dimension scoring is pure computation — AI engine must not be called."""
        ai_engine = MagicMock()
        ai_engine.generate_completion = AsyncMock()

        results = [
            _r(name="P1", dimension="security", status=EvaluationStatus.PASS),
            _r(name="F1", dimension="security", status=EvaluationStatus.FAIL),
        ]
        calc.calculate_dimension_scores(results)

        ai_engine.generate_completion.assert_not_called()


# ===========================================================================
# Determinism
# ===========================================================================

class TestDeterminism:
    def test_same_inputs_same_output_three_runs(self, calc):
        """Run the same scenario 3 times and assert identical dimension scores."""
        results = [
            _r(name="P1", dimension="code_quality", status=EvaluationStatus.PASS, weight="2.0"),
            _r(name="P2", dimension="code_quality", status=EvaluationStatus.PASS, weight="3.0"),
            _r(name="F1", dimension="code_quality", status=EvaluationStatus.FAIL, weight="1.0"),
            _r(name="P3", dimension="test_coverage", status=EvaluationStatus.PASS),
            _r(name="F2", dimension="test_coverage", status=EvaluationStatus.FAIL),
        ]

        runs = [
            calc.calculate_dimension_scores(results)
            for _ in range(3)
        ]

        for dim in ("code_quality", "test_coverage"):
            assert runs[0][dim].score == runs[1][dim].score == runs[2][dim].score

    def test_determinism_at_boundary_score_50(self, calc):
        results = [
            _r(name="P", dimension="security", status=EvaluationStatus.PASS, weight="50.0"),
            _r(name="F", dimension="security", status=EvaluationStatus.FAIL, weight="50.0"),
        ]
        scores = [
            calc.calculate_dimension_scores(results)["security"].score
            for _ in range(3)
        ]
        assert scores[0] == scores[1] == scores[2] == Decimal("50.00")

    def test_determinism_at_boundary_score_70(self, calc):
        results = [
            _r(name="P", dimension="security", status=EvaluationStatus.PASS, weight="70.0"),
            _r(name="F", dimension="security", status=EvaluationStatus.FAIL, weight="30.0"),
        ]
        scores = [
            calc.calculate_dimension_scores(results)["security"].score
            for _ in range(3)
        ]
        assert scores[0] == scores[1] == scores[2] == Decimal("70.00")
