"""Unit tests for HealthScoreAggregator (WO-040).

Covers:
  - Equal-weight aggregation with all five dimensions having data
  - Custom weights with varied scores
  - Weight redistribution for 1, 2, 3, 4, and 5 null dimensions
  - Single dimension with data (100% effective weight)
  - Boundary values: all 0.00, all 100.00
  - HealthScoreResult fields: overall_score, weights_used, dimensions_with_data,
    dimensions_without_data, assessment_id, service_id, calculated_at
  - Decimal precision: 2 decimal places, ROUND_HALF_UP
  - Benchmark: aggregation completes within 10ms

Run:
    pytest tests/unit/services/test_health_score_aggregator.py -v
"""

from __future__ import annotations

import time
import uuid
from decimal import Decimal

import pytest

from forgeguard.services.domain.scoring import DimensionScore, HealthScoreResult
from forgeguard.services.health_score_aggregator import (
    DEFAULT_WEIGHTS,
    HealthScoreAggregator,
)
from tests.fixtures.health_score_fixtures import (
    ALL_EQUAL_80,
    ALL_HUNDRED,
    ALL_NO_DATA,
    ALL_ZERO,
    DOCS_NO_DATA,
    SECURITY_WEIGHTED,
    SECURITY_WEIGHTS,
    SINGLE_DIMENSION,
    TWO_MISSING,
    VARIED_EQUAL_WEIGHTS,
    _ds,
    _ASSESSMENT_ID,
    _SERVICE_ID,
)

# ---------------------------------------------------------------------------
# Shared fixture
# ---------------------------------------------------------------------------


@pytest.fixture()
def agg() -> HealthScoreAggregator:
    return HealthScoreAggregator()


@pytest.fixture()
def aid() -> uuid.UUID:
    return _ASSESSMENT_ID


@pytest.fixture()
def sid() -> uuid.UUID:
    return _SERVICE_ID


# ===========================================================================
# Default weights
# ===========================================================================

class TestDefaultWeights:
    def test_all_equal_scores_with_default_weights(self, agg, aid, sid):
        result = agg.aggregate(ALL_EQUAL_80, None, aid, sid)
        assert result.overall_score == Decimal("80.00")

    def test_default_weights_are_equal(self, agg, aid, sid):
        for dim_weight in DEFAULT_WEIGHTS.values():
            assert dim_weight == Decimal("20")

    def test_five_default_dimensions(self):
        assert len(DEFAULT_WEIGHTS) == 5

    def test_default_weights_sum_to_100(self):
        assert sum(DEFAULT_WEIGHTS.values()) == Decimal("100")

    def test_varied_scores_equal_weights(self, agg, aid, sid):
        # (50+60+70+80+90) / 5 = 70.00
        result = agg.aggregate(VARIED_EQUAL_WEIGHTS, None, aid, sid)
        assert result.overall_score == Decimal("70.00")

    def test_all_zero_scores(self, agg, aid, sid):
        result = agg.aggregate(ALL_ZERO, None, aid, sid)
        assert result.overall_score == Decimal("0.00")

    def test_all_hundred_scores(self, agg, aid, sid):
        result = agg.aggregate(ALL_HUNDRED, None, aid, sid)
        assert result.overall_score == Decimal("100.00")


# ===========================================================================
# Custom weights
# ===========================================================================

