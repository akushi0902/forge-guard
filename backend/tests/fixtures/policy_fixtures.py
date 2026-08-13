"""Policy Guardian test fixtures: 3 policies × 5 rules (WO-035).

Provides deterministic in-memory fixture dicts for unit/integration tests.
These fixtures represent database row shapes (dict) as returned by the
PolicyRepository — not Pydantic schema objects.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

# ---------------------------------------------------------------------------
# Deterministic UUIDs for reproducible tests
# ---------------------------------------------------------------------------

POLICY_CODE_QUALITY_ID = uuid.UUID("11111111-0001-0001-0001-000000000001")
POLICY_SECURITY_ID = uuid.UUID("11111111-0002-0002-0002-000000000002")
POLICY_TEST_COVERAGE_ID = uuid.UUID("11111111-0003-0003-0003-000000000003")

RULE_IDS: list[uuid.UUID] = [
    uuid.UUID(f"22222222-{i:04d}-{i:04d}-{i:04d}-{i:012d}")
    for i in range(1, 16)
]

_TS = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)

# ---------------------------------------------------------------------------
# Policy fixtures
# ---------------------------------------------------------------------------

POLICY_CODE_QUALITY: dict = {
    "id": POLICY_CODE_QUALITY_ID,
    "name": "Code Quality Policy",
    "dimension": "code_quality",
    "description": "Enforces code quality standards for all services.",
    "is_active": True,
    "version": 1,
    "created_by": None,
    "deleted_at": None,
    "created_at": _TS,
    "updated_at": _TS,
    "rule_count": 5,
}

POLICY_SECURITY: dict = {
    "id": POLICY_SECURITY_ID,
    "name": "Security Policy",
    "dimension": "security",
    "description": "Enforces security standards and vulnerability thresholds.",
    "is_active": True,
    "version": 2,
    "created_by": None,
    "deleted_at": None,
    "created_at": _TS,
    "updated_at": _TS,
    "rule_count": 5,
}

POLICY_TEST_COVERAGE: dict = {
    "id": POLICY_TEST_COVERAGE_ID,
    "name": "Test Coverage Policy",
    "dimension": "test_coverage",
    "description": "Requires minimum test coverage across all services.",
    "is_active": True,
    "version": 1,
    "created_by": None,
    "deleted_at": None,
    "created_at": _TS,
    "updated_at": _TS,
    "rule_count": 5,
}

ALL_POLICIES: list[dict] = [
    POLICY_CODE_QUALITY,
    POLICY_SECURITY,
    POLICY_TEST_COVERAGE,
]

# ---------------------------------------------------------------------------
# Policy rule fixtures (5 per policy, varying rule_types and severities)
# ---------------------------------------------------------------------------

RULES_CODE_QUALITY: list[dict] = [
    {
        "id": RULE_IDS[0],
        "policy_id": POLICY_CODE_QUALITY_ID,
        "name": "Min Cyclomatic Complexity",
        "rule_type": "threshold_lte",
        "threshold_config": {"numeric_value": 10, "unit": "count"},
        "severity": "high",
        "weight": "10.00",
        "is_active": True,
        "created_at": _TS,
        "updated_at": _TS,
    },
    {
        "id": RULE_IDS[1],
        "policy_id": POLICY_CODE_QUALITY_ID,
        "name": "Max Function Length",
        "rule_type": "threshold_lte",
        "threshold_config": {"numeric_value": 50, "unit": "lines"},
        "severity": "medium",
        "weight": "5.00",
        "is_active": True,
        "created_at": _TS,
        "updated_at": _TS,
    },
    {
        "id": RULE_IDS[2],
        "policy_id": POLICY_CODE_QUALITY_ID,
        "name": "No TODO Comments",
        "rule_type": "regex_no_match",
        "threshold_config": {"pattern": r"TODO|FIXME|HACK"},
        "severity": "low",
        "weight": "2.00",
        "is_active": True,
        "created_at": _TS,
        "updated_at": _TS,
    },
    {
        "id": RULE_IDS[3],
        "policy_id": POLICY_CODE_QUALITY_ID,
        "name": "Docstring Required",
        "rule_type": "regex_match",
        "threshold_config": {"pattern": r'"""'},
        "severity": "low",
        "weight": "3.00",
        "is_active": False,
        "created_at": _TS,
        "updated_at": _TS,
    },
    {
        "id": RULE_IDS[4],
        "policy_id": POLICY_CODE_QUALITY_ID,
        "name": "Max File Size",
        "rule_type": "threshold_lte",
        "threshold_config": {"numeric_value": 500, "unit": "lines"},
        "severity": "medium",
        "weight": "5.00",
        "is_active": True,
        "created_at": _TS,
        "updated_at": _TS,
    },
]

