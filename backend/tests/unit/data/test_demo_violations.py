"""Unit tests for Payment Service demo violation seed data (WO-055).

Covers:
  - All 10 violation rules have valid schema fields
  - Severity values are in the allowed enum set
  - Weights are in the valid range (> 0.0, <= 3.0)
  - Dimension values match the 5 allowed values
  - threshold_config JSON is well-formed with required fields
  - rule_type values match valid evaluation engine types
  - All 10 simulated values fail their respective thresholds
  - Idempotency: all rule IDs are unique (no duplicates)
  - JSON fixture files are loadable and match Python constants
  - Severity distribution: at least 1 critical, 2 high, 1 medium, 1 low
  - VIOLATIONS_CATALOG.md exists and documents required scenarios
  - collected_data expected_violations ≥ 5 entries with required fields

Run:
    pytest tests/unit/data/test_demo_violations.py -v
"""

from __future__ import annotations

import json
import os
from decimal import Decimal
from pathlib import Path

import pytest

from forgeguard.data.seeds.demo_violations import (
    ALL_VIOLATION_RULE_IDS,
    VIOLATION_RULES,
)
from forgeguard.data.seeds.demo_collected_data import (
    EXPECTED_VIOLATIONS,
    PAYMENT_SERVICE_COLLECTED_DATA,
)

# ---------------------------------------------------------------------------
# Allowed value sets
# ---------------------------------------------------------------------------

VALID_DIMENSIONS = {
    "code_quality",
    "test_coverage",
    "security",
    "documentation",
    "operations_readiness",
}

VALID_SEVERITIES = {"critical", "high", "medium", "low"}

VALID_RULE_TYPES = {
    "threshold_gte",
    "threshold_lte",
    "threshold_eq",
    "threshold",
    "regex_match",
    "regex_no_match",
    "existence",
    "boolean",
}

_FIXTURE_DIR = Path(__file__).parent.parent.parent / "fixtures" / "demo" / "violations"
_CATALOG_PATH = Path(__file__).parent.parent.parent.parent / "docs" / "VIOLATIONS_CATALOG.md"


# ===========================================================================
# Schema validation
# ===========================================================================

class TestViolationRuleSchema:
    def test_exactly_ten_rules_defined(self):
        assert len(VIOLATION_RULES) == 10

    def test_all_rules_have_required_keys(self):
        required = {"id", "policy_id", "name", "rule_type", "threshold_config", "severity", "weight", "is_active"}
        for rule in VIOLATION_RULES:
            missing = required - set(rule.keys())
            assert not missing, f"Rule {rule.get('name')!r} missing fields: {missing}"

    def test_all_rule_ids_are_unique(self):
        ids = [r["id"] for r in VIOLATION_RULES]
        assert len(ids) == len(set(ids)), "Duplicate rule IDs detected"

    def test_all_rule_ids_match_constants(self):
        ids_from_rules = {r["id"] for r in VIOLATION_RULES}
        ids_from_constants = set(ALL_VIOLATION_RULE_IDS)
        assert ids_from_rules == ids_from_constants

    def test_all_severities_are_valid(self):
        for rule in VIOLATION_RULES:
            assert rule["severity"] in VALID_SEVERITIES, (
                f"Rule {rule['name']!r} has invalid severity: {rule['severity']!r}"
            )

    def test_all_dimensions_from_policy_ids(self):
        valid_policy_prefixes = {"e0000000-0000-0000-0000-00000000000"}
        for rule in VIOLATION_RULES:
            assert rule["policy_id"].startswith("e0000000"), (
                f"Rule {rule['name']!r} references unexpected policy {rule['policy_id']!r}"
            )

    def test_all_weights_positive_and_in_range(self):
        for rule in VIOLATION_RULES:
            w = Decimal(str(rule["weight"]))
            assert w > Decimal("0"), f"Rule {rule['name']!r} has zero weight"
            assert w <= Decimal("3.0"), f"Rule {rule['name']!r} weight {w} exceeds maximum 3.0"

    def test_all_rule_types_are_valid(self):
        for rule in VIOLATION_RULES:
            assert rule["rule_type"] in VALID_RULE_TYPES, (
                f"Rule {rule['name']!r} has unrecognised rule_type: {rule['rule_type']!r}"
            )

    def test_all_rules_are_active(self):
        for rule in VIOLATION_RULES:
            assert rule["is_active"] is True, (
                f"Rule {rule['name']!r} is not active — violation rules must be is_active=True"
            )


# ===========================================================================
# threshold_config JSON validity
# ===========================================================================

