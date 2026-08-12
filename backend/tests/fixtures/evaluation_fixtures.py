"""Evaluation engine test fixtures: mock rules and normalized input dicts (WO-038).

Provides deterministic SimpleNamespace rule objects and flat input_data dicts
for all 5 governance dimensions.  These bypass the ORM layer entirely —
no database required.
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from types import SimpleNamespace

from forgeguard.services.domain.severity import SeverityLevel

# ---------------------------------------------------------------------------
# Deterministic rule IDs
# ---------------------------------------------------------------------------

RULE_GTE_ID = uuid.UUID("aaaaaaaa-0001-0001-0001-000000000001")
RULE_LTE_ID = uuid.UUID("aaaaaaaa-0002-0002-0002-000000000002")
RULE_EQ_ID = uuid.UUID("aaaaaaaa-0003-0003-0003-000000000003")
RULE_REGEX_MATCH_ID = uuid.UUID("aaaaaaaa-0004-0004-0004-000000000004")
RULE_REGEX_NO_MATCH_ID = uuid.UUID("aaaaaaaa-0005-0005-0005-000000000005")
RULE_MISSING_KEY_ID = uuid.UUID("aaaaaaaa-0006-0006-0006-000000000006")
RULE_INVALID_REGEX_ID = uuid.UUID("aaaaaaaa-0007-0007-0007-000000000007")
RULE_UNKNOWN_TYPE_ID = uuid.UUID("aaaaaaaa-0008-0008-0008-000000000008")


def _policy(dimension: str) -> SimpleNamespace:
    return SimpleNamespace(dimension=dimension)


def make_rule(
    rule_id: uuid.UUID | None = None,
    name: str = "Test Rule",
    rule_type: str = "threshold_gte",
    threshold_config: dict | None = None,
    severity: SeverityLevel = SeverityLevel.HIGH,
    dimension: str = "code_quality",
    weight: Decimal = Decimal("1.0"),
    is_active: bool = True,
) -> SimpleNamespace:
    """Build a SimpleNamespace that mimics a loaded PolicyRule ORM object."""
    return SimpleNamespace(
        id=rule_id or uuid.uuid4(),
        name=name,
        rule_type=rule_type,
        threshold_config=threshold_config or {"data_key": "test_key", "numeric_value": 80},
        severity=severity,
        weight=weight,
        is_active=is_active,
        policy=_policy(dimension),
    )


# ---------------------------------------------------------------------------
# One fixture rule per evaluator type
# ---------------------------------------------------------------------------

GTE_RULE = make_rule(
    rule_id=RULE_GTE_ID,
    name="Min Test Coverage",
    rule_type="threshold_gte",
    threshold_config={"data_key": "test_coverage", "numeric_value": 80},
    severity=SeverityLevel.HIGH,
    dimension="test_coverage",
)

LTE_RULE = make_rule(
    rule_id=RULE_LTE_ID,
    name="Max Cyclomatic Complexity",
    rule_type="threshold_lte",
    threshold_config={"data_key": "cyclomatic_complexity", "numeric_value": 10},
    severity=SeverityLevel.MEDIUM,
    dimension="code_quality",
)

EQ_RULE = make_rule(
    rule_id=RULE_EQ_ID,
    name="Zero Critical CVEs",
    rule_type="threshold_eq",
    threshold_config={"data_key": "critical_cve_count", "numeric_value": 0},
    severity=SeverityLevel.CRITICAL,
    dimension="security",
)

REGEX_MATCH_RULE = make_rule(
    rule_id=RULE_REGEX_MATCH_ID,
    name="Has README",
    rule_type="regex_match",
    threshold_config={"data_key": "readme_content", "pattern": r"(?i)^#\s+\w+"},
    severity=SeverityLevel.LOW,
    dimension="documentation",
)

REGEX_NO_MATCH_RULE = make_rule(
    rule_id=RULE_REGEX_NO_MATCH_ID,
    name="No TODO Comments",
    rule_type="regex_no_match",
    threshold_config={"data_key": "source_scan", "pattern": r"TODO|FIXME|HACK"},
    severity=SeverityLevel.LOW,
    dimension="code_quality",
)

MISSING_KEY_RULE = make_rule(
    rule_id=RULE_MISSING_KEY_ID,
    name="Missing Data Rule",
    rule_type="threshold_gte",
    threshold_config={"data_key": "nonexistent_key", "numeric_value": 50},
    severity=SeverityLevel.MEDIUM,
    dimension="operations_readiness",
)

INVALID_REGEX_RULE = make_rule(
    rule_id=RULE_INVALID_REGEX_ID,
    name="Bad Regex Rule",
    rule_type="regex_match",
    threshold_config={"data_key": "source_scan", "pattern": r"[unclosed"},
    severity=SeverityLevel.LOW,
    dimension="code_quality",
)

UNKNOWN_TYPE_RULE = make_rule(
    rule_id=RULE_UNKNOWN_TYPE_ID,
    name="Unknown Type Rule",
    rule_type="threshold_magic",
    threshold_config={"data_key": "test_coverage", "numeric_value": 80},
    severity=SeverityLevel.LOW,
    dimension="test_coverage",
)

# ---------------------------------------------------------------------------
# Normalized input dicts for all 5 dimensions (realistic values)
# ---------------------------------------------------------------------------

CODE_QUALITY_INPUT: dict = {
    "cyclomatic_complexity": 7,
    "function_length_lines": 35,
    "source_scan": "def calculate_total(items): return sum(i.price for i in items)",
    "file_size_lines": 250,
    "type_coverage_percent": 92.0,
}

TEST_COVERAGE_INPUT: dict = {
    "test_coverage": 85.5,
    "branch_coverage": 78.2,
    "mutation_score": 65.0,
    "skipped_tests": 0,
    "integration_test_count": 12,
}

SECURITY_INPUT: dict = {
    "critical_cve_count": 0,
    "high_cve_count": 2,
    "sast_score": 88,
    "dependency_licenses": "MIT Apache-2.0 BSD-3-Clause",
    "secrets_scan": "No secrets detected in scan output",
}

DOCUMENTATION_INPUT: dict = {
    "readme_content": "# Payment Service\n\nHandles payment processing.",
    "api_doc_coverage": 95.0,
    "changelog_present": "true",
    "inline_doc_ratio": 0.82,
}

OPERATIONS_READINESS_INPUT: dict = {
    "health_endpoint_present": "true",
    "metrics_endpoint_present": "true",
    "deployment_frequency_days": 3,
    "mean_time_to_recovery_hours": 1.5,
    "alert_coverage_percent": 90.0,
}

ALL_DIMENSIONS_INPUT: dict = {
    **CODE_QUALITY_INPUT,
    **TEST_COVERAGE_INPUT,
    **SECURITY_INPUT,
    **DOCUMENTATION_INPUT,
    **OPERATIONS_READINESS_INPUT,
}
