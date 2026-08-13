"""Rule evaluation engine with strategy pattern and per-rule timeout (WO-038).

Accepts a list of PolicyRule objects (pre-loaded) and a flat input_data dict,
returns one RuleEvaluationResult per rule.  Rules exceeding the 100ms latency
budget are terminated and returned as ERROR status.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any

import structlog

from forgeguard.services.domain.evaluation import EvaluationStatus, RuleEvaluationResult
from forgeguard.services.evaluators import RuleEvaluator
from forgeguard.services.evaluators.regex import RegexMatchEvaluator, RegexNoMatchEvaluator
from forgeguard.services.evaluators.threshold import (
    ThresholdEqEvaluator,
    ThresholdGteEvaluator,
    ThresholdLteEvaluator,
    _get_dimension,
)

logger = structlog.get_logger(__name__)

_RULE_TIMEOUT_SECONDS = 0.1  # 100ms per-rule latency budget

RULE_TYPE_REGISTRY: dict[str, RuleEvaluator] = {
    "threshold_gte": ThresholdGteEvaluator(),
    "threshold_lte": ThresholdLteEvaluator(),
    "threshold_eq": ThresholdEqEvaluator(),
    "regex_match": RegexMatchEvaluator(),
    "regex_no_match": RegexNoMatchEvaluator(),
}


def _error_result(rule: Any, reason: str) -> RuleEvaluationResult:
    return RuleEvaluationResult(
        rule_id=rule.id,
        rule_name=rule.name,
        dimension=_get_dimension(rule),
        severity=rule.severity,
        status=EvaluationStatus.ERROR,
        actual_value=None,
        expected_value=None,
        evidence={"reason": reason},
        evaluated_at=datetime.now(tz=timezone.utc),
    )


class RuleEvaluationEngine:
    """Pure computation engine for evaluating policy rules against service data.

    No database or network calls — all data must be pre-loaded and passed in.
    """

    async def evaluate_rules(
        self,
        rules: list[Any],
        input_data: dict[str, Any],
    ) -> list[RuleEvaluationResult]:
        """Evaluate rules against input_data, returning one result per rule.

        Rules with an unrecognised rule_type or that exceed the 100ms timeout
        are marked as ERROR rather than raising an exception.
        """
        results: list[RuleEvaluationResult] = []

        for rule in rules:
            evaluator = RULE_TYPE_REGISTRY.get(rule.rule_type)

            if evaluator is None:
                logger.warning(
                    "evaluation_engine.unknown_rule_type",
                    rule_id=str(rule.id),
                    rule_type=rule.rule_type,
                )
                results.append(_error_result(rule, f"unknown_rule_type:{rule.rule_type}"))
                continue

            try:
                result = await asyncio.wait_for(
                    evaluator.evaluate(rule, input_data),
                    timeout=_RULE_TIMEOUT_SECONDS,
                )
                results.append(result)
            except asyncio.TimeoutError:
                logger.warning(
                    "evaluation_engine.rule_timeout",
                    rule_id=str(rule.id),
                    timeout_seconds=_RULE_TIMEOUT_SECONDS,
                )
                results.append(_error_result(rule, "rule_evaluation_timeout"))
            except Exception as exc:  # noqa: BLE001
                logger.error(
                    "evaluation_engine.rule_error",
                    rule_id=str(rule.id),
                    error=str(exc),
                )
                results.append(_error_result(rule, f"unexpected_error:{exc}"))

        return results
