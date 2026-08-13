"""Finding test fixtures (WO-041).

Pre-built finding dicts at all severity levels and statuses across three
services.  Use these in unit and integration tests to avoid repetitive
fixture construction.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

_NOW = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)

# ---------------------------------------------------------------------------
# Stable IDs
# ---------------------------------------------------------------------------

SERVICE_A_ID = uuid.UUID("a0000000-0000-0000-0000-000000000001")
SERVICE_B_ID = uuid.UUID("a0000000-0000-0000-0000-000000000002")
SERVICE_C_ID = uuid.UUID("a0000000-0000-0000-0000-000000000003")

ASSESSMENT_1_ID = uuid.UUID("b0000000-0000-0000-0000-000000000001")
ASSESSMENT_2_ID = uuid.UUID("b0000000-0000-0000-0000-000000000002")

RULE_1_ID = uuid.UUID("c0000000-0000-0000-0000-000000000001")
RULE_2_ID = uuid.UUID("c0000000-0000-0000-0000-000000000002")
RULE_3_ID = uuid.UUID("c0000000-0000-0000-0000-000000000003")
RULE_4_ID = uuid.UUID("c0000000-0000-0000-0000-000000000004")
RULE_5_ID = uuid.UUID("c0000000-0000-0000-0000-000000000005")


def _finding(
    *,
    finding_id: uuid.UUID,
    service_id: uuid.UUID,
    assessment_id: uuid.UUID,
    policy_rule_id: uuid.UUID,
    severity: str,
    dimension: str,
    status: str,
    title: str,
    description: str | None = None,
    escalation_required: bool = False,
    evidence: dict | None = None,
) -> dict:
    return {
        "id": finding_id,
        "assessment_id": assessment_id,
        "service_id": service_id,
        "policy_rule_id": policy_rule_id,
        "severity": severity,
        "dimension": dimension,
        "status": status,
        "title": title,
        "description": description or f"{title} description",
        "evidence": evidence or {"actual_value": None, "expected_value": None, "evaluation_status": "fail"},
        "ai_explanation": None,
        "confidence_score": None,
        "escalation_required": escalation_required,
        "created_at": _NOW,
        "updated_at": _NOW,
        "resolved_at": None,
    }


# ---------------------------------------------------------------------------
# One finding per severity level — all open, Service A
# ---------------------------------------------------------------------------

CRITICAL_FINDING = _finding(
    finding_id=uuid.UUID("f0000000-0000-0000-0000-000000000001"),
    service_id=SERVICE_A_ID,
    assessment_id=ASSESSMENT_1_ID,
    policy_rule_id=RULE_1_ID,
    severity="critical",
    dimension="security",
    status="open",
    title="Critical CVE violation in security",
    description="Expected 0 but found 2 for Critical CVE Check",
    escalation_required=True,
    evidence={"actual_value": 2, "expected_value": 0, "evaluation_status": "fail", "data_key": "critical_cve_count"},
)

HIGH_FINDING = _finding(
    finding_id=uuid.UUID("f0000000-0000-0000-0000-000000000002"),
    service_id=SERVICE_A_ID,
    assessment_id=ASSESSMENT_1_ID,
    policy_rule_id=RULE_2_ID,
    severity="high",
    dimension="test_coverage",
    status="open",
    title="Unit Test Coverage violation in test_coverage",
    description="Expected 80 but found 45 for Unit Test Coverage",
    evidence={"actual_value": 45.0, "expected_value": 80.0, "evaluation_status": "fail", "data_key": "unit_test_coverage"},
)

MEDIUM_FINDING = _finding(
    finding_id=uuid.UUID("f0000000-0000-0000-0000-000000000003"),
    service_id=SERVICE_B_ID,
    assessment_id=ASSESSMENT_1_ID,
    policy_rule_id=RULE_3_ID,
    severity="medium",
    dimension="documentation",
    status="acknowledged",
    title="API Documentation violation in documentation",
    description="Expected True but found False for API Documentation",
    evidence={"actual_value": False, "expected_value": True, "evaluation_status": "fail", "data_key": "api_docs_complete"},
)

LOW_FINDING = _finding(
    finding_id=uuid.UUID("f0000000-0000-0000-0000-000000000004"),
    service_id=SERVICE_B_ID,
    assessment_id=ASSESSMENT_2_ID,
    policy_rule_id=RULE_4_ID,
    severity="low",
    dimension="code_quality",
    status="remediated",
    title="Complexity Check violation in code_quality",
    description="Expected 10 but found 12 for Complexity Check",
    evidence={"actual_value": 12, "expected_value": 10, "evaluation_status": "fail", "data_key": "cyclomatic_complexity"},
)

# ---------------------------------------------------------------------------
# One finding per status — all Service C
# ---------------------------------------------------------------------------

OPEN_FINDING = _finding(
    finding_id=uuid.UUID("f0000000-0000-0000-0000-000000000010"),
    service_id=SERVICE_C_ID,
    assessment_id=ASSESSMENT_1_ID,
    policy_rule_id=RULE_1_ID,
    severity="high",
    dimension="security",
    status="open",
    title="Open Secrets Check violation in security",
)

ACKNOWLEDGED_FINDING = _finding(
    finding_id=uuid.UUID("f0000000-0000-0000-0000-000000000011"),
    service_id=SERVICE_C_ID,
    assessment_id=ASSESSMENT_1_ID,
    policy_rule_id=RULE_2_ID,
    severity="medium",
    dimension="test_coverage",
    status="acknowledged",
    title="Acknowledged coverage violation in test_coverage",
)

REMEDIATED_FINDING = _finding(
    finding_id=uuid.UUID("f0000000-0000-0000-0000-000000000012"),
    service_id=SERVICE_C_ID,
    assessment_id=ASSESSMENT_2_ID,
    policy_rule_id=RULE_3_ID,
    severity="low",
    dimension="documentation",
    status="remediated",
    title="Remediated docs violation in documentation",
)

EXCEPTION_GRANTED_FINDING = _finding(
    finding_id=uuid.UUID("f0000000-0000-0000-0000-000000000013"),
    service_id=SERVICE_C_ID,
    assessment_id=ASSESSMENT_2_ID,
    policy_rule_id=RULE_4_ID,
    severity="high",
    dimension="operations_readiness",
    status="exception_granted",
    title="Exception-granted ops violation in operations_readiness",
)

REOPENED_FINDING = _finding(
    finding_id=uuid.UUID("f0000000-0000-0000-0000-000000000014"),
    service_id=SERVICE_C_ID,
    assessment_id=ASSESSMENT_2_ID,
    policy_rule_id=RULE_5_ID,
    severity="critical",
    dimension="security",
    status="reopened",
    title="Reopened CVE violation in security",
    escalation_required=True,
)

# ---------------------------------------------------------------------------
# Convenience collections
# ---------------------------------------------------------------------------

ALL_SEVERITY_FINDINGS = [CRITICAL_FINDING, HIGH_FINDING, MEDIUM_FINDING, LOW_FINDING]
ALL_STATUS_FINDINGS = [
    OPEN_FINDING,
    ACKNOWLEDGED_FINDING,
    REMEDIATED_FINDING,
    EXCEPTION_GRANTED_FINDING,
    REOPENED_FINDING,
]
SERVICE_A_FINDINGS = [CRITICAL_FINDING, HIGH_FINDING]
SERVICE_B_FINDINGS = [MEDIUM_FINDING, LOW_FINDING]
SERVICE_C_FINDINGS = ALL_STATUS_FINDINGS
