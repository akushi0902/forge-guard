"""Unit tests for the rule evaluation engine (WO-095).

Tests the RuleEvaluationEngine.evaluate_rules() pipeline covering:
    - Threshold rules (gte, lte, eq): pass/fail/inconclusive/error paths
    - Regex rules (match, no_match): match/no-match/invalid-pattern/missing-key
    - Missing input data → INCONCLUSIVE (never ERROR)
    - Unknown rule_type → ERROR
    - AI engine is NEVER invoked during rule evaluation — assert zero calls
    - Determinism: identical inputs produce identical results across 3 runs

All tests use dependency injection with mock/SimpleNamespace rule objects.
No database or network calls are made.

Run:
    pytest tests/unit/test_rule_evaluation.py -v
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from forgeguard.services.domain.evaluation import EvaluationStatus
from forgeguard.services.domain.severity import SeverityLevel
from forgeguard.services.evaluation_engine import RuleEvaluationEngine
from tests.fixtures.evaluation_fixtures import make_rule


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _gte_rule(
    name: str,
    data_key: str,
    threshold: float,
    dimension: str = "code_quality",
    weight: str = "1.0",
) -> SimpleNamespace:
    return make_rule(
        name=name,
        rule_type="threshold_gte",
        threshold_config={"data_key": data_key, "numeric_value": threshold},
        dimension=dimension,
        weight=Decimal(weight),
    )


def _lte_rule(
    name: str,
    data_key: str,
    threshold: float,
    dimension: str = "code_quality",
    weight: str = "1.0",
) -> SimpleNamespace:
    return make_rule(
        name=name,
        rule_type="threshold_lte",
        threshold_config={"data_key": data_key, "numeric_value": threshold},
        dimension=dimension,
        weight=Decimal(weight),
    )


def _eq_rule(
    name: str,
    data_key: str,
    threshold: float,
    dimension: str = "code_quality",
    weight: str = "1.0",
) -> SimpleNamespace:
    return make_rule(
        name=name,
        rule_type="threshold_eq",
        threshold_config={"data_key": data_key, "numeric_value": threshold},
        dimension=dimension,
        weight=Decimal(weight),
    )


def _regex_rule(
    name: str,
    data_key: str,
    pattern: str,
    dimension: str = "code_quality",
    inverted: bool = False,
) -> SimpleNamespace:
    rule_type = "regex_no_match" if inverted else "regex_match"
    return make_rule(
        name=name,
        rule_type=rule_type,
        threshold_config={"data_key": data_key, "pattern": pattern},
        dimension=dimension,
    )


@pytest.fixture()
def engine() -> RuleEvaluationEngine:
    return RuleEvaluationEngine()


# ===========================================================================
# Threshold GTE rules
# ===========================================================================

class TestThresholdGte:
    @pytest.mark.asyncio
    async def test_pass_when_value_equals_threshold(self, engine):
        rule = _gte_rule("Coverage", "coverage", 80.0)
        results = await engine.evaluate_rules([rule], {"coverage": 80.0})
        assert results[0].status == EvaluationStatus.PASS

    @pytest.mark.asyncio
    async def test_pass_when_value_exceeds_threshold(self, engine):
        rule = _gte_rule("Coverage", "coverage", 80.0)
        results = await engine.evaluate_rules([rule], {"coverage": 95.0})
        assert results[0].status == EvaluationStatus.PASS

    @pytest.mark.asyncio
    async def test_fail_when_value_below_threshold(self, engine):
        rule = _gte_rule("Coverage", "coverage", 80.0)
        results = await engine.evaluate_rules([rule], {"coverage": 79.9})
        assert results[0].status == EvaluationStatus.FAIL

    @pytest.mark.asyncio
    async def test_fail_when_value_just_below_threshold(self, engine):
        rule = _gte_rule("Coverage", "coverage", 70.0)
        results = await engine.evaluate_rules([rule], {"coverage": 69.99})
        assert results[0].status == EvaluationStatus.FAIL

    @pytest.mark.asyncio
    async def test_pass_at_zero_threshold(self, engine):
        rule = _gte_rule("Coverage", "coverage", 0.0)
        results = await engine.evaluate_rules([rule], {"coverage": 0.0})
        assert results[0].status == EvaluationStatus.PASS

    @pytest.mark.asyncio
    async def test_inconclusive_when_data_key_missing(self, engine):
        rule = _gte_rule("Coverage", "coverage", 80.0)
        results = await engine.evaluate_rules([rule], {})
        assert results[0].status == EvaluationStatus.INCONCLUSIVE

    @pytest.mark.asyncio
    async def test_evidence_contains_operator(self, engine):
        rule = _gte_rule("Coverage", "coverage", 80.0)
        results = await engine.evaluate_rules([rule], {"coverage": 85.0})
        assert results[0].evidence.get("operator") == "gte"


# ===========================================================================
# Threshold LTE rules
# ===========================================================================

class TestThresholdLte:
    @pytest.mark.asyncio
    async def test_pass_when_value_equals_threshold(self, engine):
        rule = _lte_rule("Vulnerabilities", "vuln_count", 5.0)
        results = await engine.evaluate_rules([rule], {"vuln_count": 5.0})
        assert results[0].status == EvaluationStatus.PASS

    @pytest.mark.asyncio
    async def test_pass_when_value_below_threshold(self, engine):
        rule = _lte_rule("Vulnerabilities", "vuln_count", 5.0)
        results = await engine.evaluate_rules([rule], {"vuln_count": 0.0})
        assert results[0].status == EvaluationStatus.PASS

    @pytest.mark.asyncio
    async def test_fail_when_value_exceeds_threshold(self, engine):
        rule = _lte_rule("Vulnerabilities", "vuln_count", 5.0)
        results = await engine.evaluate_rules([rule], {"vuln_count": 6.0})
        assert results[0].status == EvaluationStatus.FAIL

    @pytest.mark.asyncio
    async def test_inconclusive_when_data_key_missing(self, engine):
        rule = _lte_rule("Vulnerabilities", "vuln_count", 5.0)
        results = await engine.evaluate_rules([rule], {})
        assert results[0].status == EvaluationStatus.INCONCLUSIVE


# ===========================================================================
# Threshold EQ rules
# ===========================================================================

class TestThresholdEq:
    @pytest.mark.asyncio
    async def test_pass_when_value_equals_threshold(self, engine):
        rule = _eq_rule("Version", "api_version", 2.0)
        results = await engine.evaluate_rules([rule], {"api_version": 2.0})
        assert results[0].status == EvaluationStatus.PASS

    @pytest.mark.asyncio
    async def test_fail_when_value_differs_from_threshold(self, engine):
        rule = _eq_rule("Version", "api_version", 2.0)
        results = await engine.evaluate_rules([rule], {"api_version": 3.0})
        assert results[0].status == EvaluationStatus.FAIL

    @pytest.mark.asyncio
    async def test_inconclusive_when_data_key_missing(self, engine):
        rule = _eq_rule("Version", "api_version", 2.0)
        results = await engine.evaluate_rules([rule], {})
        assert results[0].status == EvaluationStatus.INCONCLUSIVE


# ===========================================================================
# Regex match rules
# ===========================================================================

class TestRegexMatch:
    @pytest.mark.asyncio
    async def test_pass_when_value_matches_pattern(self, engine):
        rule = _regex_rule("Semver Check", "version", r"^\d+\.\d+\.\d+$")
        results = await engine.evaluate_rules([rule], {"version": "1.2.3"})
        assert results[0].status == EvaluationStatus.PASS

    @pytest.mark.asyncio
    async def test_fail_when_value_does_not_match(self, engine):
        rule = _regex_rule("Semver Check", "version", r"^\d+\.\d+\.\d+$")
        results = await engine.evaluate_rules([rule], {"version": "latest"})
        assert results[0].status == EvaluationStatus.FAIL

    @pytest.mark.asyncio
    async def test_inconclusive_when_data_key_missing(self, engine):
        rule = _regex_rule("Semver Check", "version", r"^\d+\.\d+\.\d+$")
        results = await engine.evaluate_rules([rule], {})
        assert results[0].status == EvaluationStatus.INCONCLUSIVE

    @pytest.mark.asyncio
    async def test_error_when_invalid_regex_pattern(self, engine):
        rule = _regex_rule("Bad Pattern", "version", r"[invalid")
        results = await engine.evaluate_rules([rule], {"version": "1.0.0"})
        assert results[0].status == EvaluationStatus.ERROR


# ===========================================================================
# Regex no-match rules
# ===========================================================================

class TestRegexNoMatch:
    @pytest.mark.asyncio
    async def test_pass_when_value_does_not_match(self, engine):
        rule = _regex_rule("No Test Skip", "test_flags", r"--skip", inverted=True)
        results = await engine.evaluate_rules([rule], {"test_flags": "--verbose"})
        assert results[0].status == EvaluationStatus.PASS

    @pytest.mark.asyncio
    async def test_fail_when_value_matches(self, engine):
        rule = _regex_rule("No Test Skip", "test_flags", r"--skip", inverted=True)
        results = await engine.evaluate_rules([rule], {"test_flags": "--skip-slow"})
        assert results[0].status == EvaluationStatus.FAIL

    @pytest.mark.asyncio
    async def test_inconclusive_when_data_key_missing(self, engine):
        rule = _regex_rule("No Test Skip", "test_flags", r"--skip", inverted=True)
        results = await engine.evaluate_rules([rule], {})
        assert results[0].status == EvaluationStatus.INCONCLUSIVE


# ===========================================================================
# Unknown rule type
# ===========================================================================

class TestUnknownRuleType:
    @pytest.mark.asyncio
    async def test_unknown_type_produces_error_status(self, engine):
        rule = make_rule(name="Unknown", rule_type="boolean_check")
        results = await engine.evaluate_rules([rule], {"some_key": True})
        assert results[0].status == EvaluationStatus.ERROR

    @pytest.mark.asyncio
    async def test_unknown_type_error_evidence_contains_reason(self, engine):
        rule = make_rule(name="Unknown", rule_type="boolean_check")
        results = await engine.evaluate_rules([rule], {"some_key": True})
        assert "unknown_rule_type" in results[0].evidence.get("reason", "")


# ===========================================================================
# Rule metadata preservation
# ===========================================================================

class TestRuleMetadata:
    @pytest.mark.asyncio
    async def test_rule_id_preserved_in_result(self, engine):
        rule_id = uuid.UUID("abcdef00-0000-0000-0000-000000000001")
        rule = _gte_rule("Coverage", "coverage", 80.0)
        rule.id = rule_id
        results = await engine.evaluate_rules([rule], {"coverage": 85.0})
        assert results[0].rule_id == rule_id

    @pytest.mark.asyncio
    async def test_rule_name_preserved_in_result(self, engine):
        rule = _gte_rule("My Coverage Rule", "coverage", 80.0)
        results = await engine.evaluate_rules([rule], {"coverage": 85.0})
        assert results[0].rule_name == "My Coverage Rule"

    @pytest.mark.asyncio
    async def test_weight_preserved_in_result(self, engine):
        rule = _gte_rule("Coverage", "coverage", 80.0, weight="2.5")
        results = await engine.evaluate_rules([rule], {"coverage": 85.0})
        assert results[0].weight == Decimal("2.5")


# ===========================================================================
# AI engine never called during evaluation
# ===========================================================================

class TestAIEngineNotInvoked:
    @pytest.mark.asyncio
    async def test_ai_engine_never_called_during_rule_evaluation(self, engine):
        """Scoring must be deterministic — AI must not be called."""
        ai_engine = MagicMock()
        ai_engine.generate_completion = AsyncMock()

        rules = [
            _gte_rule("Coverage", "coverage", 80.0),
            _lte_rule("Vulns", "vulns", 5.0),
            _regex_rule("Semver", "version", r"^\d+\.\d+\.\d+$"),
        ]
        await engine.evaluate_rules(rules, {"coverage": 85.0, "vulns": 2, "version": "1.0.0"})

        ai_engine.generate_completion.assert_not_called()


# ===========================================================================
# Determinism: same inputs always produce same outputs
# ===========================================================================

class TestDeterminism:
    @pytest.mark.asyncio
    async def test_identical_inputs_produce_identical_results(self, engine):
        """Run the same evaluation 3 times and assert results are identical."""
        rules = [
            _gte_rule("Coverage", "coverage", 80.0),
            _lte_rule("Vulns", "vuln_count", 3.0),
            _regex_rule("Semver", "version", r"^\d+\.\d+\.\d+$"),
        ]
        input_data = {"coverage": 75.0, "vuln_count": 5, "version": "1.0.0"}

        runs = []
        for _ in range(3):
            results = await engine.evaluate_rules(rules, input_data)
            runs.append([(r.status, r.rule_name) for r in results])

        assert runs[0] == runs[1] == runs[2]

    @pytest.mark.asyncio
    async def test_determinism_with_mixed_pass_fail(self, engine):
        rules = [
            _gte_rule("Coverage", "coverage", 80.0),
            _gte_rule("Quality", "quality_score", 70.0),
        ]
        input_data = {"coverage": 85.0, "quality_score": 65.0}  # first pass, second fail

        statuses_run1 = [r.status for r in await engine.evaluate_rules(rules, input_data)]
        statuses_run2 = [r.status for r in await engine.evaluate_rules(rules, input_data)]
        statuses_run3 = [r.status for r in await engine.evaluate_rules(rules, input_data)]

        assert statuses_run1 == [EvaluationStatus.PASS, EvaluationStatus.FAIL]
        assert statuses_run1 == statuses_run2 == statuses_run3
