"""Demo assessment, score, finding, release assessment, and decision fixtures.

Payment Service Health Score: 62 (demonstrating room for improvement).
Dimension scores:
  security:             45  (critical CVE finding)
  test_coverage:        52  (high test coverage finding)
  documentation:        68  (medium API docs finding)
  operations_readiness: 70  (medium runbook finding)
  code_quality:         75  (low complexity finding)
Overall (equal weight): (45+52+68+70+75)/5 = 62
"""

from __future__ import annotations

import json

from forgeguard.data.seeds.fixtures.services import SERVICE_PAYMENT_ID
from forgeguard.data.seeds.fixtures.users import USER_TECHLEAD_ID, USER_SECURITY_ID
from forgeguard.data.seeds.fixtures.policies import (
    RULE_CQ_COMPLEXITY_ID,
    RULE_TC_UNIT_ID,
    RULE_SEC_CVE_ID,
    RULE_DOC_API_ID,
    RULE_DOC_RUNBOOK_ID,
)

# ---------------------------------------------------------------------------
# Fixed IDs
# ---------------------------------------------------------------------------
ASSESSMENT_HEALTH_ID       = "10000000-0000-0000-0000-000000000001"
SCORE_HEALTH_ID            = "20000000-0000-0000-0000-000000000001"

FINDING_CVE_ID             = "30000000-0000-0000-0000-000000000001"  # critical / security
FINDING_COVERAGE_ID        = "30000000-0000-0000-0000-000000000002"  # high / test_coverage
FINDING_API_DOCS_ID        = "30000000-0000-0000-0000-000000000003"  # medium / documentation
FINDING_RUNBOOK_ID         = "30000000-0000-0000-0000-000000000004"  # medium / operations_readiness
FINDING_COMPLEXITY_ID      = "30000000-0000-0000-0000-000000000005"  # low / code_quality

RELEASE_ASSESSMENT_ID      = "40000000-0000-0000-0000-000000000001"
RELEASE_DECISION_ID        = "50000000-0000-0000-0000-000000000001"

# ---------------------------------------------------------------------------
# Assessment
# ---------------------------------------------------------------------------
ASSESSMENT = {
    "id": ASSESSMENT_HEALTH_ID,
    "service_id": SERVICE_PAYMENT_ID,
    "assessment_type": "health_check",
    "trigger_type": "scheduled",
    "triggered_by": USER_TECHLEAD_ID,
    "status": "completed",
    "collected_data": json.dumps({
        "commit_sha": "abc123def456789",
        "branch": "main",
        "tools_run": ["semgrep", "bandit", "coverage.py", "osv-scanner"],
        "collection_duration_ms": 12450,
    }),
}

# ---------------------------------------------------------------------------
# Score
# ---------------------------------------------------------------------------
SCORE = {
    "id": SCORE_HEALTH_ID,
    "assessment_id": ASSESSMENT_HEALTH_ID,
    "service_id": SERVICE_PAYMENT_ID,
    "score_type": "health",
    "overall_score": "62.00",
    "dimension_scores": json.dumps({
        "security": 45.0,
        "test_coverage": 52.0,
        "documentation": 68.0,
        "operations_readiness": 70.0,
        "code_quality": 75.0,
    }),
    "contributing_factors": json.dumps({
        "top_risk": "Critical CVE in cryptography dependency",
        "quick_win": "Increase test coverage from 45% to 80% threshold",
        "trend": "declining",
    }),
}

