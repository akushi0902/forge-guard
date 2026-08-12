"""Unit tests for DimensionScoreCalculator (WO-039).

Covers:
  - All-pass dimension → score 100.00
  - All-fail dimension → score 0.00
  - Mixed pass/fail with different weights → weighted score
  - All-inconclusive → score None, has_data False
  - Error rules treated as failures
  - Zero-weight rules → score None (weighted_total=0, has_data False)
  - Single-rule dimensions
  - All 5 statuses in one dimension
  - Multi-dimension batch: all 5 dimensions present
  - Empty results: all known dims get score None
  - Unknown dimension: scored + warning logged
  - ContributingFactor signs: positive for PASS, negative for FAIL/ERROR
  - Decimal precision: scores are always 2dp
  - INCONCLUSIVE excluded from denominator

Run:
    pytest tests/unit/services/test_dimension_scorer.py -v
"""

from __future__ import annotations

import time
import uuid
from decimal import Decimal

import pytest

from forgeguard.services.dimension_scorer import DimensionScoreCalculator
from forgeguard.services.domain.evaluation import EvaluationStatus
from forgeguard.services.domain.scoring import VALID_DIMENSIONS
from tests.fixtures.scoring_fixtures import (
    ALL_FAIL_RESULTS,
    ALL_INCONCLUSIVE_RESULTS,
    ALL_PASS_RESULTS,
    ALL_STATUS_RESULTS,
    ERROR_RESULTS,
    FIFTY_RULE_RESULTS,
    MIXED_RESULTS,
    MULTI_DIMENSION_RESULTS,
    SINGLE_FAIL_RESULTS,
    SINGLE_PASS_RESULTS,
    ZERO_WEIGHT_RESULTS,
    _r,
)


@pytest.fixture()
def calc() -> DimensionScoreCalculator:
    return DimensionScoreCalculator()


# ===========================================================================
# All-pass
# ===========================================================================

class TestAllPass:
    def test_score_is_100(self, calc):
        scores = calc.calculate_dimension_scores(ALL_PASS_RESULTS)
        assert scores["test_coverage"].score == Decimal("100.00")

    def test_has_data_true(self, calc):
        scores = calc.calculate_dimension_scores(ALL_PASS_RESULTS)
        assert scores["test_coverage"].has_data is True

    def test_passed_rules_count(self, calc):
        scores = calc.calculate_dimension_scores(ALL_PASS_RESULTS)
        assert scores["test_coverage"].passed_rules == 3

    def test_failed_rules_zero(self, calc):
        scores = calc.calculate_dimension_scores(ALL_PASS_RESULTS)
        assert scores["test_coverage"].failed_rules == 0

    def test_all_factors_positive(self, calc):
        scores = calc.calculate_dimension_scores(ALL_PASS_RESULTS)
        for f in scores["test_coverage"].contributing_factors:
            assert f.score_impact > Decimal("0")


# ===========================================================================
# All-fail
# ===========================================================================

class TestAllFail:
    def test_score_is_0(self, calc):
        scores = calc.calculate_dimension_scores(ALL_FAIL_RESULTS)
        assert scores["security"].score == Decimal("0.00")

    def test_has_data_true(self, calc):
        scores = calc.calculate_dimension_scores(ALL_FAIL_RESULTS)
        assert scores["security"].has_data is True

    def test_failed_rules_count(self, calc):
        scores = calc.calculate_dimension_scores(ALL_FAIL_RESULTS)
        assert scores["security"].failed_rules == 3

    def test_all_factors_negative(self, calc):
        scores = calc.calculate_dimension_scores(ALL_FAIL_RESULTS)
        for f in scores["security"].contributing_factors:
            assert f.score_impact < Decimal("0")


# ===========================================================================
# Mixed weights
# ===========================================================================

class TestMixedWeights:
    def test_weighted_score(self, calc):
        # PASS w=2+2=4, FAIL w=1, total=5 → 4/5*100 = 80.00
        scores = calc.calculate_dimension_scores(MIXED_RESULTS)
        assert scores["documentation"].score == Decimal("80.00")

    def test_contributing_factor_signs(self, calc):
        scores = calc.calculate_dimension_scores(MIXED_RESULTS)
        factors_by_name = {f.rule_name: f for f in scores["documentation"].contributing_factors}
        assert factors_by_name["API Docs"].score_impact > Decimal("0")
        assert factors_by_name["README"].score_impact > Decimal("0")
        assert factors_by_name["Runbook"].score_impact < Decimal("0")

    def test_total_rules_count(self, calc):
        scores = calc.calculate_dimension_scores(MIXED_RESULTS)
        assert scores["documentation"].total_rules == 3


