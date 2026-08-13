"""Unit tests for CoverageScorer — boundary-value tests for each threshold."""

from __future__ import annotations

import pytest

from forgeguard.services.release_guardian.models import CoverageMetrics
from forgeguard.services.release_guardian.scorers.coverage_scorer import CoverageScorer


def _metrics(
    delta=0.0,
    has_new_tests=False,
    ratio=0.0,
    test_files=0,
    test_lines_added=0,
):
    return CoverageMetrics(
        test_files_changed=test_files,
        test_lines_added=test_lines_added,
        estimated_coverage_delta=delta,
        has_new_tests=has_new_tests,
        test_to_code_ratio=ratio,
    )


@pytest.fixture
def scorer():
    return CoverageScorer()


class TestCoverageDeltaBuckets:
    def test_positive_delta_no_contribution(self, scorer):
        score, _ = scorer.score(_metrics(delta=2.0))
        assert score == 0

    def test_zero_delta_no_contribution(self, scorer):
        score, _ = scorer.score(_metrics(delta=0.0))
        assert score == 0

    def test_minus_one_bucket(self, scorer):
        # -1.0 >= -1.0 → 20
        score, _ = scorer.score(_metrics(delta=-1.0))
        assert score == 20

    def test_minus_0_5_bucket(self, scorer):
        # -0.5 >= -1.0 → 20
        score, _ = scorer.score(_metrics(delta=-0.5))
        assert score == 20

    def test_minus_two_bucket(self, scorer):
        # -2.0 >= -2.0 → 40
        score, _ = scorer.score(_metrics(delta=-2.0))
        assert score == 40

    def test_minus_1_5_bucket(self, scorer):
        # -1.5 >= -2.0 → 40
        score, _ = scorer.score(_metrics(delta=-1.5))
        assert score == 40

    def test_below_minus_two_bucket(self, scorer):
        # < -2.0 → 60
        score, _ = scorer.score(_metrics(delta=-3.0))
        assert score == 60


class TestNoNewTestsPenalty:
    def test_no_penalty_when_no_code_added(self, scorer):
        # code_lines_added = 0 → no penalty
        score, _ = scorer.score(_metrics(delta=0.0, has_new_tests=False), code_lines_added=0)
        assert score == 0

    def test_no_penalty_with_10_code_lines_at_threshold(self, scorer):
        # code_lines_added = 10 (not > 10) → no penalty
        score, _ = scorer.score(_metrics(has_new_tests=False), code_lines_added=10)
        assert score == 0

    def test_penalty_when_11_code_lines_no_tests(self, scorer):
        # delta=0→0, no_tests (>10)→30, ratio=0.0<0.1→45; total=75
        score, _ = scorer.score(_metrics(has_new_tests=False), code_lines_added=11)
        assert score == 75

    def test_no_penalty_when_has_new_tests(self, scorer):
        score, _ = scorer.score(_metrics(has_new_tests=True, ratio=0.5), code_lines_added=100)
        assert score == 0  # delta=0→0, has_tests→0, ratio=0.5→0


class TestTestToCodeRatioBuckets:
    def test_ratio_zero_no_code_added(self, scorer):
        # code_lines_added=0 → ratio component skipped
        score, _ = scorer.score(_metrics(ratio=0.0, has_new_tests=False), code_lines_added=0)
        assert score == 0

    def test_ratio_at_0_5_no_penalty(self, scorer):
        score, _ = scorer.score(_metrics(ratio=0.5, has_new_tests=True), code_lines_added=100)
        assert score == 0

    def test_ratio_at_0_2_bucket(self, scorer):
        # ratio=0.2: >= 0.2 → 15; delta=0; has_new_tests=True → no no-tests penalty
        score, _ = scorer.score(_metrics(ratio=0.2, has_new_tests=True), code_lines_added=100)
        assert score == 15

    def test_ratio_at_0_1_bucket(self, scorer):
        # ratio=0.1: >= 0.1 → 30; delta=0; has_new_tests=True → no no-tests penalty
        score, _ = scorer.score(_metrics(ratio=0.1, has_new_tests=True), code_lines_added=100)
        assert score == 30

    def test_ratio_below_0_1_bucket(self, scorer):
        # ratio=0.05: < 0.1 → 45; delta=0; has_new_tests=True → no no-tests penalty
        score, _ = scorer.score(_metrics(ratio=0.05, has_new_tests=True), code_lines_added=100)
        assert score == 45


class TestScoreCap:
    def test_score_capped_at_100(self, scorer):
        # delta=-3.0→60, no_tests→30, ratio<0.1→45; total=135 → 100
        score, _ = scorer.score(_metrics(delta=-3.0, has_new_tests=False, ratio=0.0), code_lines_added=200)
        assert score == 100


class TestContributingFactors:
    def test_returns_three_factors(self, scorer):
        _, factors = scorer.score(_metrics())
        assert len(factors) == 3

    def test_factor_dimension_is_test_coverage(self, scorer):
        _, factors = scorer.score(_metrics())
        assert all(f.dimension == "test_coverage" for f in factors)

    def test_factor_metric_names(self, scorer):
        _, factors = scorer.score(_metrics())
        names = {f.metric_name for f in factors}
        assert names == {"estimated_coverage_delta", "no_new_tests_with_code", "test_to_code_ratio"}
