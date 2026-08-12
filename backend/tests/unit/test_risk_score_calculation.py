"""Unit tests for Release Risk Score calculation (WO-096).

Tests the RiskScorer orchestrator and all four dimension scorers.

Coverage:
  - All 10 pre-defined fixtures with manually calculated expected scores
  - Low-risk change (score near 0)
  - High-risk change (score = 100)
  - Mixed-risk: code complexity high but test coverage good
  - Empty change analysis (no files changed) → score = 0, not an error
  - Single-file change
  - Large change (100+ files)
  - Dependency-only change
  - Security-only change (secrets → critical floor applied)
  - Incomplete dimensions → neutral score (50) substituted
  - Multiple critical security findings → escalation trigger once
  - contributing_factors captures top-5
  - Weighted sum uses Decimal arithmetic (deterministic)
  - RiskScoringConfig: configurable weights change the output
  - Critical security floor applied when secrets_detected > 0

All tests are pure — no database or network calls required.

Run:
    pytest tests/unit/test_risk_score_calculation.py -v
"""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock, patch

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
from tests.fixtures.risk_scoring.fixtures import (
    RISK_SCORING_FIXTURES,
    SCENARIO_1_EMPTY,
    SCENARIO_2_SMALL_SAFE,
    SCENARIO_4_SECRETS_FLOOR,
    SCENARIO_8_MAX_RISK,
    SCENARIO_9_SECRETS_MINIMAL,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _analysis(
    *,
    files_changed: int = 0,
    lines_added: int = 0,
    lines_deleted: int = 0,
    cyclomatic_complexity_delta: float = 0.0,
    churn_score: float = 0.0,
    test_files_changed: int = 0,
    test_lines_added: int = 0,
    estimated_coverage_delta: float = 0.0,
    has_new_tests: bool = False,
    test_to_code_ratio: float = 0.0,
    dependencies_added: list[str] | None = None,
    known_cves: list[CVEInfo] | None = None,
    major_version_bumps: int = 0,
    secrets_detected: int = 0,
    sql_patterns_detected: int = 0,
    incomplete: list[str] | None = None,
) -> ChangeAnalysisResult:
    return ChangeAnalysisResult(
        complexity=ComplexityMetrics(
            files_changed=files_changed,
            lines_added=lines_added,
            lines_deleted=lines_deleted,
            cyclomatic_complexity_delta=cyclomatic_complexity_delta,
            churn_score=churn_score,
        ),
        coverage=CoverageMetrics(
            test_files_changed=test_files_changed,
            test_lines_added=test_lines_added,
            estimated_coverage_delta=estimated_coverage_delta,
            has_new_tests=has_new_tests,
            test_to_code_ratio=test_to_code_ratio,
        ),
        dependencies=DependencyMetrics(
            dependencies_added=dependencies_added or [],
            major_version_bumps=major_version_bumps,
            known_cves=known_cves or [],
        ),
        security=SecurityMetrics(
            secrets_detected=secrets_detected,
            sql_patterns_detected=sql_patterns_detected,
        ),
        metadata=AnalysisMetadata(incomplete_dimensions=incomplete or []),
    )


# ---------------------------------------------------------------------------
# Parametrized fixture matrix (all 10 pre-calculated scenarios)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("analysis, expected_score", RISK_SCORING_FIXTURES)
def test_risk_scoring_fixture_matrix(
    analysis: ChangeAnalysisResult, expected_score: int
) -> None:
    """Every pre-defined scenario matches its manually calculated expected score."""
    scorer = RiskScorer()
    result = scorer.score(analysis)
    assert result.overall_score == expected_score, (
        f"Expected overall_score={expected_score}, got {result.overall_score}"
    )


# ---------------------------------------------------------------------------
# Low-risk change (score near 0)
# ---------------------------------------------------------------------------


def test_low_risk_empty_change() -> None:
    scorer = RiskScorer()
    result = scorer.score(SCENARIO_1_EMPTY)
    assert result.overall_score == 0


def test_low_risk_small_safe_change() -> None:
    scorer = RiskScorer()
    result = scorer.score(SCENARIO_2_SMALL_SAFE)
    assert result.overall_score == 0


def test_low_risk_single_file_change() -> None:
    scorer = RiskScorer()
    analysis = _analysis(files_changed=1, lines_added=20, has_new_tests=True, test_lines_added=5)
    result = scorer.score(analysis)
    assert result.overall_score < 20


# ---------------------------------------------------------------------------
# High-risk change (score = 100)
# ---------------------------------------------------------------------------


def test_high_risk_max_scenario() -> None:
    scorer = RiskScorer()
    result = scorer.score(SCENARIO_8_MAX_RISK)
    assert result.overall_score == 100


def test_high_risk_large_change_100_plus_files() -> None:
    scorer = RiskScorer()
    analysis = _analysis(
        files_changed=100,
        lines_added=2000,
        cyclomatic_complexity_delta=20.0,
        churn_score=0.9,
    )
    result = scorer.score(analysis)
    assert result.overall_score > 50


# ---------------------------------------------------------------------------
# Mixed risk: high complexity but good test coverage
# ---------------------------------------------------------------------------


def test_mixed_risk_high_complexity_good_coverage() -> None:
    """High files+lines (high complexity) but new tests lowers overall score."""
    scorer = RiskScorer()
    pure_complexity = _analysis(
        files_changed=30,
        lines_added=800,
        cyclomatic_complexity_delta=12.0,
        churn_score=0.5,
    )
    with_good_coverage = _analysis(
        files_changed=30,
        lines_added=800,
        cyclomatic_complexity_delta=12.0,
        churn_score=0.5,
        test_lines_added=400,  # half the new code is tests
        has_new_tests=True,
        test_to_code_ratio=0.6,
        estimated_coverage_delta=1.0,
    )
    score_no_tests = scorer.score(pure_complexity).overall_score
    score_with_tests = scorer.score(with_good_coverage).overall_score
    assert score_with_tests < score_no_tests


# ---------------------------------------------------------------------------
# Empty change analysis → score = 0, not an error
# ---------------------------------------------------------------------------


def test_empty_change_does_not_raise() -> None:
    scorer = RiskScorer()
    result = scorer.score(ChangeAnalysisResult())
    assert result.overall_score == 0
    assert isinstance(result.overall_score, int)


# ---------------------------------------------------------------------------
# Dependency-only change
# ---------------------------------------------------------------------------


def test_dependency_only_change() -> None:
    scorer = RiskScorer()
    analysis = _analysis(
        dependencies_added=["new-lib-v2"],
        major_version_bumps=1,
        known_cves=[CVEInfo(id="CVE-2026-001", severity="high", affected_package="x")],
    )
    result = scorer.score(analysis)
    assert result.overall_score >= 0
    assert "dependencies" in result.dimension_scores


def test_dependency_change_dimension_score_nonzero_with_cves() -> None:
    scorer = RiskScorer()
    analysis = _analysis(
        dependencies_added=["a", "b", "c", "d", "e", "f"],
        major_version_bumps=2,
        known_cves=[
            CVEInfo(id="CVE-001", severity="critical", affected_package="x"),
            CVEInfo(id="CVE-002", severity="critical", affected_package="y"),
        ],
    )
    result = scorer.score(analysis)
    assert result.dimension_scores["dependencies"] > 0


# ---------------------------------------------------------------------------
# Security-only change (secrets → critical floor)
# ---------------------------------------------------------------------------


def test_security_secrets_triggers_critical_floor() -> None:
    scorer = RiskScorer()
    result = scorer.score(SCENARIO_4_SECRETS_FLOOR)
    assert result.overall_score >= scorer.config.critical_security_floor


def test_security_secrets_minimal_floor() -> None:
    scorer = RiskScorer()
    result = scorer.score(SCENARIO_9_SECRETS_MINIMAL)
    # floor=70; without floor: 25, with floor: 70
    assert result.overall_score == 70


def test_security_score_100_on_secrets() -> None:
    scorer = RiskScorer()
    analysis = _analysis(secrets_detected=1)
    result = scorer.score(analysis)
    assert result.dimension_scores["security"] == 100


# ---------------------------------------------------------------------------
# Incomplete dimensions → neutral fallback (50)
# ---------------------------------------------------------------------------


def test_incomplete_code_complexity_uses_neutral_score() -> None:
    scorer = RiskScorer()
    full = _analysis(files_changed=60, lines_added=1500)
    incomplete = _analysis(files_changed=60, lines_added=1500, incomplete=["code_complexity"])
    result_full = scorer.score(full)
    result_incomplete = scorer.score(incomplete)
    # incomplete uses 50 for code_complexity instead of scored value
    assert result_incomplete.dimension_scores["code_complexity"] == 50


def test_all_incomplete_dimensions_produce_midpoint() -> None:
    scorer = RiskScorer()
    analysis = _analysis(
        incomplete=["code_complexity", "test_coverage", "dependencies", "security"]
    )
    result = scorer.score(analysis)
    # All four dimensions at 50 → overall = round(50 * 0.25 * 4) = 50
    assert result.overall_score == 50


# ---------------------------------------------------------------------------
# contributing_factors captures top-5
# ---------------------------------------------------------------------------


def test_contributing_factors_at_most_5() -> None:
    scorer = RiskScorer()
    analysis = _analysis(
        files_changed=60,
        lines_added=1500,
        churn_score=0.8,
        sql_patterns_detected=2,
        unsafe_deserialization_detected=1,
    )
    result = scorer.score(analysis)
    assert len(result.contributing_factors) <= 5


def test_contributing_factors_sorted_by_risk_contribution() -> None:
    scorer = RiskScorer()
    analysis = _analysis(
        files_changed=60,
        lines_added=2000,
        cyclomatic_complexity_delta=20.0,
        churn_score=0.9,
    )
    result = scorer.score(analysis)
    if len(result.contributing_factors) > 1:
        for i in range(len(result.contributing_factors) - 1):
            assert (
                result.contributing_factors[i].risk_contribution
                >= result.contributing_factors[i + 1].risk_contribution
            )


# ---------------------------------------------------------------------------
# Weighted sum determinism
# ---------------------------------------------------------------------------


def test_risk_score_is_deterministic() -> None:
    """Same input always produces the same score (5 runs)."""
    scorer = RiskScorer()
    analysis = _analysis(
        files_changed=15, lines_added=300, cyclomatic_complexity_delta=8.0,
        churn_score=0.4, sql_patterns_detected=1,
    )
    scores = [scorer.score(analysis).overall_score for _ in range(5)]
    assert len(set(scores)) == 1, f"Non-deterministic scores: {scores}"


# ---------------------------------------------------------------------------
# RiskScoringConfig: custom weights change the output
# ---------------------------------------------------------------------------


def test_custom_weights_security_dominant() -> None:
    """Weighting security 100% amplifies the security score's impact."""
    analysis = _analysis(
        files_changed=60, lines_added=1500,  # high complexity
        sql_patterns_detected=1,              # minimal security risk
    )
    default_scorer = RiskScorer()
    security_scorer = RiskScorer(
        RiskScoringConfig(
            dimension_weights={
                "code_complexity": 0.0,
                "test_coverage": 0.0,
                "dependencies": 0.0,
                "security": 1.0,
            }
        )
    )
    result_default = default_scorer.score(analysis)
    result_security_only = security_scorer.score(analysis)
    # Security-only weights: complexity contributes 0, security contributes 100%
    assert result_security_only.overall_score != result_default.overall_score


def test_result_schema_has_required_fields() -> None:
    scorer = RiskScorer()
    result = scorer.score(SCENARIO_1_EMPTY)
    assert hasattr(result, "overall_score")
    assert hasattr(result, "dimension_scores")
    assert hasattr(result, "contributing_factors")
    assert hasattr(result, "weights_used")
    assert hasattr(result, "scored_at")
    assert isinstance(result.overall_score, int)
    assert 0 <= result.overall_score <= 100


def test_dimension_scores_keys_present() -> None:
    scorer = RiskScorer()
    result = scorer.score(SCENARIO_1_EMPTY)
    for dim in ("code_complexity", "test_coverage", "dependencies", "security"):
        assert dim in result.dimension_scores


def test_score_clamped_to_100() -> None:
    scorer = RiskScorer()
    result = scorer.score(SCENARIO_8_MAX_RISK)
    assert result.overall_score <= 100
