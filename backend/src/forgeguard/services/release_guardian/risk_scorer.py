"""RiskScorer — deterministic Release Risk Score orchestrator (WO-046).

Accepts a ChangeAnalysisResult and returns a RiskScoreResult (0-100, lower is
safer) by:

  1. Running four dimension scorers (pure functions, no I/O).
  2. Computing the weighted sum with Decimal arithmetic to avoid float drift.
  3. Clamping the result to [0, 100] and rounding to integer.
  4. Enforcing the critical security floor when secrets are detected.
  5. Collecting the top-5 contributing factors.

The algorithm is 100% deterministic: identical inputs always produce identical
outputs regardless of Python version or platform.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

import structlog

from forgeguard.services.release_guardian.models import (
    ChangeAnalysisResult,
    ContributingFactor,
    RiskScoreResult,
    RiskScoringConfig,
)
from forgeguard.services.release_guardian.scorers.complexity_scorer import ComplexityScorer
from forgeguard.services.release_guardian.scorers.coverage_scorer import CoverageScorer
from forgeguard.services.release_guardian.scorers.dependency_scorer import DependencyScorer
from forgeguard.services.release_guardian.scorers.security_scorer import SecurityScorer

logger = structlog.get_logger(__name__)

#: Neutral score used for incomplete dimensions (neither safe nor risky).
_INCOMPLETE_DIMENSION_SCORE = 50

#: Top N contributing factors returned in the result.
_TOP_FACTORS_COUNT = 5


class RiskScorer:
    """Orchestrates all dimension scorers into a single Release Risk Score.

    Args:
        config: Optional RiskScoringConfig. Defaults to equal weights (0.25 each).

    Example::

        scorer = RiskScorer()
        result = scorer.score(change_analysis_result)
        print(result.overall_score)  # e.g. 42
    """

    def __init__(self, config: RiskScoringConfig | None = None) -> None:
        self.config = config or RiskScoringConfig()
        self._complexity_scorer = ComplexityScorer()
        self._coverage_scorer = CoverageScorer()
        self._dependency_scorer = DependencyScorer()
        self._security_scorer = SecurityScorer()

    def score(self, analysis: ChangeAnalysisResult) -> RiskScoreResult:
        """Transform a ChangeAnalysisResult into a RiskScoreResult.

        The operation is synchronous, CPU-only, and completes in under 50ms
        for any input size.

        Args:
            analysis: The structured output of the ChangeAnalyzer pipeline.

        Returns:
            RiskScoreResult with overall_score, dimension_scores, top-5
            contributing_factors, weights_used, and scored_at timestamp.
        """
        incomplete = set(analysis.metadata.incomplete_dimensions)

        # --- Run all four dimension scorers ---
        if "code_complexity" in incomplete:
            complexity_score = _INCOMPLETE_DIMENSION_SCORE
            complexity_factors: list[ContributingFactor] = []
        else:
            complexity_score, complexity_factors = self._complexity_scorer.score(
                analysis.complexity
            )

        # code_lines_added excludes test files to correctly evaluate "no tests added"
        code_lines_added = max(
            0,
            analysis.complexity.lines_added - analysis.coverage.test_lines_added,
        )
        if "test_coverage" in incomplete:
            coverage_score = _INCOMPLETE_DIMENSION_SCORE
            coverage_factors: list[ContributingFactor] = []
        else:
            coverage_score, coverage_factors = self._coverage_scorer.score(
                analysis.coverage, code_lines_added=code_lines_added
            )

        if "dependencies" in incomplete:
            dependency_score = _INCOMPLETE_DIMENSION_SCORE
            dependency_factors: list[ContributingFactor] = []
        else:
            dependency_score, dependency_factors = self._dependency_scorer.score(
                analysis.dependencies
            )

        if "security" in incomplete:
            security_score = _INCOMPLETE_DIMENSION_SCORE
            security_factors: list[ContributingFactor] = []
            is_critical = False
        else:
            security_score, security_factors, is_critical = self._security_scorer.score(
                analysis.security
            )

        dimension_scores = {
            "code_complexity": complexity_score,
            "test_coverage": coverage_score,
            "dependencies": dependency_score,
            "security": security_score,
        }

        # --- Weighted sum via Decimal arithmetic (determinism guarantee) ---
        weights = self.config.dimension_weights
        weighted_sum = Decimal("0")
        for dim, raw_score in dimension_scores.items():
            w = Decimal(str(weights.get(dim, 0.0)))
            weighted_sum += Decimal(str(raw_score)) * w

        overall_int = int(
            weighted_sum.quantize(Decimal("1"), rounding=ROUND_HALF_UP)
        )
        overall_int = max(0, min(100, overall_int))

        # --- Critical security floor ---
        if is_critical:
            floor = self.config.critical_security_floor
            if overall_int < floor:
                logger.info(
                    "risk_scorer.floor_applied",
                    pre_floor=overall_int,
                    floor=floor,
                )
            overall_int = max(overall_int, floor)

        # --- Top-5 contributing factors (by risk_contribution descending) ---
        all_factors = (
            complexity_factors
            + coverage_factors
            + dependency_factors
            + security_factors
        )
        top_factors = sorted(
            all_factors, key=lambda f: f.risk_contribution, reverse=True
        )[:_TOP_FACTORS_COUNT]

        logger.debug(
            "risk_scorer.scored",
            overall_score=overall_int,
            dimension_scores=dimension_scores,
            incomplete_dimensions=list(incomplete),
            is_critical=is_critical,
        )

        return RiskScoreResult(
            overall_score=overall_int,
            dimension_scores=dimension_scores,
            contributing_factors=top_factors,
            weights_used=dict(weights),
        )
