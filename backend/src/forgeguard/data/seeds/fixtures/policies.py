"""Demo policy and policy rule fixtures — one policy per engineering dimension."""

from __future__ import annotations

import json

from forgeguard.data.seeds.fixtures.users import USER_ADMIN_ID

# ---------------------------------------------------------------------------
# Policy IDs
# ---------------------------------------------------------------------------
POLICY_CODE_QUALITY_ID       = "e0000000-0000-0000-0000-000000000001"
POLICY_TEST_COVERAGE_ID      = "e0000000-0000-0000-0000-000000000002"
POLICY_SECURITY_ID           = "e0000000-0000-0000-0000-000000000003"
POLICY_DOCUMENTATION_ID      = "e0000000-0000-0000-0000-000000000004"
POLICY_OPS_READINESS_ID      = "e0000000-0000-0000-0000-000000000005"

# ---------------------------------------------------------------------------
# Policy Rule IDs (3 per policy = 15 total)
# ---------------------------------------------------------------------------
# Code Quality rules
RULE_CQ_COMPLEXITY_ID        = "f0000000-0000-0000-0000-000000000001"
RULE_CQ_DUPLICATION_ID       = "f0000000-0000-0000-0000-000000000002"
RULE_CQ_LINT_ID              = "f0000000-0000-0000-0000-000000000003"

# Test Coverage rules
RULE_TC_UNIT_ID              = "f0000000-0000-0000-0000-000000000004"
RULE_TC_INTEGRATION_ID       = "f0000000-0000-0000-0000-000000000005"
RULE_TC_BRANCH_ID            = "f0000000-0000-0000-0000-000000000006"

# Security rules
RULE_SEC_CVE_ID              = "f0000000-0000-0000-0000-000000000007"
RULE_SEC_SECRETS_ID          = "f0000000-0000-0000-0000-000000000008"
RULE_SEC_SAST_ID             = "f0000000-0000-0000-0000-000000000009"

# Documentation rules
RULE_DOC_API_ID              = "f0000000-0000-0000-0000-000000000010"
RULE_DOC_RUNBOOK_ID          = "f0000000-0000-0000-0000-000000000011"
RULE_DOC_ADR_ID              = "f0000000-0000-0000-0000-000000000012"

# Operations Readiness rules
RULE_OPS_ALERTS_ID           = "f0000000-0000-0000-0000-000000000013"
RULE_OPS_DASHBOARDS_ID       = "f0000000-0000-0000-0000-000000000014"
RULE_OPS_ONBOARDING_ID       = "f0000000-0000-0000-0000-000000000015"

# ---------------------------------------------------------------------------
# Fixture data
# ---------------------------------------------------------------------------

POLICIES = [
    {
        "id": POLICY_CODE_QUALITY_ID,
        "name": "Code Quality Standards",
        "dimension": "code_quality",
        "description": "Enforces code maintainability, complexity limits, and static analysis thresholds.",
        "is_active": True,
        "version": 1,
        "created_by": USER_ADMIN_ID,
    },
    {
        "id": POLICY_TEST_COVERAGE_ID,
        "name": "Test Coverage Requirements",
        "dimension": "test_coverage",
        "description": "Mandates minimum unit and integration test coverage ratios.",
        "is_active": True,
        "version": 1,
        "created_by": USER_ADMIN_ID,
    },
    {
        "id": POLICY_SECURITY_ID,
        "name": "Security Baseline Policy",
        "dimension": "security",
        "description": "Prevents deployment of services with known CVEs, exposed secrets, or failing SAST scans.",
        "is_active": True,
        "version": 2,
        "created_by": USER_ADMIN_ID,
    },
    {
        "id": POLICY_DOCUMENTATION_ID,
        "name": "Documentation Standards",
        "dimension": "documentation",
        "description": "Requires API documentation, runbooks, and Architecture Decision Records for production services.",
        "is_active": True,
        "version": 1,
        "created_by": USER_ADMIN_ID,
    },
    {
        "id": POLICY_OPS_READINESS_ID,
        "name": "Operations Readiness Checklist",
        "dimension": "operations_readiness",
        "description": "Verifies alerting, dashboards, on-call runbooks, and SLO definitions before production deployment.",
        "is_active": True,
        "version": 1,
        "created_by": USER_ADMIN_ID,
    },
]