class TestThresholdConfigSchema:
    def test_threshold_config_is_valid_json(self):
        for rule in VIOLATION_RULES:
            try:
                cfg = json.loads(rule["threshold_config"])
            except json.JSONDecodeError as exc:
                pytest.fail(f"Rule {rule['name']!r} has invalid threshold_config JSON: {exc}")

    def test_threshold_config_has_data_key(self):
        for rule in VIOLATION_RULES:
            cfg = json.loads(rule["threshold_config"])
            assert "data_key" in cfg, (
                f"Rule {rule['name']!r} threshold_config missing 'data_key'"
            )

    def test_threshold_config_has_numeric_value_for_threshold_rules(self):
        for rule in VIOLATION_RULES:
            if rule["rule_type"] in {"threshold_gte", "threshold_lte", "threshold_eq"}:
                cfg = json.loads(rule["threshold_config"])
                assert "numeric_value" in cfg, (
                    f"Rule {rule['name']!r} missing 'numeric_value' in threshold_config"
                )

    def test_threshold_config_has_operator(self):
        for rule in VIOLATION_RULES:
            cfg = json.loads(rule["threshold_config"])
            assert "operator" in cfg, (
                f"Rule {rule['name']!r} threshold_config missing 'operator'"
            )

    def test_all_data_keys_present_in_collected_data(self):
        for rule in VIOLATION_RULES:
            cfg = json.loads(rule["threshold_config"])
            data_key = cfg["data_key"]
            assert data_key in PAYMENT_SERVICE_COLLECTED_DATA, (
                f"Rule {rule['name']!r} data_key {data_key!r} not found in PAYMENT_SERVICE_COLLECTED_DATA"
            )


# ===========================================================================
# Severity distribution
# ===========================================================================

class TestSeverityDistribution:
    def _counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for rule in VIOLATION_RULES:
            s = rule["severity"]
            counts[s] = counts.get(s, 0) + 1
        return counts

    def test_at_least_one_critical(self):
        assert self._counts().get("critical", 0) >= 1

    def test_at_least_two_high(self):
        assert self._counts().get("high", 0) >= 2

    def test_at_least_one_medium(self):
        assert self._counts().get("medium", 0) >= 1

    def test_at_least_one_low(self):
        assert self._counts().get("low", 0) >= 1


# ===========================================================================
# Dimension coverage
# ===========================================================================

class TestDimensionCoverage:
    def _policy_to_dimension(self) -> dict[str, str]:
        return {
            "e0000000-0000-0000-0000-000000000001": "code_quality",
            "e0000000-0000-0000-0000-000000000002": "test_coverage",
            "e0000000-0000-0000-0000-000000000003": "security",
            "e0000000-0000-0000-0000-000000000004": "documentation",
            "e0000000-0000-0000-0000-000000000005": "operations_readiness",
        }

    def test_all_five_dimensions_covered(self):
        mapping = self._policy_to_dimension()
        covered = {mapping[r["policy_id"]] for r in VIOLATION_RULES if r["policy_id"] in mapping}
        assert covered == VALID_DIMENSIONS, (
            f"Not all dimensions covered. Missing: {VALID_DIMENSIONS - covered}"
        )

    def test_at_least_two_rules_per_dimension(self):
        mapping = self._policy_to_dimension()
        counts: dict[str, int] = {}
        for rule in VIOLATION_RULES:
            dim = mapping.get(rule["policy_id"], "unknown")
            counts[dim] = counts.get(dim, 0) + 1
        for dim in VALID_DIMENSIONS:
            assert counts.get(dim, 0) >= 2, (
                f"Dimension {dim!r} has fewer than 2 rules (got {counts.get(dim, 0)})"
            )


# ===========================================================================
# Simulated violations: threshold comparison
# ===========================================================================