# ===========================================================================
# All inconclusive
# ===========================================================================

class TestAllInconclusive:
    def test_score_is_none(self, calc):
        scores = calc.calculate_dimension_scores(ALL_INCONCLUSIVE_RESULTS)
        assert scores["code_quality"].score is None

    def test_has_data_false(self, calc):
        scores = calc.calculate_dimension_scores(ALL_INCONCLUSIVE_RESULTS)
        assert scores["code_quality"].has_data is False

    def test_inconclusive_count(self, calc):
        scores = calc.calculate_dimension_scores(ALL_INCONCLUSIVE_RESULTS)
        assert scores["code_quality"].inconclusive_rules == 2

    def test_factors_have_zero_impact(self, calc):
        scores = calc.calculate_dimension_scores(ALL_INCONCLUSIVE_RESULTS)
        for f in scores["code_quality"].contributing_factors:
            assert f.score_impact == Decimal("0")


# ===========================================================================
# Error rules as failures
# ===========================================================================

class TestErrorRules:
    def test_error_treated_as_fail(self, calc):
        # PASS w=1 + ERROR w=1 → 1/2*100 = 50.00
        scores = calc.calculate_dimension_scores(ERROR_RESULTS)
        assert scores["operations_readiness"].score == Decimal("50.00")

    def test_error_rules_count(self, calc):
        scores = calc.calculate_dimension_scores(ERROR_RESULTS)
        assert scores["operations_readiness"].error_rules == 1

    def test_error_factor_is_negative(self, calc):
        scores = calc.calculate_dimension_scores(ERROR_RESULTS)
        err_factor = next(
            f for f in scores["operations_readiness"].contributing_factors
            if f.status == EvaluationStatus.ERROR
        )
        assert err_factor.score_impact < Decimal("0")


# ===========================================================================
# Zero-weight rules
# ===========================================================================

class TestZeroWeight:
    def test_all_zero_weight_score_is_none(self, calc):
        scores = calc.calculate_dimension_scores(ZERO_WEIGHT_RESULTS)
        assert scores["documentation"].score is None

    def test_all_zero_weight_has_data_false(self, calc):
        scores = calc.calculate_dimension_scores(ZERO_WEIGHT_RESULTS)
        assert scores["documentation"].has_data is False


# ===========================================================================
# Single rule
# ===========================================================================

class TestSingleRule:
    def test_single_pass_is_100(self, calc):
        scores = calc.calculate_dimension_scores(SINGLE_PASS_RESULTS)
        assert scores["security"].score == Decimal("100.00")

    def test_single_fail_is_0(self, calc):
        scores = calc.calculate_dimension_scores(SINGLE_FAIL_RESULTS)
        assert scores["security"].score == Decimal("0.00")


# ===========================================================================
# All four statuses in one dimension
# ===========================================================================

class TestAllStatuses:
    def test_score_with_all_statuses(self, calc):
        # PASS w=2, FAIL w=1, ERROR w=1, INCONCLUSIVE excluded
        # weighted_pass=2, weighted_total=4 → 50.00
        scores = calc.calculate_dimension_scores(ALL_STATUS_RESULTS)
        assert scores["code_quality"].score == Decimal("50.00")

    def test_counts_correct(self, calc):
        scores = calc.calculate_dimension_scores(ALL_STATUS_RESULTS)
        ds = scores["code_quality"]
        assert ds.passed_rules == 1
        assert ds.failed_rules == 1
        assert ds.inconclusive_rules == 1
        assert ds.error_rules == 1
        assert ds.total_rules == 4

    def test_inconclusive_factor_impact_zero(self, calc):
        scores = calc.calculate_dimension_scores(ALL_STATUS_RESULTS)
        inconcl_factor = next(
            f for f in scores["code_quality"].contributing_factors
            if f.status == EvaluationStatus.INCONCLUSIVE
        )
        assert inconcl_factor.score_impact == Decimal("0")


# ===========================================================================
# Multi-dimension batch
# ===========================================================================

