"""Unit tests for ComplexityScorer — boundary-value tests for each threshold bucket."""

from __future__ import annotations

import pytest

from forgeguard.services.release_guardian.models import ComplexityMetrics
from forgeguard.services.release_guardian.scorers.complexity_scorer import ComplexityScorer


def _metrics(files=0, lines_added=0, lines_deleted=0, cc_delta=0.0, churn=0.0):
    return ComplexityMetrics(
        files_changed=files,
        lines_added=lines_added,
        lines_deleted=lines_deleted,
        cyclomatic_complexity_delta=cc_delta,
        churn_score=churn,
    )


@pytest.fixture
def scorer():
    return ComplexityScorer()


class TestFilesChangedBuckets:
    def test_zero_files(self, scorer):
        score, _ = scorer.score(_metrics(files=0))
        assert score == 0

    def test_below_5_files(self, scorer):
        score, _ = scorer.score(_metrics(files=4))
        assert score == 0

    def test_at_5_files_bucket(self, scorer):
        score, _ = scorer.score(_metrics(files=5))
        assert score == 15

    def test_at_19_files(self, scorer):
        score, _ = scorer.score(_metrics(files=19))
        assert score == 15

    def test_at_20_files_bucket(self, scorer):
        score, _ = scorer.score(_metrics(files=20))
        assert score == 35

    def test_at_49_files(self, scorer):
        score, _ = scorer.score(_metrics(files=49))
        assert score == 35

    def test_at_50_files_bucket(self, scorer):
        score, _ = scorer.score(_metrics(files=50))
        assert score == 60

    def test_large_files(self, scorer):
        score, _ = scorer.score(_metrics(files=200))
        assert score == 60


class TestLinesChangedBuckets:
    def test_zero_lines(self, scorer):
        score, _ = scorer.score(_metrics(lines_added=0, lines_deleted=0))
        assert score == 0

    def test_at_99_lines(self, scorer):
        score, _ = scorer.score(_metrics(lines_added=99))
        assert score == 0

    def test_at_100_lines_bucket(self, scorer):
        score, _ = scorer.score(_metrics(lines_added=100))
        assert score == 15

    def test_lines_added_plus_deleted(self, scorer):
        # 50 added + 50 deleted = 100 total → bucket 15
        score, _ = scorer.score(_metrics(lines_added=50, lines_deleted=50))
        assert score == 15

    def test_at_499_lines(self, scorer):
        score, _ = scorer.score(_metrics(lines_added=499))
        assert score == 15

    def test_at_500_lines_bucket(self, scorer):
        score, _ = scorer.score(_metrics(lines_added=500))
        assert score == 30

    def test_at_999_lines(self, scorer):
        score, _ = scorer.score(_metrics(lines_added=999))
        assert score == 30

    def test_at_1000_lines_bucket(self, scorer):
        score, _ = scorer.score(_metrics(lines_added=1000))
        assert score == 55

    def test_large_lines(self, scorer):
        score, _ = scorer.score(_metrics(lines_added=5000))
        assert score == 55


class TestCyclomaticComplexityBuckets:
    def test_zero_cc(self, scorer):
        score, _ = scorer.score(_metrics(cc_delta=0.0))
        assert score == 0

    def test_at_4_9_cc(self, scorer):
        score, _ = scorer.score(_metrics(cc_delta=4.9))
        assert score == 0

    def test_at_5_0_cc_bucket(self, scorer):
        score, _ = scorer.score(_metrics(cc_delta=5.0))
        assert score == 10

    def test_at_14_9_cc(self, scorer):
        score, _ = scorer.score(_metrics(cc_delta=14.9))
        assert score == 10

    def test_at_15_0_cc_bucket(self, scorer):
        score, _ = scorer.score(_metrics(cc_delta=15.0))
        assert score == 20

    def test_large_cc(self, scorer):
        score, _ = scorer.score(_metrics(cc_delta=100.0))
        assert score == 20


class TestChurnScoreBuckets:
    def test_zero_churn(self, scorer):
        score, _ = scorer.score(_metrics(churn=0.0))
        assert score == 0

    def test_at_0_29_churn(self, scorer):
        score, _ = scorer.score(_metrics(churn=0.29))
        assert score == 0

    def test_at_0_3_churn_bucket(self, scorer):
        score, _ = scorer.score(_metrics(churn=0.3))
        assert score == 15

    def test_at_0_69_churn(self, scorer):
        score, _ = scorer.score(_metrics(churn=0.69))
        assert score == 15

    def test_at_0_7_churn_bucket(self, scorer):
        score, _ = scorer.score(_metrics(churn=0.7))
        assert score == 25

    def test_max_churn(self, scorer):
        score, _ = scorer.score(_metrics(churn=1.0))
        assert score == 25


class TestScoreCap:
    def test_all_max_capped_at_100(self, scorer):
        score, _ = scorer.score(_metrics(files=100, lines_added=2000, cc_delta=30.0, churn=1.0))
        # 60 + 55 + 20 + 25 = 160 → capped at 100
        assert score == 100


class TestContributingFactors:
    def test_returns_four_factors(self, scorer):
        _, factors = scorer.score(_metrics(files=5, lines_added=100, cc_delta=5.0, churn=0.3))
        assert len(factors) == 4

    def test_factor_dimension_is_code_complexity(self, scorer):
        _, factors = scorer.score(_metrics(files=5))
        assert all(f.dimension == "code_complexity" for f in factors)

    def test_factor_metric_names(self, scorer):
        _, factors = scorer.score(_metrics())
        names = {f.metric_name for f in factors}
        assert names == {"files_changed", "lines_changed", "cyclomatic_complexity_delta", "churn_score"}