class TestSimulatedViolations:
    """Verify that each simulated actual value FAILS its rule threshold."""

    def _fails(self, rule_type: str, actual: float, threshold: float) -> bool:
        if rule_type == "threshold_gte":
            return actual < threshold
        if rule_type == "threshold_lte":
            return actual > threshold
        if rule_type == "threshold_eq":
            return actual != threshold
        return False

    def test_all_ten_rules_produce_violations(self):
        failing = 0
        for rule in VIOLATION_RULES:
            cfg = json.loads(rule["threshold_config"])
            data_key = cfg["data_key"]
            actual = PAYMENT_SERVICE_COLLECTED_DATA.get(data_key)
            threshold = cfg.get("numeric_value")
            if actual is not None and threshold is not None:
                if self._fails(rule["rule_type"], float(actual), float(threshold)):
                    failing += 1
        assert failing == 10, (
            f"Expected all 10 rules to fail against collected_data, got {failing}"
        )

    def test_critical_cve_count_fails_eq_zero(self):
        actual = PAYMENT_SERVICE_COLLECTED_DATA["critical_cve_count"]
        assert actual != 0, f"Expected critical_cve_count != 0, got {actual}"

    def test_unit_test_coverage_fails_gte_80(self):
        actual = PAYMENT_SERVICE_COLLECTED_DATA["unit_test_coverage"]
        assert actual < 80, f"Expected unit_test_coverage < 80, got {actual}"

    def test_critical_path_coverage_fails_gte_95(self):
        actual = PAYMENT_SERVICE_COLLECTED_DATA["critical_path_coverage"]
        assert actual < 95, f"Expected critical_path_coverage < 95, got {actual}"

    def test_cyclomatic_complexity_fails_lte_10(self):
        actual = PAYMENT_SERVICE_COLLECTED_DATA["cyclomatic_complexity"]
        assert actual > 10, f"Expected cyclomatic_complexity > 10, got {actual}"

    def test_at_least_five_violations_in_expected_list(self):
        assert len(EXPECTED_VIOLATIONS) >= 5


# ===========================================================================
# Expected violations schema
# ===========================================================================

class TestExpectedViolationsSchema:
    def test_all_violations_have_required_fields(self):
        required = {"rule_name", "dimension", "severity", "data_key", "threshold", "actual", "operator", "expected_status", "finding_title"}
        for v in EXPECTED_VIOLATIONS:
            missing = required - set(v.keys())
            assert not missing, f"Violation {v.get('rule_name')!r} missing fields: {missing}"

    def test_all_violation_statuses_are_fail(self):
        for v in EXPECTED_VIOLATIONS:
            assert v["expected_status"] == "fail", (
                f"Violation {v['rule_name']!r} expected_status should be 'fail', got {v['expected_status']!r}"
            )

    def test_violation_dimensions_are_valid(self):
        for v in EXPECTED_VIOLATIONS:
            assert v["dimension"] in VALID_DIMENSIONS


# ===========================================================================
# JSON fixtures
# ===========================================================================

class TestJsonFixtures:
    def test_policy_rules_json_exists(self):
        assert (_FIXTURE_DIR / "policy_rules.json").exists()

    def test_collected_data_json_exists(self):
        assert (_FIXTURE_DIR / "collected_data.json").exists()

    def test_policy_rules_json_parses(self):
        rules = json.loads((_FIXTURE_DIR / "policy_rules.json").read_text())
        assert isinstance(rules, list)
        assert len(rules) == 10

    def test_collected_data_json_parses(self):
        data = json.loads((_FIXTURE_DIR / "collected_data.json").read_text())
        assert "collected_data" in data
        assert "expected_violations" in data

    def test_json_rule_ids_match_python_constants(self):
        rules = json.loads((_FIXTURE_DIR / "policy_rules.json").read_text())
        json_ids = {r["id"] for r in rules}
        assert json_ids == set(ALL_VIOLATION_RULE_IDS)

    def test_json_collected_data_keys_match_python(self):
        fixture = json.loads((_FIXTURE_DIR / "collected_data.json").read_text())
        json_keys = set(fixture["collected_data"].keys())
        py_keys = {k for k in PAYMENT_SERVICE_COLLECTED_DATA.keys() if not k.startswith("_")}
        assert json_keys == py_keys

    def test_json_violations_count_matches_python(self):
        fixture = json.loads((_FIXTURE_DIR / "collected_data.json").read_text())
        assert len(fixture["expected_violations"]) == len(EXPECTED_VIOLATIONS)


# ===========================================================================
# VIOLATIONS_CATALOG.md
# ===========================================================================

class TestViolationsCatalog:
    def test_catalog_file_exists(self):
        assert _CATALOG_PATH.exists(), (
            f"VIOLATIONS_CATALOG.md not found at {_CATALOG_PATH}"
        )

    def test_catalog_documents_at_least_five_scenarios(self):
        content = _CATALOG_PATH.read_text()
        # Each scenario has a numbered heading (### 1., ### 2., etc.)
        import re
        scenarios = re.findall(r"^### \d+\.", content, re.MULTILINE)
        assert len(scenarios) >= 5, (
            f"VIOLATIONS_CATALOG.md documents only {len(scenarios)} scenarios, need ≥ 5"
        )

    def test_catalog_has_safety_review_section(self):
        content = _CATALOG_PATH.read_text()
        assert "Safety Review" in content or "Safety Verification" in content

    def test_catalog_mentions_all_five_dimensions(self):
        content = _CATALOG_PATH.read_text()
        for dim in VALID_DIMENSIONS:
            assert dim in content, f"VIOLATIONS_CATALOG.md does not mention dimension {dim!r}"
