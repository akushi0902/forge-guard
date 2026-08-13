"""Dimension score calculator using weighted pass-rate algorithm (WO-039).

Aggregates RuleEvaluationResult objects into per-dimension scores (0-100)
using Decimal arithmetic with ROUND_HALF_UP.

Algorithm per dimension:
  weighted_pass  = sum(weight for PASS rules)
  weighted_total = sum(weight for PASS + FAIL + ERROR rules)
  score          = (weighted_pass / weighted_total) * 100  [or None if total == 0]

INCONCLUSIVE rules are excluded from the denominator — they do not penalise
the score — but are tracked in inconclusive_rules.
ERROR rules are treated as failures (count toward weighted_total as losses).
"""

from __future__ import annotations

from collections import defaultdict
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

import structlog

from forgeguard.services.domain.evaluation import EvaluationStatus, RuleEvaluationResult
from forgeguard.services.domain.scoring import (
    ContributingFactor,
    DimensionScore,
    VALID_DIMENSIONS,
)

logger = structlog.get_logger(__name__)

_ZERO = Decimal("0")
_HUNDRED = Decimal("100")
_TWO_DP = Decimal("0.01")


def _quantize(value: Decimal) -> Decimal:
    return value.quantize(_TWO_DP, rounding=ROUND_HALF_UP)


class DimensionScoreCalculator:
    """Pure computation service — no I/O, no side effects."""

    def calculate_dimension_scores(
        self,
        results: list[RuleEvaluationResult],
    ) -> dict[str, DimensionScore]:
        """Aggregate rule evaluation results into per-dimension scores.

        Returns a dict keyed by dimension string.  All five known dimensions
        are always present — dimensions with no results get score=None.
        Unknown dimensions in results are still scored but trigger a warning.
        """
        by_dim: dict[str, list[RuleEvaluationResult]] = defaultdict(list)

        for r in results:
            if r.dimension not in VALID_DIMENSIONS:
                logger.warning(
                    "dimension_scorer.unknown_dimension",
                    dimension=r.dimension,
                    rule_id=str(r.rule_id),
                )
            by_dim[r.dimension].append(r)

        output: dict[str, DimensionScore] = {}

        for dim, dim_results in by_dim.items():
            output[dim] = self._score_dimension(dim, dim_results)

        for dim in VALID_DIMENSIONS:
            if dim not in output:
                output[dim] = DimensionScore(
                    dimension=dim,
                    score=None,
                    total_rules=0,
                    passed_rules=0,
                    failed_rules=0,
                    inconclusive_rules=0,
                    error_rules=0,
                    has_data=False,
                    contributing_factors=[],
                )

        return output

    def _score_dimension(
        self,
        dimension: str,
        results: list[RuleEvaluationResult],
    ) -> DimensionScore:
        passed = [r for r in results if r.status == EvaluationStatus.PASS]
        failed = [r for r in results if r.status == EvaluationStatus.FAIL]
        inconcl = [r for r in results if r.status == EvaluationStatus.INCONCLUSIVE]
        errors = [r for r in results if r.status == EvaluationStatus.ERROR]

        evaluated = passed + failed + errors

        weighted_pass = self._weight_sum(passed)
        weighted_total = self._weight_sum(evaluated)

        if weighted_total <= _ZERO:
            score = None
            has_data = False
        else:
            score = _quantize(weighted_pass / weighted_total * _HUNDRED)
            has_data = True

        factors = [
            self._make_factor(r, weighted_total)
            for r in results
        ]

        return DimensionScore(
            dimension=dimension,
            score=score,
            total_rules=len(results),
            passed_rules=len(passed),
            failed_rules=len(failed),
            inconclusive_rules=len(inconcl),
            error_rules=len(errors),
            has_data=has_data,
            contributing_factors=factors,
        )

    @staticmethod
    def _weight_sum(results: list[RuleEvaluationResult]) -> Decimal:
        total = _ZERO
        for r in results:
            w = r.weight if isinstance(r.weight, Decimal) else Decimal(str(r.weight))
            if w < _ZERO:
                logger.error(
                    "dimension_scorer.negative_weight",
                    rule_id=str(r.rule_id),
                    weight=str(w),
                )
                w = _ZERO
            total += w
        return total

    @staticmethod
    def _make_factor(
        r: RuleEvaluationResult,
        weighted_total: Decimal,
    ) -> ContributingFactor:
        w = r.weight if isinstance(r.weight, Decimal) else Decimal(str(r.weight))
        if w < _ZERO:
            w = _ZERO

        if r.status == EvaluationStatus.INCONCLUSIVE or weighted_total <= _ZERO:
            impact = _ZERO
        elif r.status == EvaluationStatus.PASS:
            impact = _quantize(w / weighted_total * _HUNDRED)
        else:
            impact = _quantize(-(w / weighted_total * _HUNDRED))

        return ContributingFactor(
            rule_id=r.rule_id,
            rule_name=r.rule_name,
            status=r.status,
            weight=w,
            score_impact=impact,
        )
