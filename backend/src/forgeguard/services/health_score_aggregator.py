"""Health Score Aggregator — combines dimension scores into a single metric (WO-040).

Algorithm:
  1. Separate dimensions into active (has_data=True) and inactive (has_data=False).
  2. Compute effective weights: each active dimension's original weight, scaled so
     the active weights sum to 100.
       effective_w[d] = original_w[d] / sum(original_w for active dims) * 100
  3. Compute overall score:
       overall = sum(score[d] * original_w[d] for active d) / sum(original_w for active d)
  4. overall_score is None when no active dimensions exist.

All arithmetic uses Decimal with ROUND_HALF_UP to 2 decimal places.
Custom weights must sum to exactly 100; the aggregator defensively normalises
them if they don't (logs a warning).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import ROUND_HALF_UP, Decimal
from typing import Optional

import structlog

from forgeguard.services.domain.scoring import (
    DimensionScore,
    HealthScoreResult,
    VALID_DIMENSIONS,
)

logger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_WEIGHTS: dict[str, Decimal] = {
    "code_quality": Decimal("20"),
    "test_coverage": Decimal("20"),
    "security": Decimal("20"),
    "documentation": Decimal("20"),
    "operations_readiness": Decimal("20"),
}

_ZERO = Decimal("0")
_HUNDRED = Decimal("100")
_TWO_DP = Decimal("0.01")
_WEIGHT_TOLERANCE = Decimal("0.01")


def _quantize(value: Decimal) -> Decimal:
    return value.quantize(_TWO_DP, rounding=ROUND_HALF_UP)


class HealthScoreAggregator:
    """Pure computation service — no I/O during aggregation.

    Inject a ScoreRepository to persist results after calling aggregate().

    Example::

        aggregator = HealthScoreAggregator()
        result = aggregator.aggregate(
            dimension_scores=dimension_scores,
            weights=None,          # use default equal weights
            assessment_id=assessment_id,
            service_id=service_id,
        )
        await score_repo.save_health_score(result, assessment_id, service_id)
    """

    def aggregate(
        self,
        dimension_scores: dict[str, DimensionScore],
        weights: Optional[dict[str, Decimal]],
        assessment_id: uuid.UUID,
        service_id: uuid.UUID,
    ) -> HealthScoreResult:
        """Aggregate dimension scores into a single Health Score.

        Args:
            dimension_scores: Output of DimensionScoreCalculator.calculate_dimension_scores.
            weights:          Custom weight map (values must sum to ~100).  Pass
                              None to use the default equal weights (20% each).
            assessment_id:    UUID of the parent assessment record.
            service_id:       UUID of the service being scored.

        Returns:
            HealthScoreResult with overall_score, redistributed weights_used,
            and full dimension breakdown.
        """
        resolved_weights = self._resolve_weights(weights, dimension_scores)

        active: dict[str, DimensionScore] = {
            d: s for d, s in dimension_scores.items()
            if s.has_data and s.score is not None
        }
        inactive_count = len(dimension_scores) - len(active)

        total_active_weight = sum(
            resolved_weights.get(d, _ZERO) for d in active
        )

        if total_active_weight <= _ZERO or not active:
            overall_score: Optional[Decimal] = None
            weights_used = {d: _ZERO for d in dimension_scores}
        else:
            # Weighted average of active dimension scores
            weighted_sum = sum(
                active[d].score * resolved_weights.get(d, _ZERO)  # type: ignore[operator]
                for d in active
            )
            overall_score = _quantize(weighted_sum / total_active_weight)

            # Effective weight each active dimension contributed (normalised to 100)
            weights_used = {}
            for d in dimension_scores:
                if d in active:
                    weights_used[d] = _quantize(
                        resolved_weights.get(d, _ZERO) / total_active_weight * _HUNDRED
                    )
                else:
                    weights_used[d] = _ZERO

        return HealthScoreResult(
            assessment_id=assessment_id,
            service_id=service_id,
            overall_score=overall_score,
            dimension_scores=dimension_scores,
            weights_used=weights_used,
            dimensions_with_data=len(active),
            dimensions_without_data=inactive_count,
            calculated_at=datetime.now(timezone.utc),
        )

    def _resolve_weights(
        self,
        weights: Optional[dict[str, Decimal]],
        dimension_scores: dict[str, DimensionScore],
    ) -> dict[str, Decimal]:
        """Return the effective weight map to use for this aggregation.

        Falls back to DEFAULT_WEIGHTS for any dimension not in the supplied map.
        Defensively normalises if supplied weights do not sum to 100.
        """
        if weights is None:
            base = dict(DEFAULT_WEIGHTS)
        else:
            base = {d: Decimal(str(w)) for d, w in weights.items()}
            # Fill missing dimensions with their default weights
            for d in VALID_DIMENSIONS:
                if d not in base:
                    base[d] = DEFAULT_WEIGHTS.get(d, _ZERO)
            self._validate_weights(base)

        # Ensure all dimensions in dimension_scores have a weight entry
        for d in dimension_scores:
            if d not in base:
                base[d] = _ZERO

        return base

    @staticmethod
    def _validate_weights(weights: dict[str, Decimal]) -> None:
        """Log a warning if weights do not sum to 100; normalise defensively."""
        total = sum(weights.values())
        if abs(total - _HUNDRED) > _WEIGHT_TOLERANCE:
            logger.warning(
                "health_score_aggregator.weights_do_not_sum_to_100",
                total=str(total),
            )
