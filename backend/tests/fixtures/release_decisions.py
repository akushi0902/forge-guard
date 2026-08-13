"""Test fixtures for Release Decision endpoint tests (WO-051).

Pre-built data structures for:
    - Release assessments in various states (pending, in_progress, completed)
    - Assessment score records (health and risk) keyed to assessment_ids
    - Mock request objects for each of the six user roles
    - Valid and invalid ReleaseDecisionRequest bodies
    - Expected response shapes for contract verification
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock, MagicMock

from forgeguard.core.permissions import UserRole

# ---------------------------------------------------------------------------
# Canonical UUIDs — stable across all test files
# ---------------------------------------------------------------------------

ASSESSMENT_ID_COMPLETED: uuid.UUID = uuid.UUID("aaaaaaaa-0000-0000-0000-000000000001")
ASSESSMENT_ID_PENDING: uuid.UUID = uuid.UUID("aaaaaaaa-0000-0000-0000-000000000002")
ASSESSMENT_ID_IN_PROGRESS: uuid.UUID = uuid.UUID("aaaaaaaa-0000-0000-0000-000000000003")
ASSESSMENT_ID_ALREADY_DECIDED: uuid.UUID = uuid.UUID("aaaaaaaa-0000-0000-0000-000000000004")
ASSESSMENT_ID_MISSING_HEALTH: uuid.UUID = uuid.UUID("aaaaaaaa-0000-0000-0000-000000000005")
ASSESSMENT_ID_MISSING_RISK: uuid.UUID = uuid.UUID("aaaaaaaa-0000-0000-0000-000000000006")
ASSESSMENT_ID_WITH_ESCALATION: uuid.UUID = uuid.UUID("aaaaaaaa-0000-0000-0000-000000000007")
ASSESSMENT_ID_MISSING_BOTH: uuid.UUID = uuid.UUID("aaaaaaaa-0000-0000-0000-000000000008")

SERVICE_ID: uuid.UUID = uuid.UUID("bbbbbbbb-0000-0000-0000-000000000001")
EXISTING_DECISION_ID: uuid.UUID = uuid.UUID("cccccccc-0000-0000-0000-000000000001")

# ---------------------------------------------------------------------------
# Assessment rows
# ---------------------------------------------------------------------------

_BASE_ASSESSMENT: dict[str, Any] = {
    "service_id": SERVICE_ID,
    "commit_sha": "a" * 40,
    "pr_reference": None,
    "change_analysis": None,
    "created_at": datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
    "completed_at": datetime(2026, 1, 1, 12, 5, 0, tzinfo=timezone.utc),
    "requested_by": None,
}

COMPLETED_ASSESSMENT: dict[str, Any] = {
    **_BASE_ASSESSMENT,
    "id": ASSESSMENT_ID_COMPLETED,
    "status": "completed",
}

PENDING_ASSESSMENT: dict[str, Any] = {
    **_BASE_ASSESSMENT,
    "id": ASSESSMENT_ID_PENDING,
    "status": "pending",
    "completed_at": None,
}

IN_PROGRESS_ASSESSMENT: dict[str, Any] = {
    **_BASE_ASSESSMENT,
    "id": ASSESSMENT_ID_IN_PROGRESS,
    "status": "in_progress",
    "completed_at": None,
}

ALREADY_DECIDED_ASSESSMENT: dict[str, Any] = {
    **_BASE_ASSESSMENT,
    "id": ASSESSMENT_ID_ALREADY_DECIDED,
    "status": "completed",
}

COMPLETED_ASSESSMENT_WITH_ESCALATION: dict[str, Any] = {
    **_BASE_ASSESSMENT,
    "id": ASSESSMENT_ID_WITH_ESCALATION,
    "status": "completed",
    "change_analysis": {
        "findings": [
            {
                "id": str(uuid.UUID("dddddddd-0000-0000-0000-000000000001")),
                "title": "SQL injection vulnerability",
                "severity": "critical",
                "dimension": "security",
                "explanation": "Unsanitised input passed to DB query",
                "business_impact": "Data breach risk",
                "remediation_steps": ["Use parameterised queries"],
                "confidence_score": 0.95,
                "source": "static_analysis",
            }
        ],
        "summary": {},
    },
}

# Assessment with missing health score
ASSESSMENT_MISSING_HEALTH: dict[str, Any] = {
    **_BASE_ASSESSMENT,
    "id": ASSESSMENT_ID_MISSING_HEALTH,
    "status": "completed",
}

# Assessment with missing risk score
ASSESSMENT_MISSING_RISK: dict[str, Any] = {
    **_BASE_ASSESSMENT,
    "id": ASSESSMENT_ID_MISSING_RISK,
    "status": "completed",
}

# Assessment with both scores missing
ASSESSMENT_MISSING_BOTH: dict[str, Any] = {
    **_BASE_ASSESSMENT,
    "id": ASSESSMENT_ID_MISSING_BOTH,
    "status": "completed",
}

# ---------------------------------------------------------------------------
# Score rows
# ---------------------------------------------------------------------------

HEALTH_SCORE_ROW: dict[str, Any] = {
    "id": uuid.UUID("eeeeeeee-0000-0000-0000-000000000001"),
    "assessment_id": ASSESSMENT_ID_COMPLETED,
    "service_id": SERVICE_ID,
    "score_type": "health",
    "overall_score": Decimal("72.50"),
    "dimension_scores": {},
    "contributing_factors": [],
    "weights_used": {},
    "created_at": datetime(2026, 1, 1, 12, 4, 0, tzinfo=timezone.utc),
}

RISK_SCORE_ROW: dict[str, Any] = {
    "id": uuid.UUID("eeeeeeee-0000-0000-0000-000000000002"),
    "assessment_id": ASSESSMENT_ID_COMPLETED,
    "service_id": SERVICE_ID,
    "score_type": "risk",
    "overall_score": Decimal("28.00"),
    "dimension_scores": {},
    "contributing_factors": [],
    "weights_used": {},
    "created_at": datetime(2026, 1, 1, 12, 4, 30, tzinfo=timezone.utc),
}

ESCALATION_HEALTH_SCORE_ROW: dict[str, Any] = {
    **HEALTH_SCORE_ROW,
    "id": uuid.UUID("eeeeeeee-0000-0000-0000-000000000003"),
    "assessment_id": ASSESSMENT_ID_WITH_ESCALATION,
    "overall_score": Decimal("85.00"),
}

ESCALATION_RISK_SCORE_ROW: dict[str, Any] = {
    **RISK_SCORE_ROW,
    "id": uuid.UUID("eeeeeeee-0000-0000-0000-000000000004"),
    "assessment_id": ASSESSMENT_ID_WITH_ESCALATION,
    "overall_score": Decimal("20.00"),
}

# ---------------------------------------------------------------------------
# Existing decision (for duplicate-check tests)
# ---------------------------------------------------------------------------

EXISTING_DECISION_ROW: dict[str, Any] = {
    "id": EXISTING_DECISION_ID,
    "release_assessment_id": ASSESSMENT_ID_ALREADY_DECIDED,
    "health_score_at_decision": Decimal("72.50"),
    "risk_score_at_decision": Decimal("28.00"),
    "decision": "APPROVE",
    "decided_by_role": "tech_lead",
    "decided_by": uuid.UUID("ffffffff-0000-0000-0000-000000000001"),
    "rationale": "All checks passed, safe to deploy",
    "comment": None,
    "was_escalated": False,
    "created_at": datetime(2026, 1, 2, 9, 0, 0, tzinfo=timezone.utc),
}

# ---------------------------------------------------------------------------
# Request bodies
# ---------------------------------------------------------------------------

APPROVE_REQUEST: dict[str, Any] = {
    "decision": "APPROVE",
    "rationale": "All quality gates passed and risk is acceptable",
}

BLOCK_REQUEST: dict[str, Any] = {
    "decision": "BLOCK",
    "rationale": "Critical defects found in the security dimension",
}

CONDITIONAL_APPROVE_REQUEST: dict[str, Any] = {
    "decision": "CONDITIONAL_APPROVE",
    "rationale": "Minor issues found, deployment can proceed with monitoring",
    "comment": "Revisit within 72 hours",
}

# Invalid request bodies
REQUEST_MISSING_RATIONALE: dict[str, Any] = {
    "decision": "APPROVE",
}

REQUEST_RATIONALE_TOO_SHORT: dict[str, Any] = {
    "decision": "APPROVE",
    "rationale": "Too short",  # < 10 chars
}

REQUEST_NO_DECISION: dict[str, Any] = {
    "rationale": "All quality gates passed and risk is acceptable",
}

REQUEST_INVALID_DECISION: dict[str, Any] = {
    "decision": "MAYBE",
    "rationale": "All quality gates passed and risk is acceptable",
}

# ---------------------------------------------------------------------------
# Mock request helpers — one per role
# ---------------------------------------------------------------------------

_USER_ID = uuid.UUID("11111111-0000-0000-0000-000000000001")


def _make_request(role: str, user_id: uuid.UUID = _USER_ID) -> MagicMock:
    req = MagicMock()
    req.state = MagicMock()
    req.state.user_role = role
    req.state.user_id = user_id
    return req


def tech_lead_request() -> MagicMock:
    return _make_request(UserRole.tech_lead.value)


def security_reviewer_request() -> MagicMock:
    return _make_request(UserRole.security_reviewer.value)


def platform_admin_request() -> MagicMock:
    return _make_request(UserRole.platform_admin.value)


def developer_request() -> MagicMock:
    return _make_request(UserRole.developer.value)


def engineering_manager_request() -> MagicMock:
    return _make_request(UserRole.engineering_manager.value)


def operator_request() -> MagicMock:
    return _make_request(UserRole.operator.value)


ALL_ROLE_REQUESTS: dict[str, MagicMock] = {
    UserRole.tech_lead.value: tech_lead_request(),
    UserRole.security_reviewer.value: security_reviewer_request(),
    UserRole.platform_admin.value: platform_admin_request(),
    UserRole.developer.value: developer_request(),
    UserRole.engineering_manager.value: engineering_manager_request(),
    UserRole.operator.value: operator_request(),
}

# ---------------------------------------------------------------------------
# Roles expected to pass RBAC (have RELEASE_APPROVE or RELEASE_BLOCK)
# ---------------------------------------------------------------------------

AUTHORIZED_ROLES: list[str] = [
    UserRole.tech_lead.value,
    UserRole.security_reviewer.value,
    UserRole.platform_admin.value,
]

UNAUTHORIZED_ROLES: list[str] = [
    UserRole.developer.value,
    UserRole.engineering_manager.value,
    UserRole.operator.value,
]
