"""Unit tests for RuleEvaluationEngine (WO-038).

Covers:
  - Multi-rule evaluation returning one result per rule
  - All 5 rule types in a single batch
  - Missing data keys → INCONCLUSIVE (not ERROR)
  - Unknown rule_type → ERROR
  - Per-rule timeout → ERROR
  - Empty rules list returns empty results
  - Empty input_data marks all rules as INCONCLUSIVE
  - Mixed pass/fail/inconclusive in single batch
  - Rule metadata preserved in every result

Run:
    pytest tests/unit/services/test_evaluation_engine.py -v
"""

from __future__ import annotations

import asyncio
import uuid
from decimal import Decimal
from unittest.mock import AsyncMock, patch

import pytest

from forgeguard.services.domain.evaluation import EvaluationStatus
from forgeguard.services.domain.severity import SeverityLevel
from forgeguard.services.evaluation_engine import RuleEvaluationEngine, RULE_TYPE_REGISTRY
from tests.fixtures.evaluation_fixtures import (
    ALL_DIMENSIONS_INPUT,
    GTE_RULE,
    LTE_RULE,
    EQ_RULE,
    REGEX_MATCH_RULE,
    REGEX_NO_MATCH_RULE,
    MISSING_KEY_RULE,
    UNKNOWN_TYPE_RULE,
    make_rule,
)


# ===========================================================================
# Helpers
# ===========================================================================

@pytest.fixture()
def engine() -> RuleEvaluationEngine:
    return RuleEvaluationEngine()


# ===========================================================================
# Basic evaluation
# ===========================================================================

class TestEvaluateRules:
    @pytest.mark.asyncio
    async def test_returns_one_result_per_rule(self, engine):
        rules = [GTE_RULE, LTE_RULE, EQ_RULE, REGEX_MATCH_RULE, REGEX_NO_MATCH_RULE]
        results = await engine.evaluate_rules(rules, ALL_DIMENSIONS_INPUT)
        assert len(results) == 5

    @pytest.mark.asyncio
    async def test_empty_rules_returns_empty(self, engine):
        results = await engine.evaluate_rules([], ALL_DIMENSIONS_INPUT)
        assert results == []

    @pytest.mark.asyncio
    async def test_empty_input_data_all_inconclusive(self, engine):
        rules = [GTE_RULE, LTE_RULE, EQ_RULE, REGEX_MATCH_RULE, REGEX_NO_MATCH_RULE]
        results = await engine.evaluate_rules(rules, {})
        for r in results:
            assert r.status == EvaluationStatus.INCONCLUSIVE, (
                f"Expected INCONCLUSIVE for {r.rule_name}, got {r.status}"
            )

    @pytest.mark.asyncio
    async def test_gte_rule_passes_with_sufficient_coverage(self, engine):
        # GTE_RULE: test_coverage >= 80; input has 85.5
        results = await engine.evaluate_rules([GTE_RULE], ALL_DIMENSIONS_INPUT)
        assert results[0].status == EvaluationStatus.PASS

    @pytest.mark.asyncio
    async def test_lte_rule_passes_with_low_complexity(self, engine):
        # LTE_RULE: cyclomatic_complexity <= 10; input has 7
        results = await engine.evaluate_rules([LTE_RULE], ALL_DIMENSIONS_INPUT)
        assert results[0].status == EvaluationStatus.PASS

    @pytest.mark.asyncio
    async def test_eq_rule_passes_with_zero_cves(self, engine):
        # EQ_RULE: critical_cve_count == 0; input has 0
        results = await engine.evaluate_rules([EQ_RULE], ALL_DIMENSIONS_INPUT)
        assert results[0].status == EvaluationStatus.PASS

    @pytest.mark.asyncio
    async def test_regex_match_rule_passes_on_match(self, engine):
        # REGEX_MATCH_RULE: readme_content matches heading pattern
        results = await engine.evaluate_rules([REGEX_MATCH_RULE], ALL_DIMENSIONS_INPUT)
        assert results[0].status == EvaluationStatus.PASS

    @pytest.mark.asyncio
    async def test_regex_no_match_rule_passes_on_clean_source(self, engine):
        # REGEX_NO_MATCH_RULE: source_scan must NOT match TODO|FIXME|HACK
        results = await engine.evaluate_rules([REGEX_NO_MATCH_RULE], ALL_DIMENSIONS_INPUT)
        assert results[0].status == EvaluationStatus.PASS


# ===========================================================================
# Missing data / INCONCLUSIVE
# ===========================================================================

class TestMissingData:
    @pytest.mark.asyncio
    async def test_missing_key_rule_returns_inconclusive(self, engine):
        results = await engine.evaluate_rules([MISSING_KEY_RULE], ALL_DIMENSIONS_INPUT)
        assert results[0].status == EvaluationStatus.INCONCLUSIVE

    @pytest.mark.asyncio
    async def test_evidence_explains_missing_key(self, engine):
        results = await engine.evaluate_rules([MISSING_KEY_RULE], ALL_DIMENSIONS_INPUT)
        assert results[0].evidence["reason"] == "missing_data_key"
        assert results[0].evidence["data_key"] == "nonexistent_key"

    @pytest.mark.asyncio
    async def test_mixed_present_and_missing_keys(self, engine):
        rule_present = make_rule(
            rule_type="threshold_gte",
            threshold_config={"data_key": "test_coverage", "numeric_value": 80},
            dimension="test_coverage",
        )
        rule_missing = make_rule(
            rule_type="threshold_gte",
            threshold_config={"data_key": "absent_key", "numeric_value": 50},
            dimension="test_coverage",
        )
        results = await engine.evaluate_rules(
            [rule_present, rule_missing],
            {"test_coverage": 90},
        )
        assert results[0].status == EvaluationStatus.PASS
        assert results[1].status == EvaluationStatus.INCONCLUSIVE


