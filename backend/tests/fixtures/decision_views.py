"""Test fixtures for CombinedDecisionViewService and GET /api/v1/releases/{id}/decision (WO-052).

Scenarios covered:
    - APPROVE: high health, low risk, no critical security findings
    - CONDITIONAL_APPROVE: mid health, mid risk, high severity (non-critical) findings
    - BLOCK: low health, high risk, no findings
    - ESCALATED: high health, low risk, critical security finding → overrides APPROVE → BLOCK
    - PRE_DECISION: completed assessment with no human decision yet
    - POST_DECISION: completed assessment with human decision record
    - ZERO_FINDINGS: no findings in change_analysis
    - NO_SCORES: assessment with no score rows (partial evaluation)
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

# ---------------------------------------------------------------------------
# Canonical UUIDs
# ---------------------------------------------------------------------------

ASSESS_APPROVE = uuid.UUID("aa000000-0000-0000-0000-000000000001")
ASSESS_CONDITIONAL = uuid.UUID("aa000000-0000-0000-0000-000000000002")
ASSESS_BLOCK = uuid.UUID("aa000000-0000-0000-0000-000000000003")
ASSESS_ESCALATED = uuid.UUID("aa000000-0000-0000-0000-000000000004")
ASSESS_NO_SCORES = uuid.UUID("aa000000-0000-0000-0000-000000000005")
ASSESS_ZERO_FINDINGS = uuid.UUID("aa000000-0000-0000-0000-000000000006")

SERVICE_ID = uuid.UUID("bb000000-0000-0000-0000-000000000001")
DECISION_ID = uuid.UUID("cc000000-0000-0000-0000-000000000001")
REVIEWER_ID = uuid.UUID("dd000000-0000-0000-0000-000000000001")

_T = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
_TDONE = datetime(2026, 1, 1, 12, 5, 0, tzinfo=timezone.utc)

# ---------------------------------------------------------------------------
# Finding helpers
# ---------------------------------------------------------------------------

def _finding(
    fid: str,
    title: str,
    severity: str,
    dimension: str,
    explanation: str = "Detected by static analysis",
) -> dict[str, Any]:
    return {
        "id": fid,
        "title": title,
        "severity": severity,
        "dimension": dimension,
        "explanation": explanation,
        "business_impact": f"{severity.capitalize()} business impact",
        "remediation_steps": ["Step 1", "Step 2"],
        "confidence_score": 0.9,
        "source": "static_analysis",
    }


CRITICAL_SECURITY_FINDING = _finding(
    "f1000000-0000-0000-0000-000000000001",
    "SQL injection vulnerability",
    "critical",
    "security",
)

HIGH_CODE_QUALITY_FINDING = _finding(
    "f1000000-0000-0000-0000-000000000002",
    "High cyclomatic complexity",
    "high",
    "code_quality",
)

HIGH_DEPENDENCY_FINDING = _finding(
    "f1000000-0000-0000-0000-000000000003",
    "Outdated dependency with known CVE",
    "high",
    "dependency",
)

MEDIUM_FINDING = _finding(
    "f1000000-0000-0000-0000-000000000004",
    "Missing unit test coverage",
    "medium",
    "testing",
)

LOW_FINDING = _finding(
    "f1000000-0000-0000-0000-000000000005",
    "Minor code style violation",
    "low",
    "code_quality",
)


def _change_analysis(findings: list[dict[str, Any]]) -> str:
    return json.dumps({"findings": findings, "summary": {}})


# ---------------------------------------------------------------------------
# Assessment rows
# ---------------------------------------------------------------------------

def _base_assessment(aid: uuid.UUID, findings: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "id": aid,
        "service_id": SERVICE_ID,
        "status": "completed",
        "commit_sha": "a" * 40,
        "pr_reference": None,
        "change_analysis": _change_analysis(findings),
        "created_at": _T,
        "completed_at": _TDONE,
        "requested_by": None,
    }


ASSESSMENT_APPROVE = _base_assessment(ASSESS_APPROVE, [])
ASSESSMENT_CONDITIONAL = _base_assessment(
    ASSESS_CONDITIONAL, [HIGH_CODE_QUALITY_FINDING, HIGH_DEPENDENCY_FINDING, MEDIUM_FINDING]
)
ASSESSMENT_BLOCK = _base_assessment(ASSESS_BLOCK, [])
ASSESSMENT_ESCALATED = _base_assessment(
    ASSESS_ESCALATED, [CRITICAL_SECURITY_FINDING, LOW_FINDING]
)
ASSESSMENT_NO_SCORES = _base_assessment(ASSESS_NO_SCORES, [])
ASSESSMENT_ZERO_FINDINGS = _base_assessment(ASSESS_ZERO_FINDINGS, [])

# ---------------------------------------------------------------------------
# Score rows — health and risk
# ---------------------------------------------------------------------------

def _health_score(aid: uuid.UUID, overall: float, dims: dict | None = None) -> dict[str, Any]:
    dimension_scores = dims or {
        "code_quality": {"dimension": "code_quality", "score": overall, "total_rules": 10, "passed_rules": 8, "failed_rules": 2, "inconclusive_rules": 0, "error_rules": 0, "has_data": True},
        "security": {"dimension": "security", "score": overall, "total_rules": 10, "passed_rules": 8, "failed_rules": 2, "inconclusive_rules": 0, "error_rules": 0, "has_data": True},
    }
    return {
        "id": uuid.uuid4(),
        "assessment_id": aid,
        "service_id": SERVICE_ID,
        "score_type": "health",
        "overall_score": Decimal(str(overall)),
        "dimension_scores": json.dumps(dimension_scores),
        "contributing_factors": "[]",
        "weights_used": "{}",
        "created_at": _TDONE,
    }


def _risk_score(aid: uuid.UUID, overall: float) -> dict[str, Any]:
    factors = [
        {"metric_name": "deployment_frequency", "risk_contribution": str(overall * 0.5), "weight": 0.5},
        {"metric_name": "change_failure_rate", "risk_contribution": str(overall * 0.5), "weight": 0.5},
    ]
    return {
        "id": uuid.uuid4(),
        "assessment_id": aid,
        "service_id": SERVICE_ID,
        "score_type": "risk",
        "overall_score": Decimal(str(overall)),
        "dimension_scores": "{}",
        "contributing_factors": json.dumps(factors),
        "weights_used": "{}",
        "created_at": _TDONE,
    }


# APPROVE: health=80, risk=20 → APPROVE
HEALTH_APPROVE = _health_score(ASSESS_APPROVE, 80.0)
RISK_APPROVE = _risk_score(ASSESS_APPROVE, 20.0)

# CONDITIONAL: health=60, risk=50 → CONDITIONAL_APPROVE
HEALTH_CONDITIONAL = _health_score(ASSESS_CONDITIONAL, 60.0)
RISK_CONDITIONAL = _risk_score(ASSESS_CONDITIONAL, 50.0)

# BLOCK: health=40, risk=70 → BLOCK
HEALTH_BLOCK = _health_score(ASSESS_BLOCK, 40.0)
RISK_BLOCK = _risk_score(ASSESS_BLOCK, 70.0)

# ESCALATED: health=85, risk=15 → normally APPROVE but escalated to BLOCK
HEALTH_ESCALATED = _health_score(ASSESS_ESCALATED, 85.0)
RISK_ESCALATED = _risk_score(ASSESS_ESCALATED, 15.0)

# ZERO_FINDINGS: health=75, risk=25 → APPROVE
HEALTH_ZERO = _health_score(ASSESS_ZERO_FINDINGS, 75.0)
RISK_ZERO = _risk_score(ASSESS_ZERO_FINDINGS, 25.0)

# ---------------------------------------------------------------------------
# Human decision record
# ---------------------------------------------------------------------------

HUMAN_DECISION_APPROVE: dict[str, Any] = {
    "id": DECISION_ID,
    "release_assessment_id": ASSESS_APPROVE,
    "health_score_at_decision": Decimal("80.00"),
    "risk_score_at_decision": Decimal("20.00"),
    "decision": "APPROVE",
    "decided_by_role": "tech_lead",
    "decided_by": REVIEWER_ID,
    "rationale": "All quality gates passed and risk is acceptable for production",
    "comment": None,
    "was_escalated": False,
    "created_at": _TDONE,
}

HUMAN_DECISION_BLOCK: dict[str, Any] = {
    "id": uuid.UUID("cc000000-0000-0000-0000-000000000002"),
    "release_assessment_id": ASSESS_ESCALATED,
    "health_score_at_decision": Decimal("85.00"),
    "risk_score_at_decision": Decimal("15.00"),
    "decision": "BLOCK",
    "decided_by_role": "security_reviewer",
    "decided_by": REVIEWER_ID,
    "rationale": "SQL injection vulnerability requires immediate remediation",
    "comment": "Do not deploy until security finding is resolved",
    "was_escalated": True,
    "created_at": _TDONE,
}

# ---------------------------------------------------------------------------
# Scenario maps — convenience for parameterised tests
# ---------------------------------------------------------------------------

SCENARIOS = {
    "approve": {
        "assessment": ASSESSMENT_APPROVE,
        "health": HEALTH_APPROVE,
        "risk": RISK_APPROVE,
        "decisions": [],
        "expected_recommendation": "APPROVE",
    },
    "conditional": {
        "assessment": ASSESSMENT_CONDITIONAL,
        "health": HEALTH_CONDITIONAL,
        "risk": RISK_CONDITIONAL,
        "decisions": [],
        "expected_recommendation": "CONDITIONAL_APPROVE",
    },
    "block": {
        "assessment": ASSESSMENT_BLOCK,
        "health": HEALTH_BLOCK,
        "risk": RISK_BLOCK,
        "decisions": [],
        "expected_recommendation": "BLOCK",
    },
    "escalated": {
        "assessment": ASSESSMENT_ESCALATED,
        "health": HEALTH_ESCALATED,
        "risk": RISK_ESCALATED,
        "decisions": [],
        "expected_recommendation": "BLOCK",  # escalated despite high health
    },
    "post_decision": {
        "assessment": ASSESSMENT_APPROVE,
        "health": HEALTH_APPROVE,
        "risk": RISK_APPROVE,
        "decisions": [HUMAN_DECISION_APPROVE],
        "expected_recommendation": "APPROVE",
    },
    "no_scores": {
        "assessment": ASSESSMENT_NO_SCORES,
        "health": None,
        "risk": None,
        "decisions": [],
        "expected_recommendation": "BLOCK",  # default when no scores
    },
    "zero_findings": {
        "assessment": ASSESSMENT_ZERO_FINDINGS,
        "health": HEALTH_ZERO,
        "risk": RISK_ZERO,
        "decisions": [],
        "expected_recommendation": "APPROVE",
    },
}
