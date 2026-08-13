"""Simulated collected_data for the Payment Service demo (WO-055).

Each fixture represents the data the Policy Guardian would collect from the
Payment Service.  Values are deliberately set to FAIL the corresponding
violation rules in demo_violations.py to produce a realistic finding set.

Simulated compliance posture of ForgeGuard Payment Service v2.4.1:
  - Health score: ~42 (critically non-compliant)
  - Findings: 2 critical, 4 high, 3 medium, 1 low

All security simulations are safe:
  - critical_cve_count=2 represents a COUNT of known CVE identifiers returned
    by a dependency scanner — no actual exploit code or payloads are included.
  - input_validation_coverage=70 represents a measured percentage, not a gap
    in a live system — the demo uses parameterised queries throughout.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Payment Service simulated collected_data (flat dict, keyed by data_key)
# ---------------------------------------------------------------------------

PAYMENT_SERVICE_COLLECTED_DATA: dict = {
    # --- code_quality --------------------------------------------------------
    # cyclomatic_complexity: 15 — FAILS threshold_lte 10 (severity: high)
    "cyclomatic_complexity": 15,
    # code_duplication_ratio: 12.0% — FAILS threshold_lte 5% (severity: medium)
    "code_duplication_ratio": 12.0,

    # --- test_coverage -------------------------------------------------------
    # unit_test_coverage: 45.0% — FAILS threshold_gte 80% (severity: high)
    "unit_test_coverage": 45.0,
    # critical_path_coverage: 60.0% — FAILS threshold_gte 95% (severity: critical)
    "critical_path_coverage": 60.0,

    # --- security ------------------------------------------------------------
    # critical_cve_count: 2 — FAILS threshold_eq 0 (severity: critical)
    # Simulated: OSV scanner reports 2 critical CVEs in dependency tree.
    # Safety: this is a COUNT value only; no CVE identifiers or exploits included.
    "critical_cve_count": 2,
    # input_validation_coverage: 70.0% — FAILS threshold_gte 100% (severity: high)
    # Simulated: 7/10 API endpoint groups have input validation.
    # Safety: this is a coverage percentage; underlying code uses parameterised queries.
    "input_validation_coverage": 70.0,

    # --- documentation -------------------------------------------------------
    # api_doc_coverage: 40.0% — FAILS threshold_gte 90% (severity: medium)
    "api_doc_coverage": 40.0,
    # readme_complete: 0 (false) — FAILS threshold_eq 1 (severity: low)
    # README exists but is missing: API reference, runbook link, setup guide
    "readme_complete": 0,

    # --- operations_readiness ------------------------------------------------
    # health_check_endpoint_present: 0 (false) — FAILS threshold_eq 1 (severity: high)
    # Service does not expose /health or /ready endpoints
    "health_check_endpoint_present": 0,
    # structured_logging_enabled: 0 (false/partial) — FAILS threshold_eq 1 (severity: medium)
    # Partial: some modules use print() instead of structured logger
    "structured_logging_enabled": 0,

    # --- metadata (not used in rule evaluation) ----------------------------
    "_meta": {
        "service_name": "ForgeGuard Payment Service",
        "version": "2.4.1",
        "commit_sha": "deadbeef12345678deadbeef12345678deadbeef",
        "branch": "release/v2.4.1",
        "collection_timestamp": "2026-08-12T04:00:00Z",
        "tools_run": ["semgrep", "coverage.py", "osv-scanner", "pylint", "lizard"],
    },
}

# ---------------------------------------------------------------------------
# Expected violation outcomes (for documentation and testing)
# ---------------------------------------------------------------------------

EXPECTED_VIOLATIONS: list[dict] = [
    {
        "rule_name": "Critical Path Coverage",
        "dimension": "test_coverage",
        "severity": "critical",
        "data_key": "critical_path_coverage",
        "threshold": 95,
        "actual": 60.0,
        "operator": "gte",
        "expected_status": "fail",
        "finding_title": "Critical path coverage at 60% — 35pp below the 95% requirement",
    },
    {
        "rule_name": "Dependency Vulnerability Check",
        "dimension": "security",
        "severity": "critical",
        "data_key": "critical_cve_count",
        "threshold": 0,
        "actual": 2,
        "operator": "eq",
        "expected_status": "fail",
        "finding_title": "2 critical CVEs detected in production dependency tree",
    },
    {
        "rule_name": "Cyclomatic Complexity Threshold",
        "dimension": "code_quality",
        "severity": "high",
        "data_key": "cyclomatic_complexity",
        "threshold": 10,
        "actual": 15,
        "operator": "lte",
        "expected_status": "fail",
        "finding_title": "Cyclomatic complexity score 15 exceeds maximum of 10",
    },
    {
        "rule_name": "Minimum Coverage Percentage",
        "dimension": "test_coverage",
        "severity": "high",
        "data_key": "unit_test_coverage",
        "threshold": 80,
        "actual": 45.0,
        "operator": "gte",
        "expected_status": "fail",
        "finding_title": "Unit test coverage at 45% — 35pp below the 80% minimum",
    },
    {
        "rule_name": "Input Validation Coverage",
        "dimension": "security",
        "severity": "high",
        "data_key": "input_validation_coverage",
        "threshold": 100,
        "actual": 70.0,
        "operator": "gte",
        "expected_status": "fail",
        "finding_title": "Input validation covers only 70% of API endpoint groups",
    },
    {
        "rule_name": "Health Check Endpoint",
        "dimension": "operations_readiness",
        "severity": "high",
        "data_key": "health_check_endpoint_present",
        "threshold": 1,
        "actual": 0,
        "operator": "eq",
        "expected_status": "fail",
        "finding_title": "No /health or /ready endpoint present — Kubernetes probes will fail",
    },
    {
        "rule_name": "Code Duplication Percentage",
        "dimension": "code_quality",
        "severity": "medium",
        "data_key": "code_duplication_ratio",
        "threshold": 5,
        "actual": 12.0,
        "operator": "lte",
        "expected_status": "fail",
        "finding_title": "Code duplication at 12% — 7pp above the 5% threshold",
    },
    {
        "rule_name": "API Documentation Completeness",
        "dimension": "documentation",
        "severity": "medium",
        "data_key": "api_doc_coverage",
        "threshold": 90,
        "actual": 40.0,
        "operator": "gte",
        "expected_status": "fail",
        "finding_title": "API documentation covers only 40% of endpoints",
    },
    {
        "rule_name": "Structured Logging Enabled",
        "dimension": "operations_readiness",
        "severity": "medium",
        "data_key": "structured_logging_enabled",
        "threshold": 1,
        "actual": 0,
        "operator": "eq",
        "expected_status": "fail",
        "finding_title": "Structured logging is partial — some modules use unstructured print()",
    },
    {
        "rule_name": "README Completeness",
        "dimension": "documentation",
        "severity": "low",
        "data_key": "readme_complete",
        "threshold": 1,
        "actual": 0,
        "operator": "eq",
        "expected_status": "fail",
        "finding_title": "README is missing: API reference, runbook link, setup guide",
    },
]
