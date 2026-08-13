"""SecurityScorer — maps SecurityMetrics to a 0-100 risk score.

Short-circuit: any secrets_detected → score = 100 (triggers critical floor).

Other contributions:
  sql_patterns_detected:         each +25, capped at 100
  unsafe_deserialization_detected: each +30, capped at 100
  security_config_changes:       each +5, capped at 20

All non-secrets contributions are summed and capped at 100.
The is_critical flag is True only when secrets_detected > 0.
"""

from __future__ import annotations

from forgeguard.services.release_guardian.models import ContributingFactor, SecurityMetrics

_DIM = "security"


class SecurityScorer:
    """Maps SecurityMetrics to a risk score in [0, 100].

    All calculations are pure and deterministic — no I/O, no randomness.
    """

    def score(
        self, metrics: SecurityMetrics
    ) -> tuple[int, list[ContributingFactor], bool]:
        """Compute the security risk score.

        Returns:
            (score, factors, is_critical) where:
              score       ∈ [0, 100]
              factors     list of ContributingFactor
              is_critical True if secrets were detected (triggers global floor)
        """
        factors: list[ContributingFactor] = []

        # Secrets detected: automatic maximum — short-circuit everything else.
        if metrics.secrets_detected > 0:
            factors.append(ContributingFactor(
                metric_name="secrets_detected",
                actual_value=float(metrics.secrets_detected),
                threshold=1.0,
                risk_contribution=100.0,
                dimension=_DIM,
            ))
            return 100, factors, True

        total = 0.0

        # SQL injection patterns
        sql_contrib = min(100.0, float(metrics.sql_patterns_detected) * 25.0)
        factors.append(ContributingFactor(
            metric_name="sql_patterns_detected",
            actual_value=float(metrics.sql_patterns_detected),
            threshold=1.0,
            risk_contribution=sql_contrib,
            dimension=_DIM,
        ))
        total += sql_contrib

        # Unsafe deserialization patterns
        deser_contrib = min(100.0, float(metrics.unsafe_deserialization_detected) * 30.0)
        factors.append(ContributingFactor(
            metric_name="unsafe_deserialization_detected",
            actual_value=float(metrics.unsafe_deserialization_detected),
            threshold=1.0,
            risk_contribution=deser_contrib,
            dimension=_DIM,
        ))
        total += deser_contrib

        # Security config changes
        config_contrib = min(20.0, float(len(metrics.security_config_changes)) * 5.0)
        factors.append(ContributingFactor(
            metric_name="security_config_changes",
            actual_value=float(len(metrics.security_config_changes)),
            threshold=1.0,
            risk_contribution=config_contrib,
            dimension=_DIM,
        ))
        total += config_contrib

        return min(100, round(total)), factors, False
