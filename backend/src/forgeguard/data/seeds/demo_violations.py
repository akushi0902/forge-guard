"""Demo violation policy rules for the Payment Service (WO-055).

Seeds 10 policy_rule records across all 5 governance dimensions with
thresholds that the Payment Service's simulated collected_data is designed
to fail.  All inserts use ON CONFLICT DO NOTHING — the function is idempotent.

Severity distribution of violations:
  critical  — critical_cve_count (2 CVEs vs threshold 0)
              critical_path_coverage (60% vs threshold 95%)
  high      — cyclomatic_complexity (15 vs max 10)
              unit_test_coverage (45% vs min 80%)
              input_validation_coverage (70% vs threshold 100%)
              health_check_endpoint_present (false vs required)
  medium    — code_duplication_ratio (12% vs max 5%)
              api_doc_coverage (40% vs min 90%)
              structured_logging_enabled (partial vs full)
  low       — readme_complete (false vs required)

Rule IDs start at c0000000-... to avoid collision with existing fixtures.
Policy IDs reference the existing dimension policies (e0000000-...).
"""

from __future__ import annotations

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Violation rule IDs  (c0000000-0000-0000-0000-0000000000NN)
# ---------------------------------------------------------------------------

RULE_VIO_CQ_COMPLEXITY_ID         = "c0000000-0000-0000-0000-000000000001"
RULE_VIO_CQ_DUPLICATION_ID        = "c0000000-0000-0000-0000-000000000002"
RULE_VIO_TC_MIN_COVERAGE_ID       = "c0000000-0000-0000-0000-000000000003"
RULE_VIO_TC_CRITICAL_PATH_ID      = "c0000000-0000-0000-0000-000000000004"
RULE_VIO_SEC_CVE_COUNT_ID         = "c0000000-0000-0000-0000-000000000005"
RULE_VIO_SEC_INPUT_VALIDATION_ID  = "c0000000-0000-0000-0000-000000000006"
RULE_VIO_DOC_API_COMPLETENESS_ID  = "c0000000-0000-0000-0000-000000000007"
RULE_VIO_DOC_README_ID            = "c0000000-0000-0000-0000-000000000008"
RULE_VIO_OPS_HEALTH_CHECK_ID      = "c0000000-0000-0000-0000-000000000009"
RULE_VIO_OPS_STRUCTURED_LOG_ID    = "c0000000-0000-0000-0000-000000000010"

ALL_VIOLATION_RULE_IDS = [
    RULE_VIO_CQ_COMPLEXITY_ID,
    RULE_VIO_CQ_DUPLICATION_ID,
    RULE_VIO_TC_MIN_COVERAGE_ID,
    RULE_VIO_TC_CRITICAL_PATH_ID,
    RULE_VIO_SEC_CVE_COUNT_ID,
    RULE_VIO_SEC_INPUT_VALIDATION_ID,
    RULE_VIO_DOC_API_COMPLETENESS_ID,
    RULE_VIO_DOC_README_ID,
    RULE_VIO_OPS_HEALTH_CHECK_ID,
    RULE_VIO_OPS_STRUCTURED_LOG_ID,
]

# Existing policy IDs (from fixtures/policies.py)
_POLICY_CODE_QUALITY_ID   = "e0000000-0000-0000-0000-000000000001"
_POLICY_TEST_COVERAGE_ID  = "e0000000-0000-0000-0000-000000000002"
_POLICY_SECURITY_ID       = "e0000000-0000-0000-0000-000000000003"
_POLICY_DOCUMENTATION_ID  = "e0000000-0000-0000-0000-000000000004"
_POLICY_OPS_READINESS_ID  = "e0000000-0000-0000-0000-000000000005"

# ---------------------------------------------------------------------------
# Violation rule definitions
# ---------------------------------------------------------------------------

