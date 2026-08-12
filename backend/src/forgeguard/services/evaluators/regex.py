"""Regex-based rule evaluators with LRU-cached pattern compilation (WO-038).

Patterns are compiled once and cached up to 500 entries via functools.lru_cache.
Malformed regex patterns are caught at evaluation time and return ERROR status
rather than propagating an unhandled exception.
"""

from __future__ import annotations

import re
from functools import lru_cache
from typing import Any

from forgeguard.services.domain.evaluation import EvaluationStatus, RuleEvaluationResult
from forgeguard.services.evaluators import RuleEvaluator
from forgeguard.services.evaluators.threshold import _make_result


@lru_cache(maxsize=500)
def compile_pattern(pattern: str) -> re.Pattern[str]:
    """Compile and cache a regex pattern (raises re.error on invalid input)."""
    return re.compile(pattern)


class RegexMatchEvaluator(RuleEvaluator):
    """Passes when the input string MATCHES the compiled regex pattern."""

    async def evaluate(self, rule: Any, input_data: dict[str, Any]) -> RuleEvaluationResult:
        data_key = rule.threshold_config.get("data_key")
        pattern_str = rule.threshold_config.get("pattern")

        if data_key is None or data_key not in input_data:
            return _make_result(
                rule,
                EvaluationStatus.INCONCLUSIVE,
                None,
                pattern_str,
                {"reason": "missing_data_key", "data_key": data_key},
            )

        actual = str(input_data[data_key])

        try:
            compiled = compile_pattern(pattern_str)
        except re.error as exc:
            return _make_result(
                rule,
                EvaluationStatus.ERROR,
                actual,
                pattern_str,
                {"reason": "invalid_regex", "pattern": pattern_str, "error": str(exc)},
            )

        matched = bool(compiled.search(actual))
        return _make_result(
            rule,
            EvaluationStatus.PASS if matched else EvaluationStatus.FAIL,
            actual,
            pattern_str,
            {"operator": "regex_match", "data_key": data_key, "matched": matched},
        )


class RegexNoMatchEvaluator(RuleEvaluator):
    """Passes when the input string does NOT match the compiled regex pattern."""

    async def evaluate(self, rule: Any, input_data: dict[str, Any]) -> RuleEvaluationResult:
        data_key = rule.threshold_config.get("data_key")
        pattern_str = rule.threshold_config.get("pattern")

        if data_key is None or data_key not in input_data:
            return _make_result(
                rule,
                EvaluationStatus.INCONCLUSIVE,
                None,
                pattern_str,
                {"reason": "missing_data_key", "data_key": data_key},
            )

        actual = str(input_data[data_key])

        try:
            compiled = compile_pattern(pattern_str)
        except re.error as exc:
            return _make_result(
                rule,
                EvaluationStatus.ERROR,
                actual,
                pattern_str,
                {"reason": "invalid_regex", "pattern": pattern_str, "error": str(exc)},
            )

        matched = bool(compiled.search(actual))
        passed = not matched
        return _make_result(
            rule,
            EvaluationStatus.PASS if passed else EvaluationStatus.FAIL,
            actual,
            pattern_str,
            {"operator": "regex_no_match", "data_key": data_key, "matched": matched},
        )