RULES_SECURITY: list[dict] = [
    {
        "id": RULE_IDS[5],
        "policy_id": POLICY_SECURITY_ID,
        "name": "Zero Critical CVEs",
        "rule_type": "threshold_eq",
        "threshold_config": {"numeric_value": 0, "unit": "count"},
        "severity": "critical",
        "weight": "30.00",
        "is_active": True,
        "created_at": _TS,
        "updated_at": _TS,
    },
    {
        "id": RULE_IDS[6],
        "policy_id": POLICY_SECURITY_ID,
        "name": "Max High CVEs",
        "rule_type": "threshold_lte",
        "threshold_config": {"numeric_value": 5, "unit": "count"},
        "severity": "high",
        "weight": "20.00",
        "is_active": True,
        "created_at": _TS,
        "updated_at": _TS,
    },
    {
        "id": RULE_IDS[7],
        "policy_id": POLICY_SECURITY_ID,
        "name": "No Plaintext Secrets",
        "rule_type": "regex_no_match",
        "threshold_config": {"pattern": r"(?i)(password|secret|api_key)\s*=\s*['\"]"},
        "severity": "critical",
        "weight": "25.00",
        "is_active": True,
        "created_at": _TS,
        "updated_at": _TS,
    },
    {
        "id": RULE_IDS[8],
        "policy_id": POLICY_SECURITY_ID,
        "name": "Min SAST Score",
        "rule_type": "threshold_gte",
        "threshold_config": {"numeric_value": 80, "unit": "score"},
        "severity": "high",
        "weight": "15.00",
        "is_active": True,
        "created_at": _TS,
        "updated_at": _TS,
    },
    {
        "id": RULE_IDS[9],
        "policy_id": POLICY_SECURITY_ID,
        "name": "Dependency License Check",
        "rule_type": "regex_match",
        "threshold_config": {"pattern": r"^(MIT|Apache-2\.0|BSD)"},
        "severity": "medium",
        "weight": "10.00",
        "is_active": False,
        "created_at": _TS,
        "updated_at": _TS,
    },
]

RULES_TEST_COVERAGE: list[dict] = [
    {
        "id": RULE_IDS[10],
        "policy_id": POLICY_TEST_COVERAGE_ID,
        "name": "Min Line Coverage",
        "rule_type": "threshold_gte",
        "threshold_config": {"numeric_value": 80, "unit": "percent"},
        "severity": "high",
        "weight": "20.00",
        "is_active": True,
        "created_at": _TS,
        "updated_at": _TS,
    },
    {
        "id": RULE_IDS[11],
        "policy_id": POLICY_TEST_COVERAGE_ID,
        "name": "Min Branch Coverage",
        "rule_type": "threshold_gte",
        "threshold_config": {"numeric_value": 70, "unit": "percent"},
        "severity": "medium",
        "weight": "15.00",
        "is_active": True,
        "created_at": _TS,
        "updated_at": _TS,
    },
    {
        "id": RULE_IDS[12],
        "policy_id": POLICY_TEST_COVERAGE_ID,
        "name": "Min Mutation Score",
        "rule_type": "threshold_gte",
        "threshold_config": {"numeric_value": 60, "unit": "percent"},
        "severity": "medium",
        "weight": "10.00",
        "is_active": True,
        "created_at": _TS,
        "updated_at": _TS,
    },
    {
        "id": RULE_IDS[13],
        "policy_id": POLICY_TEST_COVERAGE_ID,
        "name": "No Skipped Tests",
        "rule_type": "threshold_eq",
        "threshold_config": {"numeric_value": 0, "unit": "count"},
        "severity": "low",
        "weight": "5.00",
        "is_active": True,
        "created_at": _TS,
        "updated_at": _TS,
    },
    {
        "id": RULE_IDS[14],
        "policy_id": POLICY_TEST_COVERAGE_ID,
        "name": "Integration Test Required",
        "rule_type": "regex_match",
        "threshold_config": {"pattern": r"test_integration_"},
        "severity": "high",
        "weight": "10.00",
        "is_active": True,
        "created_at": _TS,
        "updated_at": _TS,
    },
]

ALL_RULES: list[dict] = RULES_CODE_QUALITY + RULES_SECURITY + RULES_TEST_COVERAGE

RULES_BY_POLICY: dict[uuid.UUID, list[dict]] = {
    POLICY_CODE_QUALITY_ID: RULES_CODE_QUALITY,
    POLICY_SECURITY_ID: RULES_SECURITY,
    POLICY_TEST_COVERAGE_ID: RULES_TEST_COVERAGE,
}