class TestCustomWeights:
    def test_security_double_weight_pulls_score_down(self, agg, aid, sid):
        # SECURITY_WEIGHTED: all 100 except security=50, security weight=40/100
        result = agg.aggregate(SECURITY_WEIGHTED, SECURITY_WEIGHTS, aid, sid)
        assert result.overall_score == Decimal("80.00")

    def test_weights_used_reflects_custom(self, agg, aid, sid):
        result = agg.aggregate(SECURITY_WEIGHTED, SECURITY_WEIGHTS, aid, sid)
        # All 5 dimensions have data, so weights_used == normalised custom weights
        assert result.weights_used["security"] == Decimal("40.00")
        assert result.weights_used["code_quality"] == Decimal("10.00")

    def test_custom_weights_used_stored_in_result(self, agg, aid, sid):
        result = agg.aggregate(SECURITY_WEIGHTED, SECURITY_WEIGHTS, aid, sid)
        assert result.weights_used is not None
        assert len(result.weights_used) == len(SECURITY_WEIGHTED)

    def test_single_high_weight_dimension(self, agg, aid, sid):
        # security=100 weight 80; all others weight 5 each, score 0
        weights = {
            "code_quality": Decimal("5"),
            "test_coverage": Decimal("5"),
            "security": Decimal("80"),
            "documentation": Decimal("5"),
            "operations_readiness": Decimal("5"),
        }
        dim_scores = {
            "code_quality": _ds(dimension="code_quality", score=Decimal("0.00"), failed=1, passed=0),
            "test_coverage": _ds(dimension="test_coverage", score=Decimal("0.00"), failed=1, passed=0),
            "security": _ds(dimension="security", score=Decimal("100.00")),
            "documentation": _ds(dimension="documentation", score=Decimal("0.00"), failed=1, passed=0),
            "operations_readiness": _ds(dimension="operations_readiness", score=Decimal("0.00"), failed=1, passed=0),
        }
        result = agg.aggregate(dim_scores, weights, aid, sid)
        # 100*80 / 100 = 80.00
        assert result.overall_score == Decimal("80.00")


# ===========================================================================
# Weight redistribution — null dimensions
# ===========================================================================

class TestWeightRedistribution:
    def test_one_null_dimension_redistributes(self, agg, aid, sid):
        # docs has no data; remaining 4 all score 80 → still 80.00
        result = agg.aggregate(DOCS_NO_DATA, None, aid, sid)
        assert result.overall_score == Decimal("80.00")

    def test_one_null_dimension_dimensions_with_data_count(self, agg, aid, sid):
        result = agg.aggregate(DOCS_NO_DATA, None, aid, sid)
        assert result.dimensions_with_data == 4
        assert result.dimensions_without_data == 1

    def test_one_null_inactive_weight_is_zero(self, agg, aid, sid):
        result = agg.aggregate(DOCS_NO_DATA, None, aid, sid)
        assert result.weights_used["documentation"] == Decimal("0.00")

    def test_one_null_active_weights_sum_to_100(self, agg, aid, sid):
        result = agg.aggregate(DOCS_NO_DATA, None, aid, sid)
        total = sum(result.weights_used.values())
        # Allow rounding tolerance
        assert abs(total - Decimal("100")) <= Decimal("0.05")

    def test_two_null_dimensions(self, agg, aid, sid):
        # security=60, docs=90, ops=75 → equal weights → (60+90+75)/3 = 75.00
        result = agg.aggregate(TWO_MISSING, None, aid, sid)
        assert result.overall_score == Decimal("75.00")

    def test_two_null_dimensions_count(self, agg, aid, sid):
        result = agg.aggregate(TWO_MISSING, None, aid, sid)
        assert result.dimensions_with_data == 3
        assert result.dimensions_without_data == 2

    def test_four_null_dimensions(self, agg, aid, sid):
        # Only security has data, score=60 → overall = 60.00
        dims = {
            "code_quality": _ds(dimension="code_quality", score=None, has_data=False),
            "test_coverage": _ds(dimension="test_coverage", score=None, has_data=False),
            "security": _ds(dimension="security", score=Decimal("60.00")),
            "documentation": _ds(dimension="documentation", score=None, has_data=False),
            "operations_readiness": _ds(dimension="operations_readiness", score=None, has_data=False),
        }
        result = agg.aggregate(dims, None, aid, sid)
        assert result.overall_score == Decimal("60.00")

    def test_four_null_effective_weight_100(self, agg, aid, sid):
        result = agg.aggregate(SINGLE_DIMENSION, None, aid, sid)
        # security is the only active dim; it should get 100% effective weight
        assert result.weights_used["security"] == Decimal("100.00")
        assert result.weights_used["code_quality"] == Decimal("0.00")


# ===========================================================================
# Single dimension with data
# ===========================================================================

class TestSingleDimension:
    def test_single_dimension_score_equals_overall(self, agg, aid, sid):
        result = agg.aggregate(SINGLE_DIMENSION, None, aid, sid)
        assert result.overall_score == Decimal("72.50")

    def test_single_dimension_counts(self, agg, aid, sid):
        result = agg.aggregate(SINGLE_DIMENSION, None, aid, sid)
        assert result.dimensions_with_data == 1
        assert result.dimensions_without_data == 4


# ===========================================================================
# All dimensions null
# ===========================================================================

