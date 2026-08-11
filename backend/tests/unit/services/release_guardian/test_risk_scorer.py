"""Unit tests for RiskScorer — regression tests, floor, incomplete dimensions."""

from __future__ import annotations

import pytest

from forgeguard.services.release_guardian.models import (
    AnalysisMetadata,
    ChangeAnalysisResult,
    ComplexityMetrics,
    CoverageMetrics,
    CVEInfo,
    DependencyMetrics,
    RiskScoringConfig,
    SecurityMetrics,
)
from forgeguard.services.release_guardian.risk_scorer import RiskScorer
from tests.fixtures.risk_scoring.fixtures import RISK_SCORING_FIXTURES


def _result(
    complexity=None, coverage=None, dependencies=None, security=None, incomplete=None
):
    return ChangeAnalysisResult(
        complexity=complexity or ComplexityMetrics(),
        coverage=coverage or CoverageMetrics(),
        dependencies=dependencies or DependencyMetrics(),
        security=security or SecurityMetrics(),
        metadata=AnalysisMetadata(incomplete_dimensions=incomplete or []),
    )


@pytest.fixture
def scorer():
    return RiskScorer()


class TestRegressionFixtures:
    """Regression tests using the 10 pre-defined fixtures.

    Any algorithm change that alters an expected score is a BREAKING CHANGE.
    """

    @pytest.mark.parametrize(
        "analysis, expected_score",
        RISK_SCORING_FIXTURES,
        ids=[
            "empty",
            "small_safe",
            "medium_no_tests",
            "secrets_floor",
            "dependency_heavy",
            "coverage_loss",
            "test_only",
            "max_risk",
            "secrets_minimal",
            "mixed_medium",
        ],
    )
    def test_fixture_score(self, scorer, analysis, expected_score):
        result = scorer.score(analysis)
        assert result.overall_score == expected_score


class TestDeterminism:
    def test_same_input_same_output(self, scorer):
        analysis = _result(
            complexity=ComplexityMetrics(files_changed=10, lines_added=200, cyclomatic_complexity_delta=5.0, churn_score=0.4),
        )
        r1 = scorer.score(analysis)
        r2 = scorer.score(analysis)
        assert r1.overall_score == r2.overall_score
        assert r1.dimension_scores == r2.dimension_scores

    def test_independent_instances_produce_same_result(self):
        analysis = _result(
            security=SecurityMetrics(sql_patterns_detected=2),
        )
        s1 = RiskScorer()
        s2 = RiskScorer()
        assert s1.score(analysis).overall_score == s2.score(analysis).overall_score


class TestCriticalSecurityFloor:
    def test_secrets_triggers_floor_when_below_70(self, scorer):
        analysis = _result(security=SecurityMetrics(secrets_detected=1))
        result = scorer.score(analysis)
        assert result.overall_score >= 70

    def test_no_floor_when_score_already_above_70(self, scorer):
        # All 4 dimensions at high risk (non-secrets)
        analysis = _result(
            complexity=ComplexityMetrics(files_changed=60, lines_added=1200, cyclomatic_complexity_delta=20.0, churn_score=0.9),
            coverage=CoverageMetrics(estimated_coverage_delta=-3.0, has_new_tests=False),
            dependencies=DependencyMetrics(
                dependencies_added=[f"d{i}" for i in range(12)],
                major_version_bumps=4,
                known_cves=[CVEInfo(id=f"CVE-{i}", severity="critical", affected_package=f"pkg{i}") for i in range(4)],
            ),
            security=SecurityMetrics(secrets_detected=1),
        )
        result = scorer.score(analysis)
        assert result.overall_score == 100

    def test_no_secrets_no_floor_applied(self, scorer):
        analysis = _result(
            complexity=ComplexityMetrics(files_changed=5, lines_added=100),
        )
        result = scorer.score(analysis)
        assert result.overall_score < 70


class TestIncompleteDimensions:
    def test_incomplete_dimension_uses_neutral_50(self, scorer):
        analysis = _result(incomplete=["code_complexity", "test_coverage", "dependencies", "security"])
        result = scorer.score(analysis)
        # All dims = 50, weighted sum = 50*0.25*4 = 50
        assert result.overall_score == 50

    def test_single_incomplete_dimension_mixed(self, scorer):
        # code_complexity incomplete → 50; others zero
        analysis = _result(incomplete=["code_complexity"])
        result = scorer.score(analysis)
        # 50*0.25 + 0*0.25 + 0*0.25 + 0*0.25 = 12.5 → 12 or 13 depending on rounding
        # ROUND_HALF_UP: 12.5 → 13
        assert result.overall_score == 13

    def test_incomplete_dimension_names_preserved(self, scorer):
        analysis = _result(incomplete=["dependencies"])
        result = scorer.score(analysis)
        assert result.dimension_scores["dependencies"] == 50


class TestCustomWeights:
    def test_security_only_weight(self):
        config = RiskScoringConfig(dimension_weights={
            "code_complexity": 0.0,
            "test_coverage": 0.0,
            "dependencies": 0.0,
            "security": 1.0,
        })
        scorer = RiskScorer(config=config)
        analysis = _result(security=SecurityMetrics(sql_patterns_detected=2))
        result = scorer.score(analysis)
        # security score: 2*25=50; overall = 50*1.0 = 50
        assert result.overall_score == 50

    def test_weights_used_in_result(self):
        custom_weights = {
            "code_complexity": 0.4,
            "test_coverage": 0.3,
            "dependencies": 0.2,
            "security": 0.1,
        }
        scorer = RiskScorer(config=RiskScoringConfig(dimension_weights=custom_weights))
        result = scorer.score(_result())
        assert result.weights_used == custom_weights


class TestTopContributingFactors:
    def test_at_most_5_factors(self, scorer):
        # Trigger many factors by using all dimensions
        analysis = _result(
            complexity=ComplexityMetrics(files_changed=50, lines_added=500, cyclomatic_complexity_delta=10.0, churn_score=0.5),
            security=SecurityMetrics(sql_patterns_detected=2),
        )
        result = scorer.score(analysis)
        assert len(result.contributing_factors) <= 5

    def test_factors_sorted_by_contribution_descending(self, scorer):
        analysis = _result(
            complexity=ComplexityMetrics(files_changed=50, lines_added=500, cyclomatic_complexity_delta=10.0, churn_score=0.5),
        )
        result = scorer.score(analysis)
        contribs = [f.risk_contribution for f in result.contributing_factors]
        assert contribs == sorted(contribs, reverse=True)

    def test_empty_change_returns_zero_risk_contributions(self, scorer):
        result = scorer.score(_result())
        total_contrib = sum(f.risk_contribution for f in result.contributing_factors)
        assert total_contrib == 0


class TestResultShape:
    def test_result_has_all_four_dimensions(self, scorer):
        result = scorer.score(_result())
        assert set(result.dimension_scores.keys()) == {
            "code_complexity", "test_coverage", "dependencies", "security"
        }

    def test_overall_score_in_range(self, scorer):
        analysis = _result(
            complexity=ComplexityMetrics(files_changed=50, lines_added=1000),
            security=SecurityMetrics(sql_patterns_detected=3, unsafe_deserialization_detected=2),
        )
        result = scorer.score(analysis)
        assert 0 <= result.overall_score <= 100

    def test_scored_at_is_populated(self, scorer):
        result = scorer.score(_result())
        assert result.scored_at is not None