VIOLATION_RULES: list[dict[str, Any]] = [
    # ---- code_quality -------------------------------------------------------
    {
        "id": RULE_VIO_CQ_COMPLEXITY_ID,
        "policy_id": _POLICY_CODE_QUALITY_ID,
        "name": "Cyclomatic Complexity Threshold",
        "rule_type": "threshold_lte",
        "threshold_config": json.dumps({
            "data_key": "cyclomatic_complexity",
            "numeric_value": 10,
            "operator": "lte",
            "unit": "count",
            "description": "Maximum allowed cyclomatic complexity per module",
        }),
        "severity": "high",
        "weight": "2.0",
        "is_active": True,
    },
    {
        "id": RULE_VIO_CQ_DUPLICATION_ID,
        "policy_id": _POLICY_CODE_QUALITY_ID,
        "name": "Code Duplication Percentage",
        "rule_type": "threshold_lte",
        "threshold_config": json.dumps({
            "data_key": "code_duplication_ratio",
            "numeric_value": 5,
            "operator": "lte",
            "unit": "percent",
            "description": "Maximum percentage of duplicated code blocks",
        }),
        "severity": "medium",
        "weight": "1.5",
        "is_active": True,
    },
    # ---- test_coverage -------------------------------------------------------
    {
        "id": RULE_VIO_TC_MIN_COVERAGE_ID,
        "policy_id": _POLICY_TEST_COVERAGE_ID,
        "name": "Minimum Coverage Percentage",
        "rule_type": "threshold_gte",
        "threshold_config": json.dumps({
            "data_key": "unit_test_coverage",
            "numeric_value": 80,
            "operator": "gte",
            "unit": "percent",
            "description": "Minimum required unit test line coverage",
        }),
        "severity": "high",
        "weight": "2.5",
        "is_active": True,
    },
    {
        "id": RULE_VIO_TC_CRITICAL_PATH_ID,
        "policy_id": _POLICY_TEST_COVERAGE_ID,
        "name": "Critical Path Coverage",
        "rule_type": "threshold_gte",
        "threshold_config": json.dumps({
            "data_key": "critical_path_coverage",
            "numeric_value": 95,
            "operator": "gte",
            "unit": "percent",
            "description": "Coverage of payment and auth critical code paths",
        }),
        "severity": "critical",
        "weight": "3.0",
        "is_active": True,
    },
    # ---- security -----------------------------------------------------------
    {
        "id": RULE_VIO_SEC_CVE_COUNT_ID,
        "policy_id": _POLICY_SECURITY_ID,
        "name": "Dependency Vulnerability Check",
        "rule_type": "threshold_eq",
        "threshold_config": json.dumps({
            "data_key": "critical_cve_count",
            "numeric_value": 0,
            "operator": "eq",
            "unit": "count",
            "description": "Zero critical CVEs allowed in production dependencies",
        }),
        "severity": "critical",
        "weight": "3.0",
        "is_active": True,
    },
    {
        "id": RULE_VIO_SEC_INPUT_VALIDATION_ID,
        "policy_id": _POLICY_SECURITY_ID,
        "name": "Input Validation Coverage",
        "rule_type": "threshold_gte",
        "threshold_config": json.dumps({
            "data_key": "input_validation_coverage",
            "numeric_value": 100,
            "operator": "gte",
            "unit": "percent",
            "description": "All API endpoints must validate and sanitise inputs",
        }),
        "severity": "high",
        "weight": "2.5",
        "is_active": True,
    },
    # ---- documentation -------------------------------------------------------
    {
        "id": RULE_VIO_DOC_API_COMPLETENESS_ID,
        "policy_id": _POLICY_DOCUMENTATION_ID,
        "name": "API Documentation Completeness",
        "rule_type": "threshold_gte",
        "threshold_config": json.dumps({
            "data_key": "api_doc_coverage",
            "numeric_value": 90,
            "operator": "gte",
            "unit": "percent",
            "description": "OpenAPI/Swagger spec coverage across all endpoints",
        }),
        "severity": "medium",
        "weight": "1.0",
        "is_active": True,
    },
    {
        "id": RULE_VIO_DOC_README_ID,
        "policy_id": _POLICY_DOCUMENTATION_ID,
        "name": "README Completeness",
        "rule_type": "threshold_eq",
        "threshold_config": json.dumps({
            "data_key": "readme_complete",
            "numeric_value": 1,
            "operator": "eq",
            "unit": "boolean",
            "description": "README must contain: overview, setup, API reference, runbook link",
        }),
        "severity": "low",
        "weight": "0.5",
        "is_active": True,
    },
    # ---- operations_readiness ------------------------------------------------
    {
        "id": RULE_VIO_OPS_HEALTH_CHECK_ID,
        "policy_id": _POLICY_OPS_READINESS_ID,
        "name": "Health Check Endpoint",
        "rule_type": "threshold_eq",
        "threshold_config": json.dumps({
            "data_key": "health_check_endpoint_present",
            "numeric_value": 1,
            "operator": "eq",
            "unit": "boolean",
            "description": "Service must expose /health and /ready endpoints",
        }),
        "severity": "high",
        "weight": "2.0",
        "is_active": True,
    },
    {
        "id": RULE_VIO_OPS_STRUCTURED_LOG_ID,
        "policy_id": _POLICY_OPS_READINESS_ID,
        "name": "Structured Logging Enabled",
        "rule_type": "threshold_eq",
        "threshold_config": json.dumps({
            "data_key": "structured_logging_enabled",
            "numeric_value": 1,
            "operator": "eq",
            "unit": "boolean",
            "description": "All log output must be structured JSON with correlation IDs",
        }),
        "severity": "medium",
        "weight": "1.0",
        "is_active": True,
    },
]


async def seed_violation_rules(conn: Any) -> dict[str, int]:
    """Insert violation policy rules idempotently via ON CONFLICT DO NOTHING.

    Returns a dict of {inserted: N, skipped: N}.
    """
    inserted = 0
    skipped = 0

    for rule in VIOLATION_RULES:
        try:
            result = await conn.execute(
                """
                INSERT INTO policy_rules
                    (id, policy_id, name, rule_type, threshold_config, severity, weight, is_active)
                VALUES
                    ($1, $2, $3, $4, $5::jsonb, $6, $7::numeric, $8)
                ON CONFLICT (id) DO NOTHING
                """,
                rule["id"],
                rule["policy_id"],
                rule["name"],
                rule["rule_type"],
                rule["threshold_config"],
                rule["severity"],
                rule["weight"],
                rule["is_active"],
            )
            # asyncpg returns "INSERT 0 N" — parse count
            count = int(result.split()[-1]) if result else 0
            if count > 0:
                inserted += 1
            else:
                skipped += 1
        except Exception as exc:
            logger.error(
                "demo_violations.seed_rule_failed",
                rule_id=rule["id"],
                rule_name=rule["name"],
                error=str(exc),
            )

    logger.info(
        "demo_violations.seed_complete",
        inserted=inserted,
        skipped=skipped,
        total=len(VIOLATION_RULES),
    )
    return {"inserted": inserted, "skipped": skipped}
