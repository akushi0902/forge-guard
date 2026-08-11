"""DependencyScorer — maps DependencyMetrics to a 0-100 risk score.

Scoring components:
  CVE contributions (capped at 100):
    critical → +30, high → +20, medium → +10, low → +5
  Major version bumps: min(30, count * 10)
  New dependencies:    > 10 → +20, > 5 → +10, else → 0

All three are summed and capped at 100.
"""

from __future__ import annotations

from forgeguard.services.release_guardian.models import ContributingFactor, DependencyMetrics

_DIM = "dependencies"

_CVE_SEVERITY_SCORES: dict[str, float] = {
    "critical": 30.0,
    "high": 20.0,
    "medium": 10.0,
    "low": 5.0,
}


class DependencyScorer:
    """Maps DependencyMetrics to a risk score in [0, 100].

    All calculations are pure and deterministic — no I/O, no randomness.
    The CVE lookup was already performed by the DependencyAnalyzer; this
    scorer only reads the pre-computed metrics.
    """

    def score(
        self, metrics: DependencyMetrics
    ) -> tuple[int, list[ContributingFactor]]:
        """Compute the dependencies risk score.

        Returns:
            (score, factors) where score ∈ [0, 100].
        """
        factors: list[ContributingFactor] = []
        total = 0.0

        # Component 1: CVE contributions (individual contributions, capped to 100)
        cve_raw = sum(
            _CVE_SEVERITY_SCORES.get(cve.severity.lower(), 0.0)
            for cve in metrics.known_cves
        )
        cve_contrib = min(100.0, cve_raw)
        factors.append(ContributingFactor(
            metric_name="known_cves",
            actual_value=float(len(metrics.known_cves)),
            threshold=1.0,
            risk_contribution=cve_contrib,
            dimension=_DIM,
        ))
        total += cve_contrib

        # Component 2: major version bumps (capped at 30)
        major_raw = float(metrics.major_version_bumps) * 10.0
        major_contrib = min(30.0, major_raw)
        factors.append(ContributingFactor(
            metric_name="major_version_bumps",
            actual_value=float(metrics.major_version_bumps),
            threshold=1.0,
            risk_contribution=major_contrib,
            dimension=_DIM,
        ))
        total += major_contrib

        # Component 3: number of new dependencies
        num_added = len(metrics.dependencies_added)
        if num_added > 10:
            new_deps_contrib = 20.0
            new_deps_threshold = 10.0
        elif num_added > 5:
            new_deps_contrib = 10.0
            new_deps_threshold = 5.0
        else:
            new_deps_contrib = 0.0
            new_deps_threshold = 5.0
        factors.append(ContributingFactor(
            metric_name="dependencies_added",
            actual_value=float(num_added),
            threshold=new_deps_threshold,
            risk_contribution=new_deps_contrib,
            dimension=_DIM,
        ))
        total += new_deps_contrib

        return min(100, round(total)), factors