class TestMultiDimension:
    def test_all_five_known_dimensions_present(self, calc):
        scores = calc.calculate_dimension_scores(MULTI_DIMENSION_RESULTS)
        assert set(scores.keys()) >= VALID_DIMENSIONS

    def test_code_quality_score(self, calc):
        # CQ: PASS w=1 + FAIL w=1 → 50.00
        scores = calc.calculate_dimension_scores(MULTI_DIMENSION_RESULTS)
        assert scores["code_quality"].score == Decimal("50.00")

    def test_test_coverage_score(self, calc):
        # TC: PASS w=2 only → 100.00
        scores = calc.calculate_dimension_scores(MULTI_DIMENSION_RESULTS)
        assert scores["test_coverage"].score == Decimal("100.00")

    def test_security_score(self, calc):
        # SEC: FAIL w=3 → 0.00
        scores = calc.calculate_dimension_scores(MULTI_DIMENSION_RESULTS)
        assert scores["security"].score == Decimal("0.00")


# ===========================================================================
# Empty results
# ===========================================================================

class TestEmptyResults:
    def test_empty_returns_all_five_dims(self, calc):
        scores = calc.calculate_dimension_scores([])
        assert set(scores.keys()) == VALID_DIMENSIONS

    def test_all_scores_none(self, calc):
        scores = calc.calculate_dimension_scores([])
        for dim in VALID_DIMENSIONS:
            assert scores[dim].score is None

    def test_all_has_data_false(self, calc):
        scores = calc.calculate_dimension_scores([])
        for dim in VALID_DIMENSIONS:
            assert scores[dim].has_data is False


# ===========================================================================
# Unknown dimension
# ===========================================================================

class TestUnknownDimension:
    def test_unknown_dim_still_scored(self, calc):
        result = _r(
            name="Unknown Rule",
            dimension="compliance",  # not in VALID_DIMENSIONS
            status=EvaluationStatus.PASS,
        )
        scores = calc.calculate_dimension_scores([result])
        assert "compliance" in scores
        assert scores["compliance"].score == Decimal("100.00")


# ===========================================================================
# Decimal precision
# ===========================================================================

class TestDecimalPrecision:
    def test_score_is_decimal_type(self, calc):
        scores = calc.calculate_dimension_scores(ALL_PASS_RESULTS)
        assert isinstance(scores["test_coverage"].score, Decimal)

    def test_score_has_two_decimal_places(self, calc):
        scores = calc.calculate_dimension_scores(MIXED_RESULTS)
        score = scores["documentation"].score
        assert score == score.quantize(Decimal("0.01"))

    def test_uneven_weight_division_rounded(self, calc):
        # 1 pass (w=1) + 2 fail (w=1 each) → 1/3 * 100 = 33.33 (ROUND_HALF_UP)
        results = [
            _r(name="P", dimension="security", status=EvaluationStatus.PASS, weight="1.0"),
            _r(name="F1", dimension="security", status=EvaluationStatus.FAIL, weight="1.0"),
            _r(name="F2", dimension="security", status=EvaluationStatus.FAIL, weight="1.0"),
        ]
        scores = calc.calculate_dimension_scores(results)
        assert scores["security"].score == Decimal("33.33")

    def test_small_weight_precision(self, calc):
        results = [
            _r(name="A", dimension="documentation", status=EvaluationStatus.PASS, weight="0.01"),
            _r(name="B", dimension="documentation", status=EvaluationStatus.FAIL, weight="0.01"),
        ]
        scores = calc.calculate_dimension_scores(results)
        assert scores["documentation"].score == Decimal("50.00")


# ===========================================================================
# Contributing factors
# ===========================================================================

class TestContributingFactors:
    def test_factor_count_matches_total_rules(self, calc):
        scores = calc.calculate_dimension_scores(ALL_STATUS_RESULTS)
        ds = scores["code_quality"]
        assert len(ds.contributing_factors) == ds.total_rules

    def test_factor_has_correct_weight(self, calc):
        scores = calc.calculate_dimension_scores(MIXED_RESULTS)
        factors = {f.rule_name: f for f in scores["documentation"].contributing_factors}
        assert factors["API Docs"].weight == Decimal("2.0")
        assert factors["Runbook"].weight == Decimal("1.0")

    def test_positive_impacts_sum_to_score(self, calc):
        # For all-pass, sum of impacts should equal score
        scores = calc.calculate_dimension_scores(ALL_PASS_RESULTS)
        ds = scores["test_coverage"]
        total_impact = sum(f.score_impact for f in ds.contributing_factors)
        assert total_impact == ds.score


# ===========================================================================
# Performance benchmark
# ===========================================================================

class TestPerformance:
    def test_50_rules_within_50ms(self, calc):
        start = time.perf_counter()
        calc.calculate_dimension_scores(FIFTY_RULE_RESULTS)
        elapsed_ms = (time.perf_counter() - start) * 1000
        assert elapsed_ms < 50, f"Dimension scoring took {elapsed_ms:.1f}ms, budget is 50ms"