class TestAllDimensionsNull:
    def test_overall_score_is_none(self, agg, aid, sid):
        result = agg.aggregate(ALL_NO_DATA, None, aid, sid)
        assert result.overall_score is None

    def test_dimensions_with_data_zero(self, agg, aid, sid):
        result = agg.aggregate(ALL_NO_DATA, None, aid, sid)
        assert result.dimensions_with_data == 0
        assert result.dimensions_without_data == 5

    def test_all_weights_used_zero(self, agg, aid, sid):
        result = agg.aggregate(ALL_NO_DATA, None, aid, sid)
        for w in result.weights_used.values():
            assert w == Decimal("0.00")


# ===========================================================================
# HealthScoreResult fields
# ===========================================================================

class TestHealthScoreResultFields:
    def test_assessment_id_matches(self, agg, aid, sid):
        result = agg.aggregate(ALL_EQUAL_80, None, aid, sid)
        assert result.assessment_id == aid

    def test_service_id_matches(self, agg, aid, sid):
        result = agg.aggregate(ALL_EQUAL_80, None, aid, sid)
        assert result.service_id == sid

    def test_calculated_at_is_set(self, agg, aid, sid):
        result = agg.aggregate(ALL_EQUAL_80, None, aid, sid)
        assert result.calculated_at is not None

    def test_dimension_scores_preserved(self, agg, aid, sid):
        result = agg.aggregate(ALL_EQUAL_80, None, aid, sid)
        assert set(result.dimension_scores.keys()) == set(ALL_EQUAL_80.keys())

    def test_overall_score_is_decimal(self, agg, aid, sid):
        result = agg.aggregate(ALL_EQUAL_80, None, aid, sid)
        assert isinstance(result.overall_score, Decimal)

    def test_result_is_frozen(self, agg, aid, sid):
        result = agg.aggregate(ALL_EQUAL_80, None, aid, sid)
        with pytest.raises((AttributeError, TypeError)):
            result.overall_score = Decimal("99")  # type: ignore[misc]


# ===========================================================================
# Decimal precision
# ===========================================================================

class TestDecimalPrecision:
    def test_score_has_two_decimal_places(self, agg, aid, sid):
        result = agg.aggregate(ALL_EQUAL_80, None, aid, sid)
        assert result.overall_score == result.overall_score.quantize(Decimal("0.01"))

    def test_uneven_division_rounded(self, agg, aid, sid):
        # 3 dims each score 100, weights 20/20/60 → 100.00 (trivial)
        # Use varied to test rounding: (33+67+100)/3 = 66.666... → 66.67
        dims = {
            "code_quality": _ds(dimension="code_quality", score=Decimal("33.00")),
            "test_coverage": _ds(dimension="test_coverage", score=Decimal("67.00")),
            "security": _ds(dimension="security", score=Decimal("100.00")),
            "documentation": _ds(dimension="documentation", score=None, has_data=False),
            "operations_readiness": _ds(dimension="operations_readiness", score=None, has_data=False),
        }
        result = agg.aggregate(dims, None, aid, sid)
        # (33*20 + 67*20 + 100*20) / 60 = (660+1340+2000)/60 = 4000/60 = 66.666... → 66.67
        assert result.overall_score == Decimal("66.67")

    def test_weights_used_two_decimal_places(self, agg, aid, sid):
        result = agg.aggregate(DOCS_NO_DATA, None, aid, sid)
        for w in result.weights_used.values():
            assert w == w.quantize(Decimal("0.01"))


# ===========================================================================
# Performance benchmark
# ===========================================================================

class TestPerformance:
    def test_aggregation_within_10ms(self, agg, aid, sid):
        start = time.perf_counter()
        for _ in range(100):
            agg.aggregate(ALL_EQUAL_80, None, aid, sid)
        elapsed_ms = (time.perf_counter() - start) * 1000
        per_call_ms = elapsed_ms / 100
        assert per_call_ms < 10, (
            f"HealthScoreAggregator.aggregate took {per_call_ms:.2f}ms per call, "
            "budget is 10ms"
        )

    def test_single_call_within_10ms(self, agg, aid, sid):
        start = time.perf_counter()
        agg.aggregate(ALL_EQUAL_80, None, aid, sid)
        elapsed_ms = (time.perf_counter() - start) * 1000
        assert elapsed_ms < 10, f"Single call took {elapsed_ms:.2f}ms, budget is 10ms"