# ---------------------------------------------------------------------------
# Findings (5 across 5 dimensions; 3+ dimensions requirement satisfied)
# ---------------------------------------------------------------------------
FINDINGS = [
    {
        "id": FINDING_CVE_ID,
        "assessment_id": ASSESSMENT_HEALTH_ID,
        "service_id": SERVICE_PAYMENT_ID,
        "policy_rule_id": RULE_SEC_CVE_ID,
        "severity": "critical",
        "dimension": "security",
        "status": "open",
        "title": "Critical CVE-2024-3219 in cryptography==41.0.0",
        "description": (
            "Dependency cryptography==41.0.0 has a known critical vulnerability "
            "CVE-2024-3219 (CVSS 9.1) allowing remote code execution via malformed "
            "X.509 certificates. Upgrade to cryptography>=42.0.4 immediately."
        ),
        "evidence": json.dumps({
            "cve_id": "CVE-2024-3219",
            "cvss_score": 9.1,
            "package": "cryptography",
            "installed_version": "41.0.0",
            "fix_version": "42.0.4",
            "source": "osv.dev",
        }),
        "ai_explanation": json.dumps({
            "summary": "Remote code execution via malformed X.509 certificate parsing.",
            "business_impact": "Attacker could execute arbitrary code in payment processing context.",
            "recommended_action": "pip install --upgrade cryptography>=42.0.4 and redeploy.",
        }),
        "confidence_score": "0.97",
    },
    {
        "id": FINDING_COVERAGE_ID,
        "assessment_id": ASSESSMENT_HEALTH_ID,
        "service_id": SERVICE_PAYMENT_ID,
        "policy_rule_id": RULE_TC_UNIT_ID,
        "severity": "high",
        "dimension": "test_coverage",
        "status": "open",
        "title": "Unit test coverage at 45% — threshold is 80%",
        "description": (
            "Payment Service has 45% unit test coverage against a required minimum "
            "of 80%. The billing and webhook processing modules have zero test coverage. "
            "This increases the risk of undetected regressions in critical payment flows."
        ),
        "evidence": json.dumps({
            "metric": "unit_test_coverage",
            "measured_value": 45,
            "threshold": 80,
            "unit": "percent",
            "uncovered_modules": ["billing.py", "webhooks.py", "subscription.py"],
        }),
        "ai_explanation": json.dumps({
            "summary": "Critical payment flows lack test coverage.",
            "business_impact": "Regression bugs in billing may go undetected until production incidents.",
            "recommended_action": "Add unit tests for billing.py and webhooks.py as first priority.",
        }),
        "confidence_score": "0.95",
    },
    {
        "id": FINDING_API_DOCS_ID,
        "assessment_id": ASSESSMENT_HEALTH_ID,
        "service_id": SERVICE_PAYMENT_ID,
        "policy_rule_id": RULE_DOC_API_ID,
        "severity": "medium",
        "dimension": "documentation",
        "status": "open",
        "title": "API documentation coverage at 62% — threshold is 90%",
        "description": (
            "38% of Payment Service API endpoints lack OpenAPI documentation. "
            "The /webhooks and /internal/* paths have no documented request/response schemas, "
            "making integration by other teams error-prone."
        ),
        "evidence": json.dumps({
            "metric": "api_doc_coverage",
            "measured_value": 62,
            "threshold": 90,
            "unit": "percent",
            "undocumented_paths": ["/webhooks/stripe", "/internal/reconcile", "/internal/audit"],
        }),
        "ai_explanation": json.dumps({
            "summary": "Missing API documentation for webhook and internal endpoints.",
            "business_impact": "Integration teams and auditors cannot verify contract behaviour.",
            "recommended_action": "Add OpenAPI annotations to all /webhooks and /internal/* endpoints.",
        }),
        "confidence_score": "0.90",
    },
    {
        "id": FINDING_RUNBOOK_ID,
        "assessment_id": ASSESSMENT_HEALTH_ID,
        "service_id": SERVICE_PAYMENT_ID,
        "policy_rule_id": RULE_DOC_RUNBOOK_ID,
        "severity": "medium",
        "dimension": "operations_readiness",
        "status": "open",
        "title": "No on-call runbook found in repository",
        "description": (
            "Payment Service does not have an on-call runbook. "
            "Operators responding to incidents have no documented escalation paths, "
            "common failure modes, or recovery procedures for this critical service."
        ),
        "evidence": json.dumps({
            "artifact": "runbook",
            "search_paths": ["docs/runbook.md", "docs/oncall/", "wiki/runbook"],
            "found": False,
        }),
        "ai_explanation": json.dumps({
            "summary": "Missing runbook increases MTTR during payment service incidents.",
            "business_impact": "Prolonged payment outages during incidents without documented recovery steps.",
            "recommended_action": "Create docs/runbook.md covering payment failures, database issues, and webhook retries.",
        }),
        "confidence_score": "0.92",
    },
    {
        "id": FINDING_COMPLEXITY_ID,
        "assessment_id": ASSESSMENT_HEALTH_ID,
        "service_id": SERVICE_PAYMENT_ID,
        "policy_rule_id": RULE_CQ_COMPLEXITY_ID,
        "severity": "low",
        "dimension": "code_quality",
        "status": "open",
        "title": "process_payment() cyclomatic complexity 14 — threshold is 10",
        "description": (
            "The process_payment() function in payment/processor.py has a cyclomatic "
            "complexity of 14, exceeding the threshold of 10. High complexity correlates "
            "with increased defect rates and reduced maintainability."
        ),
        "evidence": json.dumps({
            "metric": "cyclomatic_complexity",
            "function": "process_payment",
            "file": "payment/processor.py",
            "line": 142,
            "measured_value": 14,
            "threshold": 10,
        }),
        "ai_explanation": json.dumps({
            "summary": "Complex conditional logic in payment processor increases maintenance cost.",
            "business_impact": "Higher chance of introducing bugs when modifying payment logic.",
            "recommended_action": "Refactor process_payment() into smaller sub-functions with single responsibility.",
        }),
        "confidence_score": "0.88",
    },
]

# ---------------------------------------------------------------------------
# Release Assessment
# ---------------------------------------------------------------------------
RELEASE_ASSESSMENT = {
    "id": RELEASE_ASSESSMENT_ID,
    "service_id": SERVICE_PAYMENT_ID,
    "commit_sha": "abc123def456789abcdef0123456789abcdef01",
    "pr_reference": "https://git.forgeguard.demo/platform/payment-service/pull/247",
    "requested_by": USER_TECHLEAD_ID,
    "status": "completed",
    "change_analysis": json.dumps({
        "risk_level": "high",
        "changed_files": 23,
        "lines_added": 412,
        "lines_removed": 187,
        "risk_factors": [
            "Critical security finding unresolved",
            "Changes touch payment processing core",
            "No new tests added for changed modules",
        ],
        "ai_risk_score": 78.5,
    }),
}

# ---------------------------------------------------------------------------
# Release Decision — CONDITIONAL_APPROVE with escalation due to critical finding
# ---------------------------------------------------------------------------
RELEASE_DECISION = {
    "id": RELEASE_DECISION_ID,
    "release_assessment_id": RELEASE_ASSESSMENT_ID,
    "health_score_at_decision": "62.00",
    "risk_score_at_decision": "78.50",
    "decision": "CONDITIONAL_APPROVE",
    "decided_by_role": "security_reviewer",
    "decided_by": USER_SECURITY_ID,
    "rationale": (
        "Release conditionally approved pending: (1) CVE-2024-3219 remediation within 72 hours "
        "post-deployment, (2) test coverage improvement plan submitted to the security team. "
        "The critical CVE is auto-escalated to the Security Reviewer per ForgeGuard policy. "
        "Deployment is permitted only to staging until the CVE is patched."
    ),
    "comment": "Escalated automatically due to unresolved critical security finding CVE-2024-3219.",
    "was_escalated": True,
}
