"""Threshold-based rule evaluators: gte, lte, eq (WO-038).

All comparisons use Python Decimal for deterministic results without
floating-point drift.  The data_key in threshold_config names the key to
look up in input_data; missing keys yield INCONCLUSIVE rather than ERROR.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any

from forgeguard.services.domain.evaluation import EvaluationStatus, RuleEvaluationResult
from forgeguard.services.evaluators import RuleEvaluator


def _get_dimension(rule: Any) -> str:
    try:
        return rule.policy.dimension
    except AttributeError:
        return "unknown"


def _make_result(
    rule: Any,
    status: EvaluationStatus,
    actual: Any,
    expected: Any,
    evidence: dict[str, Any],
) -> RuleEvaluationResult:
    return RuleEvaluationResult(
        rule_id=rule.id,
        rule_name=rule.name,
        dimension=_get_dimension(rule),
        severity=rule.severity,
        status=status,
        actual_value=actual,
        expected_value=expected,
        evidence=evidence,
        evaluated_at=datetime.now(tz=timezone.utc),
    )


def _to_decimal(value: Any) -> Decimal:
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError(f"Cannot convert {value!r} to Decimal: {exc}") from exc


def _check_missing(
    rule: Any,
    data_key: str | None,
    threshold_raw: Any,
    input_data: dict[str, Any],
) -> RuleEvaluationResult | None:
    """Return INCONCLUSIVE result if data_key is absent, else None."""
    if data_key is None or data_key not in input_data:
        return _make_result(
            rule,
            EvaluationStatus.INCONCLUSIVE,
            None,
            threshold_raw,
            {"reason": "missing_data_key", "data_key": data_key},
        )
    return None


class ThresholdGteEvaluator(RuleEvaluator):
    """Passes when actual_value >= threshold_value."""

    async def evaluate(self, rule: Any, input_data: dict[str, Any]) -> RuleEvaluationResult:
        data_key = rule.threshold_config.get("data_key")
        threshold_raw = rule.threshold_config.get("numeric_value")

        inconclusive = _check_missing(rule, data_key, threshold_raw, input_data)
        if inconclusive is not None:
            return inconclusive

        try:
            actual = _to_decimal(input_data[data_key])
            threshold = _to_decimal(threshold_raw)
        except ValueError as exc:
            return _make_result(
                rule,
                EvaluationStatus.ERROR,
                input_data.get(data_key),
                threshold_raw,
                {"reason": "type_coercion_error", "error": str(exc)},
            )

        passed = actual >= threshold
        return _make_result(
            rule,
            EvaluationStatus.PASS if passed else EvaluationStatus.FAIL,
            actual,
            threshold,
            {"operator": "gte", "data_key": data_key, "passed": passed},
        )


class ThresholdLteEvaluator(RuleEvaluator):
    """Passes when actual_value <= threshold_value."""

    async def evaluate(self, rule: Any, input_data: dict[str, Any]) -> RuleEvaluationResult:
        data_key = rule.threshold_config.get("data_key")
        threshold_raw = rule.threshold_config.get("numeric_value")

        inconclusive = _check_missing(rule, data_key, threshold_raw, input_data)
        if inconclusive is not None:
            return inconclusive

        try:
            actual = _to_decimal(input_data[data_key])
            threshold = _to_decimal(threshold_raw)
        except ValueError as exc:
            return _make_result(
                rule,
                EvaluationStatus.ERROR,
                input_data.get(data_key),
                threshold_raw,
                {"reason": "type_coercion_error", "error": str(exc)},
            )

        passed = actual <= threshold
        return _make_result(
            rule,
            EvaluationStatus.PASS if passed else EvaluationStatus.FAIL,
            actual,
            threshold,
            {"operator": "lte", "data_key": data_key, "passed": passed},
        )


class ThresholdEqEvaluator(RuleEvaluator):
    """Passes when |actual_value - threshold_value| <= tolerance.

    Tolerance defaults to 0.001 and can be overridden via
    threshold_config['tolerance'].
    """

    async def evaluate(self, rule: Any, input_data: dict[str, Any]) -> RuleEvaluationResult:
        data_key = rule.threshold_config.get("data_key")
        threshold_raw = rule.threshold_config.get("numeric_value")
        tolerance_raw = rule.threshold_config.get("tolerance", "0.001")

        inconclusive = _check_missing(rule, data_key, threshold_raw, input_data)
        if inconclusive is not None:
            return inconclusive

        try:
            actual = _to_decimal(input_data[data_key])
            threshold = _to_decimal(threshold_raw)
            tolerance = _to_decimal(tolerance_raw)
        except ValueError as exc:
            return _make_result(
                rule,
                EvaluationStatus.ERROR,
                input_data.get(data_key),
                threshold_raw,
                {"reason": "type_coercion_error", "error": str(exc)},
            )

        passed = abs(actual - threshold) <= tolerance
        return _make_result(
            rule,
            EvaluationStatus.PASS if passed else EvaluationStatus.FAIL,
            actual,
            threshold,
            {
                "operator": "eq",
                "tolerance": str(tolerance),
                "data_key": data_key,
                "passed": passed,
            },
        )
