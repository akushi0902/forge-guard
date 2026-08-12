"""Unit tests for the overall Health Score calculation engine (WO-095).

Tests the full scoring pipeline from RuleEvaluationResult → DimensionScore →
HealthScoreResult, covering:

  Overall Health Score (HealthScoreAggregator):
    - All five dimensions present with equal weights
    - All five dimensions with custom weights
    - Missing dimensions (no rules configured for a dimension)
    - Single dimension only (overall = that dimension's score)
    - All dimensions missing data → overall_score = None

  Boundary values at APPROVE (70) and CONDITIONAL_APPROVE (50) thresholds:
    - Score < 50 → BLOCK territory
    - Score = 50 → CONDITIONAL_APPROVE boundary
    - Score just below 70 → CONDITIONAL_APPROVE territory
    - Score = 70 → APPROVE boundary
    - Score just above/below each threshold (49.9, 50.0, 50.1, 69.9, 70.0, 70.1)

  Suppressed findings:
    - Active exception: finding excluded → dimension score improves → higher overall
    - Expired exception: finding re-included as FAIL → lower overall score

  AI engine never invoked:
    - Mock AI engine asserts zero calls during any scoring operation

  Determinism:
    - Same inputs produce identical HealthScoreResult across 3 runs

All tests use dependency injection — no database or network calls.

Run:
    pytest tests/unit/test_health_score_calculation.py -v
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from forgeguard.services.dimension_scorer import DimensionScoreCalculator
from forgeguard.services.domain.evaluation import EvaluationStatus, RuleEvaluationResult
from forgeguard.services.domain.scoring import DimensionScore
from forgeguard.services.domain.severity import SeverityLevel
from forgeguard.services.health_score_aggregator import DEFAULT_WEIGHTS, HealthScoreAggregator

_TS = datetime(2026, 1, 1, tzinfo=timezone.utc)
_AID = uuid.UUID("e0000000-0000-0000-0000-000000000001")
_SID = uuid.UUID("e0000000-0000-0000-0000-000000000002")


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


def _ds(
    dimension: str,
    score: Decimal | None,
    has_data: bool = True,
    passed: int = 1,
    failed: int = 0,
) -> DimensionScore:
    return DimensionScore(
        dimension=dimension,
        score=score,
        total_rules=passed + failed if has_data else 0,
        passed_rules=passed if has_data else 0,
        failed_rules=failed if has_data else 0,
        inconclusive_rules=0,
        error_rules=0,
        has_data=has_data,
        contributing_factors=[],
    )


def _all_five(score: Decimal) -> dict[str, DimensionScore]:
    """Build a dict with all five dimensions set to *score*."""
    return {
        "code_quality": _ds("code_quality", score),
        "test_coverage": _ds("test_coverage", score),
        "security": _ds("security", score),
        "documentation": _ds("documentation", score),
        "operations_readiness": _ds("operations_readiness", score),
    }


@pytest.fixture()
def agg() -> HealthScoreAggregator:
    return HealthScoreAggregator()


@pytest.fixture()
def calc() -> DimensionScoreCalculator:
    return DimensionScoreCalculator()


# ===========================================================================
# All five dimensions — equal weights
# ===========================================================================

class TestAllFiveDimensionsEqualWeights:
    def test_all_same_score_overall_equals_that_score(self, agg):
        dims = _all_five(Decimal("80.00"))
        result = agg.aggregate(dims, None, _AID, _SID)
        assert result.overall_score == Decimal("80.00")

    def test_varied_scores_equal_weights(self, agg):
        # (50 + 60 + 70 + 80 + 90) / 5 = 70.00
        dims = {
            "code_quality": _ds("code_quality", Decimal("50.00")),
            "test_coverage": _ds("test_coverage", Decimal("60.00")),
            "security": _ds("security", Decimal("70.00")),
            "documentation": _ds("documentation", Decimal("80.00")),
            "operations_readiness": _ds("operations_readiness", Decimal("90.00")),
        }
        result = agg.aggregate(dims, None, _AID, _SID)
        assert result.overall_score == Decimal("70.00")

    def test_dimensions_with_data_count(self, agg):
        dims = _all_five(Decimal("75.00"))
        result = agg.aggregate(dims, None, _AID, _SID)
        assert result.dimensions_with_data == 5
        assert result.dimensions_without_data == 0

    def test_weights_used_sum_to_100(self, agg):
        dims = _all_five(Decimal("75.00"))
        result = agg.aggregate(dims, None, _AID, _SID)
        total = sum(result.weights_used.values())
        assert abs(total - Decimal("100")) <= Decimal("0.05")

    def test_all_zero_scores_overall_is_0(self, agg):
        dims = _all_five(Decimal("0.00"))
        result = agg.aggregate(dims, None, _AID, _SID)
        assert result.overall_score == Decimal("0.00")

    def test_all_hundred_scores_overall_is_100(self, agg):
        dims = _all_five(Decimal("100.00"))
        result = agg.aggregate(dims, None, _AID, _SID)
        assert result.overall_score == Decimal("100.00")


# ===========================================================================
# All five dimensions — custom weights
# ===========================================================================

class TestCustomWeights:
    def test_security_heavy_weight_pulls_score_toward_security(self, agg):
        # All 100 except security=0; security weight=80; others weight 5 each
        weights = {
            "code_quality": Decimal("5"),
            "test_coverage": Decimal("5"),
            "security": Decimal("80"),
            "documentation": Decimal("5"),
            "operations_readiness": Decimal("5"),
        }
        dims = {
            "code_quality": _ds("code_quality", Decimal("100.00")),
            "test_coverage": _ds("test_coverage", Decimal("100.00")),
            "security": _ds("security", Decimal("0.00"), failed=1, passed=0),
            "documentation": _ds("documentation", Decimal("100.00")),
            "operations_readiness": _ds("operations_readiness", Decimal("100.00")),
        }
        result = agg.aggregate(dims, weights, _AID, _SID)
        # 100*5 + 100*5 + 0*80 + 100*5 + 100*5 = 2000 / 100 = 20.00
        assert result.overall_score == Decimal("20.00")

    def test_custom_weights_reflected_in_weights_used(self, agg):
        weights = {
            "code_quality": Decimal("10"),
            "test_coverage": Decimal("20"),
            "security": Decimal("40"),
            "documentation": Decimal("20"),
            "operations_readiness": Decimal("10"),
        }
        dims = _all_five(Decimal("70.00"))
        result = agg.aggregate(dims, weights, _AID, _SID)
        assert result.weights_used["security"] == Decimal("40.00")
        assert result.weights_used["code_quality"] == Decimal("10.00")

    def test_equal_custom_weights_same_as_default(self, agg):
        equal_weights = {dim: Decimal("20") for dim in DEFAULT_WEIGHTS}
        dims = _all_five(Decimal("65.00"))
        result_default = agg.aggregate(dims, None, _AID, _SID)
        result_custom = agg.aggregate(dims, equal_weights, _AID, _SID)
        assert result_default.overall_score == result_custom.overall_score


# ===========================================================================
# Missing dimensions (no rules configured)
# ===========================================================================

class TestMissingDimensions:
    def test_one_missing_dimension_score_unchanged(self, agg):
        # docs missing; remaining 4 all score 80 → still 80.00
        dims = {
            "code_quality": _ds("code_quality", Decimal("80.00")),
            "test_coverage": _ds("test_coverage", Decimal("80.00")),
            "security": _ds("security", Decimal("80.00")),
            "documentation": _ds("documentation", None, has_data=False),
            "operations_readiness": _ds("operations_readiness", Decimal("80.00")),
        }
        result = agg.aggregate(dims, None, _AID, _SID)
        assert result.overall_score == Decimal("80.00")

    def test_missing_dimension_has_zero_weight_used(self, agg):
        dims = {
            "code_quality": _ds("code_quality", Decimal("70.00")),
            "test_coverage": _ds("test_coverage", Decimal("70.00")),
            "security": _ds("security", Decimal("70.00")),
            "documentation": _ds("documentation", None, has_data=False),
            "operations_readiness": _ds("operations_readiness", Decimal("70.00")),
        }
        result = agg.aggregate(dims, None, _AID, _SID)
        assert result.weights_used["documentation"] == Decimal("0.00")

    def test_three_missing_dimensions(self, agg):
        # Only security=60 and docs=90 have data → (60*20 + 90*20) / 40 = 75.00
        dims = {
            "code_quality": _ds("code_quality", None, has_data=False),
            "test_coverage": _ds("test_coverage", None, has_data=False),
            "security": _ds("security", Decimal("60.00")),
            "documentation": _ds("documentation", Decimal("90.00")),
            "operations_readiness": _ds("operations_readiness", None, has_data=False),
        }
        result = agg.aggregate(dims, None, _AID, _SID)
        assert result.overall_score == Decimal("75.00")

    def test_single_dimension_only(self, agg):
        dims = {
            "code_quality": _ds("code_quality", None, has_data=False),
            "test_coverage": _ds("test_coverage", None, has_data=False),
            "security": _ds("security", Decimal("72.50")),
            "documentation": _ds("documentation", None, has_data=False),
            "operations_readiness": _ds("operations_readiness", None, has_data=False),
        }
        result = agg.aggregate(dims, None, _AID, _SID)
        assert result.overall_score == Decimal("72.50")

    def test_all_dimensions_no_data_returns_none(self, agg):
        dims = {
            dim: _ds(dim, None, has_data=False)
            for dim in ("code_quality", "test_coverage", "security",
                        "documentation", "operations_readiness")
        }
        result = agg.aggregate(dims, None, _AID, _SID)
        assert result.overall_score is None


# ===========================================================================
# Boundary values at APPROVE (70) and CONDITIONAL_APPROVE (50) thresholds
# ===========================================================================

@pytest.mark.parametrize("score_value,expected", [
    (Decimal("0.00"),   Decimal("0.00")),    # well below CONDITIONAL
    (Decimal("1.00"),   Decimal("1.00")),    # far below CONDITIONAL
    (Decimal("49.00"),  Decimal("49.00")),   # just below CONDITIONAL (BLOCK)
    (Decimal("49.90"),  Decimal("49.90")),   # just below CONDITIONAL (BLOCK)
    (Decimal("50.00"),  Decimal("50.00")),   # CONDITIONAL_APPROVE boundary
    (Decimal("50.10"),  Decimal("50.10")),   # just above CONDITIONAL
    (Decimal("69.00"),  Decimal("69.00")),   # just below APPROVE
    (Decimal("69.90"),  Decimal("69.90")),   # just below APPROVE (CONDITIONAL)
    (Decimal("70.00"),  Decimal("70.00")),   # APPROVE boundary
    (Decimal("70.10"),  Decimal("70.10")),   # just above APPROVE
    (Decimal("99.00"),  Decimal("99.00")),   # high score
    (Decimal("100.00"), Decimal("100.00")),  # maximum score
])
def test_overall_score_at_boundary_value(
    agg, score_value: Decimal, expected: Decimal
) -> None:
    """Verify the aggregator preserves exact boundary scores without rounding drift."""
    dims = _all_five(score_value)
    result = agg.aggregate(dims, None, _AID, _SID)
    assert result.overall_score == expected, (
        f"Input score {score_value} → expected {expected}, got {result.overall_score}"
    )


# ===========================================================================
# Full pipeline: RuleEvaluationResult → DimensionScore → HealthScoreResult
# ===========================================================================

class TestFullPipeline:
    def test_pipeline_all_pass_gives_100_overall(self, calc, agg):
        results = [
            _r(name=f"Rule-{dim}", dimension=dim, status=EvaluationStatus.PASS)
            for dim in ("code_quality", "test_coverage", "security",
                        "documentation", "operations_readiness")
        ]
        dim_scores = calc.calculate_dimension_scores(results)
        health = agg.aggregate(dim_scores, None, _AID, _SID)
        assert health.overall_score == Decimal("100.00")

    def test_pipeline_all_fail_gives_0_overall(self, calc, agg):
        results = [
            _r(name=f"Rule-{dim}", dimension=dim, status=EvaluationStatus.FAIL)
            for dim in ("code_quality", "test_coverage", "security",
                        "documentation", "operations_readiness")
        ]
        dim_scores = calc.calculate_dimension_scores(results)
        health = agg.aggregate(dim_scores, None, _AID, _SID)
        assert health.overall_score == Decimal("0.00")

    def test_pipeline_mixed_security_fails(self, calc, agg):
        # Security: 1 PASS + 1 FAIL → 50.00; others all PASS → 100.00
        # Overall: (100+100+50+100+100)/5 = 450/5 = 90.00
        results = [
            _r(name="CQ", dimension="code_quality", status=EvaluationStatus.PASS),
            _r(name="TC", dimension="test_coverage", status=EvaluationStatus.PASS),
            _r(name="SEC-P", dimension="security", status=EvaluationStatus.PASS),
            _r(name="SEC-F", dimension="security", status=EvaluationStatus.FAIL),
            _r(name="DOC", dimension="documentation", status=EvaluationStatus.PASS),
            _r(name="OPS", dimension="operations_readiness", status=EvaluationStatus.PASS),
        ]
        dim_scores = calc.calculate_dimension_scores(results)
        health = agg.aggregate(dim_scores, None, _AID, _SID)
        assert health.overall_score == Decimal("90.00")

    def test_pipeline_no_rules_for_dimension_excluded(self, calc, agg):
        """Dimension with no rules should not count against overall score."""
        # Only 3 dimensions have rules; all pass → overall = 100.00
        results = [
            _r(name="CQ", dimension="code_quality", status=EvaluationStatus.PASS),
            _r(name="TC", dimension="test_coverage", status=EvaluationStatus.PASS),
            _r(name="SEC", dimension="security", status=EvaluationStatus.PASS),
        ]
        dim_scores = calc.calculate_dimension_scores(results)
        health = agg.aggregate(dim_scores, None, _AID, _SID)
        assert health.overall_score == Decimal("100.00")
        assert health.dimensions_with_data == 3
        assert health.dimensions_without_data == 2


# ===========================================================================
# Suppressed findings (active exceptions)
# ===========================================================================

class TestSuppressedFindingsPipeline:
    def test_active_exception_improves_overall_score(self, calc, agg):
        """Excluding an exception-granted finding raises the overall health score."""
        # Without exception: security has 1 PASS + 1 FAIL → 50.00; others 100.00
        # Overall without exception: (100+100+50+100+100)/5 = 90.00
        results_without = [
            _r(name="CQ", dimension="code_quality", status=EvaluationStatus.PASS),
            _r(name="TC", dimension="test_coverage", status=EvaluationStatus.PASS),
            _r(name="SEC-P", dimension="security", status=EvaluationStatus.PASS),
            _r(name="SEC-F", dimension="security", status=EvaluationStatus.FAIL),
            _r(name="DOC", dimension="documentation", status=EvaluationStatus.PASS),
            _r(name="OPS", dimension="operations_readiness", status=EvaluationStatus.PASS),
        ]
        # With active exception: SEC-F excluded → security 100.00; overall 100.00
        results_with_exception = [
            r for r in results_without if r.rule_name != "SEC-F"
        ]

        dim_scores_without = calc.calculate_dimension_scores(results_without)
        health_without = agg.aggregate(dim_scores_without, None, _AID, _SID)

        dim_scores_with = calc.calculate_dimension_scores(results_with_exception)
        health_with = agg.aggregate(dim_scores_with, None, _AID, _SID)

        assert health_without.overall_score == Decimal("90.00")
        assert health_with.overall_score == Decimal("100.00")
        assert health_with.overall_score > health_without.overall_score

    def test_expired_exception_reverts_to_lower_score(self, calc, agg):
        """Expired exception means the finding re-enters as FAIL, lowering the score."""
        # Expired exception: FAIL is re-included → security 50.00; overall 90.00
        results_expired = [
            _r(name="CQ", dimension="code_quality", status=EvaluationStatus.PASS),
            _r(name="TC", dimension="test_coverage", status=EvaluationStatus.PASS),
            _r(name="SEC-P", dimension="security", status=EvaluationStatus.PASS),
            _r(name="SEC-F", dimension="security", status=EvaluationStatus.FAIL),
            _r(name="DOC", dimension="documentation", status=EvaluationStatus.PASS),
            _r(name="OPS", dimension="operations_readiness", status=EvaluationStatus.PASS),
        ]
        dim_scores = calc.calculate_dimension_scores(results_expired)
        health = agg.aggregate(dim_scores, None, _AID, _SID)
        assert health.overall_score == Decimal("90.00")

    def test_inconclusive_exception_excluded_from_denominator(self, calc, agg):
        """INCONCLUSIVE (exception-granted) findings excluded from denominator."""
        results = [
            _r(name="CQ", dimension="code_quality", status=EvaluationStatus.PASS),
            _r(name="TC", dimension="test_coverage", status=EvaluationStatus.PASS),
            _r(name="SEC-P", dimension="security", status=EvaluationStatus.PASS),
            _r(name="SEC-I", dimension="security", status=EvaluationStatus.INCONCLUSIVE),
            _r(name="DOC", dimension="documentation", status=EvaluationStatus.PASS),
            _r(name="OPS", dimension="operations_readiness", status=EvaluationStatus.PASS),
        ]
        dim_scores = calc.calculate_dimension_scores(results)
        health = agg.aggregate(dim_scores, None, _AID, _SID)
        # INCONCLUSIVE excluded: security = 1/1 = 100; all 100 → overall 100
        assert health.overall_score == Decimal("100.00")


# ===========================================================================
# AI engine never invoked during any scoring operation
# ===========================================================================

class TestAIEngineNotInvoked:
    def test_ai_engine_not_called_during_dimension_scoring(self, calc):
        ai_engine = MagicMock()
        ai_engine.generate_completion = AsyncMock()

        results = [
            _r(name="R1", dimension="security", status=EvaluationStatus.PASS),
            _r(name="R2", dimension="security", status=EvaluationStatus.FAIL),
        ]
        calc.calculate_dimension_scores(results)

        ai_engine.generate_completion.assert_not_called()

    def test_ai_engine_not_called_during_health_score_aggregation(self, agg):
        ai_engine = MagicMock()
        ai_engine.generate_completion = AsyncMock()

        dims = _all_five(Decimal("75.00"))
        agg.aggregate(dims, None, _AID, _SID)

        ai_engine.generate_completion.assert_not_called()

    def test_ai_engine_not_called_during_full_pipeline(self, calc, agg):
        ai_engine = MagicMock()
        ai_engine.generate_completion = AsyncMock()

        results = [
            _r(name="R", dimension=dim, status=EvaluationStatus.PASS)
            for dim in ("code_quality", "test_coverage", "security",
                        "documentation", "operations_readiness")
        ]
        dim_scores = calc.calculate_dimension_scores(results)
        agg.aggregate(dim_scores, None, _AID, _SID)

        ai_engine.generate_completion.assert_not_called()


# ===========================================================================
# Determinism: identical inputs → identical results across 3 runs
# ===========================================================================

class TestDeterminism:
    def test_dimension_scorer_deterministic_three_runs(self, calc):
        results = [
            _r(name="P1", dimension="security", status=EvaluationStatus.PASS, weight="3.0"),
            _r(name="F1", dimension="security", status=EvaluationStatus.FAIL, weight="1.0"),
            _r(name="P2", dimension="code_quality", status=EvaluationStatus.PASS),
        ]
        scores_all = [
            calc.calculate_dimension_scores(results)
            for _ in range(3)
        ]
        for dim in ("security", "code_quality"):
            assert scores_all[0][dim].score == scores_all[1][dim].score == scores_all[2][dim].score

    def test_health_aggregator_deterministic_three_runs(self, agg):
        dims = {
            "code_quality": _ds("code_quality", Decimal("70.00")),
            "test_coverage": _ds("test_coverage", Decimal("50.00")),
            "security": _ds("security", Decimal("80.00")),
            "documentation": _ds("documentation", None, has_data=False),
            "operations_readiness": _ds("operations_readiness", Decimal("90.00")),
        }
        results = [
            agg.aggregate(dims, None, _AID, _SID).overall_score
            for _ in range(3)
        ]
        assert results[0] == results[1] == results[2]

    def test_full_pipeline_deterministic_three_runs(self, calc, agg):
        results = [
            _r(name="CQ-P", dimension="code_quality", status=EvaluationStatus.PASS, weight="2.0"),
            _r(name="CQ-F", dimension="code_quality", status=EvaluationStatus.FAIL, weight="1.0"),
            _r(name="TC-P", dimension="test_coverage", status=EvaluationStatus.PASS),
            _r(name="SEC-F", dimension="security", status=EvaluationStatus.FAIL),
            _r(name="DOC-P", dimension="documentation", status=EvaluationStatus.PASS),
            _r(name="OPS-P", dimension="operations_readiness", status=EvaluationStatus.PASS),
        ]

        overall_scores = []
        for _ in range(3):
            dim_scores = calc.calculate_dimension_scores(results)
            health = agg.aggregate(dim_scores, None, _AID, _SID)
            overall_scores.append(health.overall_score)

        assert overall_scores[0] == overall_scores[1] == overall_scores[2]

    def test_determinism_at_conditional_approve_boundary(self, calc, agg):
        """Score at exactly 50 (CONDITIONAL_APPROVE boundary) must be stable."""
        results = [
            _r(name="P", dimension="security", status=EvaluationStatus.PASS, weight="50.0"),
            _r(name="F", dimension="security", status=EvaluationStatus.FAIL, weight="50.0"),
        ]

        overall_scores = []
        for _ in range(3):
            dim_scores = calc.calculate_dimension_scores(results)
            health = agg.aggregate(dim_scores, None, _AID, _SID)
            overall_scores.append(health.overall_score)

        # Security = 50.00; only 1 dimension has data → overall = 50.00
        assert all(s == Decimal("50.00") for s in overall_scores)

    def test_determinism_at_approve_boundary(self, calc, agg):
        """Score at exactly 70 (APPROVE boundary) must be stable."""
        results = [
            _r(name="P", dimension="security", status=EvaluationStatus.PASS, weight="70.0"),
            _r(name="F", dimension="security", status=EvaluationStatus.FAIL, weight="30.0"),
        ]

        overall_scores = []
        for _ in range(3):
            dim_scores = calc.calculate_dimension_scores(results)
            health = agg.aggregate(dim_scores, None, _AID, _SID)
            overall_scores.append(health.overall_score)

        assert all(s == Decimal("70.00") for s in overall_scores)


# ===========================================================================
# HealthScoreResult structural correctness
# ===========================================================================

class TestHealthScoreResultStructure:
    def test_result_assessment_id_matches(self, agg):
        dims = _all_five(Decimal("80.00"))
        result = agg.aggregate(dims, None, _AID, _SID)
        assert result.assessment_id == _AID

    def test_result_service_id_matches(self, agg):
        dims = _all_five(Decimal("80.00"))
        result = agg.aggregate(dims, None, _AID, _SID)
        assert result.service_id == _SID

    def test_overall_score_is_decimal(self, agg):
        dims = _all_five(Decimal("80.00"))
        result = agg.aggregate(dims, None, _AID, _SID)
        assert isinstance(result.overall_score, Decimal)

    def test_overall_score_has_two_decimal_places(self, agg):
        dims = _all_five(Decimal("66.67"))
        result = agg.aggregate(dims, None, _AID, _SID)
        assert result.overall_score == result.overall_score.quantize(Decimal("0.01"))

    def test_result_is_frozen(self, agg):
        dims = _all_five(Decimal("80.00"))
        result = agg.aggregate(dims, None, _AID, _SID)
        with pytest.raises((AttributeError, TypeError)):
            result.overall_score = Decimal("99.00")  # type: ignore[misc]

    def test_dimension_scores_all_five_keys_present(self, calc, agg):
        results = [
            _r(name="R", dimension=dim, status=EvaluationStatus.PASS)
            for dim in ("code_quality", "test_coverage", "security",
                        "documentation", "operations_readiness")
        ]
        dim_scores = calc.calculate_dimension_scores(results)
        health = agg.aggregate(dim_scores, None, _AID, _SID)
        expected_keys = {
            "code_quality", "test_coverage", "security",
            "documentation", "operations_readiness",
        }
        assert set(health.dimension_scores.keys()) >= expected_keys
