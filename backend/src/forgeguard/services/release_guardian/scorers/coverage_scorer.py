"""CoverageScorer — maps CoverageMetrics to a 0-100 risk score.

Lower test coverage or code added without tests increases risk.

Scoring components:
  coverage_delta:    >= 0 → 0; >= -1.0 → 20; >= -2.0 → 40; < -2.0 → 60
  no_new_tests:      code_lines_added > 10 and not has_new_tests → +30
  test_to_code_ratio (only when code was added):
                     >= 0.5 → 0; >= 0.2 → 15; >= 0.1 → 30; < 0.1 → 45

All three are summed and capped at 100.

Note: code_lines_added is passed separately because ComplexityMetrics.lines_added
includes test files. Callers should pass lines_added minus test_lines_added.
"""

from __future__ import annotations

from forgeguard.services.release_guardian.models import ContributingFactor, CoverageMetrics

_DIM = "test_coverage"


class CoverageScorer:
    """Maps CoverageMetrics to a risk score in [0, 100].

    All calculations are pure and deterministic — no I/O, no randomness.
    """

    def score(
        self,
        metrics: CoverageMetrics,
        code_lines_added: int = 0,
    ) -> tuple[int, list[ContributingFactor]]:
        """Compute the test_coverage risk score.

        Args:
            metrics:          Coverage metrics from the CoverageAnalyzer.
            code_lines_added: Non-test code lines added (ComplexityMetrics.lines_added
                              minus CoverageMetrics.test_lines_added).

        Returns:
            (score, factors) where score ∈ [0, 100].
        """
        factors: list[ContributingFactor] = []
        total = 0.0

        # Component 1: coverage delta
        delta = metrics.estimated_coverage_delta
        if delta >= 0.0:
            delta_contrib = 0.0
            delta_threshold = 0.0
        elif delta >= -1.0:
            delta_contrib = 20.0
            delta_threshold = -1.0
        elif delta >= -2.0:
            delta_contrib = 40.0
            delta_threshold = -2.0
        else:
            delta_contrib = 60.0
            delta_threshold = -2.0
        factors.append(ContributingFactor(
            metric_name="estimated_coverage_delta",
            actual_value=float(delta),
            threshold=delta_threshold,
            risk_contribution=delta_contrib,
            dimension=_DIM,
        ))
        total += delta_contrib

        # Component 2: no new tests added when code was added
        no_tests_contrib = 0.0
        if code_lines_added > 10 and not metrics.has_new_tests:
            no_tests_contrib = 30.0
        factors.append(ContributingFactor(
            metric_name="no_new_tests_with_code",
            actual_value=float(code_lines_added),
            threshold=10.0,
            risk_contribution=no_tests_contrib,
            dimension=_DIM,
        ))
        total += no_tests_contrib

        # Component 3: test-to-code ratio (only meaningful when code was added)
        if code_lines_added > 0:
            ratio = metrics.test_to_code_ratio
            if ratio >= 0.5:
                ratio_contrib = 0.0
                ratio_threshold = 0.5
            elif ratio >= 0.2:
                ratio_contrib = 15.0
                ratio_threshold = 0.2
            elif ratio >= 0.1:
                ratio_contrib = 30.0
                ratio_threshold = 0.1
            else:
                ratio_contrib = 45.0
                ratio_threshold = 0.1
        else:
            ratio_contrib = 0.0
            ratio_threshold = 0.5
            ratio = metrics.test_to_code_ratio

        factors.append(ContributingFactor(
            metric_name="test_to_code_ratio",
            actual_value=float(ratio),
            threshold=ratio_threshold,
            risk_contribution=ratio_contrib,
            dimension=_DIM,
        ))
        total += ratio_contrib

        return min(100, round(total)), factors
