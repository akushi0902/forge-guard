"""ComplexityScorer — maps ComplexityMetrics to a 0-100 risk score.

Threshold-based: each metric is bucketed and contributes independently.
The total is capped at 100.

Thresholds (from WO-046):
  files_changed:               [0-5): 0, [5-20): 15, [20-50): 35, [50+): 60
  lines_changed (add+del):     [0-100): 0, [100-500): 15, [500-1000): 30, [1000+): 55
  cyclomatic_complexity_delta: [0-5): 0, [5-15): 10, [15+): 20
  churn_score:                 [0-0.3): 0, [0.3-0.7): 15, [0.7+): 25
"""

from __future__ import annotations

from forgeguard.services.release_guardian.models import ComplexityMetrics, ContributingFactor

_DIM = "code_complexity"


def _bucket(value: float, thresholds: list[tuple[float, float]]) -> tuple[float, float]:
    """Return (contribution, threshold) for the first bucket where value < upper."""
    for upper, contrib in thresholds:
        if value < upper:
            return contrib, upper
    # Last bucket: value >= all bounds
    last_upper, last_contrib = thresholds[-1]
    return last_contrib, last_upper


_FILES_THRESHOLDS: list[tuple[float, float]] = [
    (5, 0),
    (20, 15),
    (50, 35),
    (float("inf"), 60),
]

_LINES_THRESHOLDS: list[tuple[float, float]] = [
    (100, 0),
    (500, 15),
    (1000, 30),
    (float("inf"), 55),
]

_CC_THRESHOLDS: list[tuple[float, float]] = [
    (5.0, 0),
    (15.0, 10),
    (float("inf"), 20),
]

_CHURN_THRESHOLDS: list[tuple[float, float]] = [
    (0.3, 0),
    (0.7, 15),
    (float("inf"), 25),
]


class ComplexityScorer:
    """Maps ComplexityMetrics to a risk score in [0, 100].

    All calculations are pure and deterministic — no I/O, no randomness.
    """

    def score(
        self, metrics: ComplexityMetrics
    ) -> tuple[int, list[ContributingFactor]]:
        """Compute the code_complexity risk score.

        Returns:
            (score, factors) where score ∈ [0, 100] and factors is the list
            of ContributingFactor objects for each metric.
        """
        factors: list[ContributingFactor] = []
        total = 0.0

        # files_changed
        contrib, threshold = _bucket(float(metrics.files_changed), _FILES_THRESHOLDS)
        factors.append(ContributingFactor(
            metric_name="files_changed",
            actual_value=float(metrics.files_changed),
            threshold=threshold,
            risk_contribution=contrib,
            dimension=_DIM,
        ))
        total += contrib

        # lines_changed = additions + deletions
        lines_changed = float(metrics.lines_added + metrics.lines_deleted)
        contrib, threshold = _bucket(lines_changed, _LINES_THRESHOLDS)
        factors.append(ContributingFactor(
            metric_name="lines_changed",
            actual_value=lines_changed,
            threshold=threshold,
            risk_contribution=contrib,
            dimension=_DIM,
        ))
        total += contrib

        # cyclomatic_complexity_delta
        contrib, threshold = _bucket(metrics.cyclomatic_complexity_delta, _CC_THRESHOLDS)
        factors.append(ContributingFactor(
            metric_name="cyclomatic_complexity_delta",
            actual_value=metrics.cyclomatic_complexity_delta,
            threshold=threshold,
            risk_contribution=contrib,
            dimension=_DIM,
        ))
        total += contrib

        # churn_score
        contrib, threshold = _bucket(metrics.churn_score, _CHURN_THRESHOLDS)
        factors.append(ContributingFactor(
            metric_name="churn_score",
            actual_value=metrics.churn_score,
            threshold=threshold,
            risk_contribution=contrib,
            dimension=_DIM,
        ))
        total += contrib

        return min(100, round(total)), factors