# ===========================================================================
# Unknown rule_type → ERROR
# ===========================================================================

class TestUnknownRuleType:
    @pytest.mark.asyncio
    async def test_unknown_type_returns_error(self, engine):
        results = await engine.evaluate_rules([UNKNOWN_TYPE_RULE], ALL_DIMENSIONS_INPUT)
        assert results[0].status == EvaluationStatus.ERROR

    @pytest.mark.asyncio
    async def test_unknown_type_evidence_mentions_type(self, engine):
        results = await engine.evaluate_rules([UNKNOWN_TYPE_RULE], ALL_DIMENSIONS_INPUT)
        assert "threshold_magic" in results[0].evidence["reason"]

    @pytest.mark.asyncio
    async def test_unknown_type_does_not_prevent_other_rules(self, engine):
        rules = [UNKNOWN_TYPE_RULE, GTE_RULE]
        results = await engine.evaluate_rules(rules, ALL_DIMENSIONS_INPUT)
        assert len(results) == 2
        assert results[0].status == EvaluationStatus.ERROR
        assert results[1].status == EvaluationStatus.PASS


# ===========================================================================
# Timeout → ERROR
# ===========================================================================

class TestRuleTimeout:
    @pytest.mark.asyncio
    async def test_timeout_returns_error_status(self, engine):
        async def _slow_evaluate(rule, input_data):
            await asyncio.sleep(1.0)  # will be cancelled by 100ms timeout

        with patch.dict(
            RULE_TYPE_REGISTRY,
            {"threshold_gte": type("SlowEval", (), {"evaluate": _slow_evaluate})()},
        ):
            rule = make_rule(
                rule_type="threshold_gte",
                threshold_config={"data_key": "cov", "numeric_value": 80},
            )
            results = await engine.evaluate_rules([rule], {"cov": 85})

        assert results[0].status == EvaluationStatus.ERROR
        assert results[0].evidence["reason"] == "rule_evaluation_timeout"

    @pytest.mark.asyncio
    async def test_timeout_does_not_prevent_other_rules(self, engine):
        async def _slow_evaluate(rule, input_data):
            await asyncio.sleep(1.0)

        with patch.dict(
            RULE_TYPE_REGISTRY,
            {"threshold_lte": type("SlowEval", (), {"evaluate": _slow_evaluate})()},
        ):
            rules = [
                make_rule(
                    rule_type="threshold_lte",
                    threshold_config={"data_key": "x", "numeric_value": 10},
                    name="Slow Rule",
                ),
                make_rule(
                    rule_type="threshold_gte",
                    threshold_config={"data_key": "test_coverage", "numeric_value": 80},
                    name="Fast Rule",
                ),
            ]
            results = await engine.evaluate_rules(rules, {"x": 5, "test_coverage": 90})

        assert results[0].status == EvaluationStatus.ERROR
        assert results[1].status == EvaluationStatus.PASS


# ===========================================================================
# Result metadata preservation
# ===========================================================================

class TestResultMetadata:
    @pytest.mark.asyncio
    async def test_result_preserves_rule_id(self, engine):
        rule_id = uuid.UUID("99999999-9999-9999-9999-999999999999")
        rule = make_rule(
            rule_id=rule_id,
            rule_type="threshold_gte",
            threshold_config={"data_key": "cov", "numeric_value": 80},
        )
        results = await engine.evaluate_rules([rule], {"cov": 85})
        assert results[0].rule_id == rule_id

    @pytest.mark.asyncio
    async def test_result_preserves_severity(self, engine):
        rule = make_rule(
            rule_type="threshold_gte",
            threshold_config={"data_key": "cov", "numeric_value": 80},
            severity=SeverityLevel.CRITICAL,
        )
        results = await engine.evaluate_rules([rule], {"cov": 85})
        assert results[0].severity == SeverityLevel.CRITICAL

    @pytest.mark.asyncio
    async def test_result_has_evaluated_at_timestamp(self, engine):
        rule = make_rule(
            rule_type="threshold_gte",
            threshold_config={"data_key": "cov", "numeric_value": 80},
        )
        results = await engine.evaluate_rules([rule], {"cov": 85})
        assert results[0].evaluated_at is not None

    @pytest.mark.asyncio
    async def test_dimension_from_policy_relationship(self, engine):
        from types import SimpleNamespace
        rule = make_rule(
            rule_type="threshold_gte",
            threshold_config={"data_key": "cov", "numeric_value": 80},
            dimension="security",
        )
        results = await engine.evaluate_rules([rule], {"cov": 85})
        assert results[0].dimension == "security"


# ===========================================================================
# RULE_TYPE_REGISTRY completeness
# ===========================================================================

class TestRuleTypeRegistry:
    def test_registry_contains_all_five_types(self):
        expected = {
            "threshold_gte",
            "threshold_lte",
            "threshold_eq",
            "regex_match",
            "regex_no_match",
        }
        assert set(RULE_TYPE_REGISTRY.keys()) == expected