POLICY_RULES = [
    # --- Code Quality (1 low, 1 low, 1 medium) ---
    {
        "id": RULE_CQ_COMPLEXITY_ID,
        "policy_id": POLICY_CODE_QUALITY_ID,
        "name": "Cyclomatic Complexity Limit",
        "rule_type": "threshold",
        "threshold_config": json.dumps({"metric": "cyclomatic_complexity", "operator": "lte", "value": 10}),
        "severity": "low",
        "weight": "0.5",
        "is_active": True,
    },
    {
        "id": RULE_CQ_DUPLICATION_ID,
        "policy_id": POLICY_CODE_QUALITY_ID,
        "name": "Code Duplication Threshold",
        "rule_type": "threshold",
        "threshold_config": json.dumps({"metric": "duplication_ratio", "operator": "lte", "value": 5, "unit": "percent"}),
        "severity": "medium",
        "weight": "1.0",
        "is_active": True,
    },
    {
        "id": RULE_CQ_LINT_ID,
        "policy_id": POLICY_CODE_QUALITY_ID,
        "name": "Zero Lint Errors",
        "rule_type": "threshold",
        "threshold_config": json.dumps({"metric": "lint_errors", "operator": "eq", "value": 0}),
        "severity": "medium",
        "weight": "1.0",
        "is_active": True,
    },
    # --- Test Coverage (1 high, 1 medium, 1 medium) ---
    {
        "id": RULE_TC_UNIT_ID,
        "policy_id": POLICY_TEST_COVERAGE_ID,
        "name": "Unit Test Coverage Minimum",
        "rule_type": "threshold",
        "threshold_config": json.dumps({"metric": "unit_test_coverage", "operator": "gte", "value": 80, "unit": "percent"}),
        "severity": "high",
        "weight": "2.0",
        "is_active": True,
    },
    {
        "id": RULE_TC_INTEGRATION_ID,
        "policy_id": POLICY_TEST_COVERAGE_ID,
        "name": "Integration Test Coverage Minimum",
        "rule_type": "threshold",
        "threshold_config": json.dumps({"metric": "integration_test_coverage", "operator": "gte", "value": 60, "unit": "percent"}),
        "severity": "medium",
        "weight": "1.5",
        "is_active": True,
    },
    {
        "id": RULE_TC_BRANCH_ID,
        "policy_id": POLICY_TEST_COVERAGE_ID,
        "name": "Branch Coverage Minimum",
        "rule_type": "threshold",
        "threshold_config": json.dumps({"metric": "branch_coverage", "operator": "gte", "value": 70, "unit": "percent"}),
        "severity": "medium",
        "weight": "1.0",
        "is_active": True,
    },
    # --- Security (1 critical, 1 high, 1 high) ---
    {
        "id": RULE_SEC_CVE_ID,
        "policy_id": POLICY_SECURITY_ID,
        "name": "No Known Critical CVEs",
        "rule_type": "vulnerability_scan",
        "threshold_config": json.dumps({"severity_threshold": "critical", "operator": "eq", "value": 0, "source": "osv.dev"}),
        "severity": "critical",
        "weight": "3.0",
        "is_active": True,
    },
    {
        "id": RULE_SEC_SECRETS_ID,
        "policy_id": POLICY_SECURITY_ID,
        "name": "No Hardcoded Secrets",
        "rule_type": "secret_scan",
        "threshold_config": json.dumps({"tool": "gitleaks", "operator": "eq", "value": 0}),
        "severity": "high",
        "weight": "2.5",
        "is_active": True,
    },
    {
        "id": RULE_SEC_SAST_ID,
        "policy_id": POLICY_SECURITY_ID,
        "name": "SAST Scan Pass",
        "rule_type": "sast",
        "threshold_config": json.dumps({"tool": "semgrep", "severity_threshold": "high", "operator": "eq", "value": 0}),
        "severity": "high",
        "weight": "2.0",
        "is_active": True,
    },
    # --- Documentation (1 medium, 1 medium, 1 low) ---
    {
        "id": RULE_DOC_API_ID,
        "policy_id": POLICY_DOCUMENTATION_ID,
        "name": "API Documentation Coverage",
        "rule_type": "threshold",
        "threshold_config": json.dumps({"metric": "api_doc_coverage", "operator": "gte", "value": 90, "unit": "percent"}),
        "severity": "medium",
        "weight": "1.0",
        "is_active": True,
    },
    {
        "id": RULE_DOC_RUNBOOK_ID,
        "policy_id": POLICY_DOCUMENTATION_ID,
        "name": "Runbook Exists",
        "rule_type": "existence",
        "threshold_config": json.dumps({"artifact": "runbook", "operator": "exists"}),
        "severity": "medium",
        "weight": "1.5",
        "is_active": True,
    },
    {
        "id": RULE_DOC_ADR_ID,
        "policy_id": POLICY_DOCUMENTATION_ID,
        "name": "Architecture Decision Records",
        "rule_type": "existence",
        "threshold_config": json.dumps({"artifact": "adr_directory", "min_count": 1}),
        "severity": "low",
        "weight": "0.5",
        "is_active": True,
    },
    # --- Operations Readiness (1 high, 1 medium, 1 low) ---
    {
        "id": RULE_OPS_ALERTS_ID,
        "policy_id": POLICY_OPS_READINESS_ID,
        "name": "Critical Alerts Configured",
        "rule_type": "existence",
        "threshold_config": json.dumps({"artifact": "alerting_rules", "min_count": 3}),
        "severity": "high",
        "weight": "2.0",
        "is_active": True,
    },
    {
        "id": RULE_OPS_DASHBOARDS_ID,
        "policy_id": POLICY_OPS_READINESS_ID,
        "name": "Operational Dashboard Exists",
        "rule_type": "existence",
        "threshold_config": json.dumps({"artifact": "grafana_dashboard", "operator": "exists"}),
        "severity": "medium",
        "weight": "1.0",
        "is_active": True,
    },
    {
        "id": RULE_OPS_ONBOARDING_ID,
        "policy_id": POLICY_OPS_READINESS_ID,
        "name": "On-call Runbook Defined",
        "rule_type": "existence",
        "threshold_config": json.dumps({"artifact": "oncall_runbook", "operator": "exists"}),
        "severity": "low",
        "weight": "0.5",
        "is_active": True,
    },
]
