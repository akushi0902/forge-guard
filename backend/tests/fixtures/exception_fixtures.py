"""Exception request test fixtures (WO-062).

Provides deterministic payloads and row shapes for unit and integration tests.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

# Deterministic IDs
FINDING_SECURITY_ID = uuid.UUID("33333333-0001-0001-0001-000000000001")
FINDING_CODE_QUALITY_ID = uuid.UUID("33333333-0002-0002-0002-000000000002")
FINDING_TEST_COVERAGE_ID = uuid.UUID("33333333-0003-0003-0003-000000000003")
FINDING_DOCUMENTATION_ID = uuid.UUID("33333333-0004-0004-0004-000000000004")
FINDING_OPS_READINESS_ID = uuid.UUID("33333333-0005-0005-0005-000000000005")

EXCEPTION_ID_1 = uuid.UUID("44444444-0001-0001-0001-000000000001")

_NOW = datetime.now(timezone.utc)
_FUTURE_30D = _NOW + timedelta(days=30)
_FUTURE_90D = _NOW + timedelta(days=89, hours=23)  # just under 90 days

# ---------------------------------------------------------------------------
# Finding rows (as returned by FindingRepository.get_by_id)
# ---------------------------------------------------------------------------

FINDING_SECURITY_ROW = {
    "id": FINDING_SECURITY_ID,
    "assessment_id": uuid.uuid4(),
    "service_id": uuid.uuid4(),
    "policy_rule_id": None,
    "severity": "critical",
    "dimension": "security",
    "status": "open",
    "title": "Critical CVE detected",
    "description": "A critical vulnerability was found.",
    "evidence": None,
    "ai_explanation": None,
    "confidence_score": None,
    "created_at": _NOW,
    "updated_at": _NOW,
}

FINDING_CODE_QUALITY_ROW = {
    "id": FINDING_CODE_QUALITY_ID,
    "assessment_id": uuid.uuid4(),
    "service_id": uuid.uuid4(),
    "policy_rule_id": None,
    "severity": "high",
    "dimension": "code_quality",
    "status": "open",
    "title": "High cyclomatic complexity",
    "description": "Function exceeds complexity threshold.",
    "evidence": None,
    "ai_explanation": None,
    "confidence_score": None,
    "created_at": _NOW,
    "updated_at": _NOW,
}

FINDING_TEST_COVERAGE_ROW = {
    "id": FINDING_TEST_COVERAGE_ID,
    "assessment_id": uuid.uuid4(),
    "service_id": uuid.uuid4(),
    "policy_rule_id": None,
    "severity": "medium",
    "dimension": "test_coverage",
    "status": "open",
    "title": "Test coverage below threshold",
    "description": "Line coverage is 65%, minimum is 80%.",
    "evidence": None,
    "ai_explanation": None,
    "confidence_score": None,
    "created_at": _NOW,
    "updated_at": _NOW,
}

FINDING_DOCUMENTATION_ROW = {
    "id": FINDING_DOCUMENTATION_ID,
    "assessment_id": uuid.uuid4(),
    "service_id": uuid.uuid4(),
    "policy_rule_id": None,
    "severity": "low",
    "dimension": "documentation",
    "status": "open",
    "title": "Missing API documentation",
    "description": "Public endpoint lacks docstring.",
    "evidence": None,
    "ai_explanation": None,
    "confidence_score": None,
    "created_at": _NOW,
    "updated_at": _NOW,
}

FINDING_OPS_READINESS_ROW = {
    "id": FINDING_OPS_READINESS_ID,
    "assessment_id": uuid.uuid4(),
    "service_id": uuid.uuid4(),
    "policy_rule_id": None,
    "severity": "high",
    "dimension": "operations_readiness",
    "status": "open",
    "title": "Missing health check endpoint",
    "description": "Service does not expose /health.",
    "evidence": None,
    "ai_explanation": None,
    "confidence_score": None,
    "created_at": _NOW,
    "updated_at": _NOW,
}

FINDING_RESOLVED_ROW = {
    **FINDING_CODE_QUALITY_ROW,
    "id": uuid.UUID("33333333-0006-0006-0006-000000000006"),
    "status": "resolved",
}

FINDING_SUPPRESSED_ROW = {
    **FINDING_CODE_QUALITY_ROW,
    "id": uuid.UUID("33333333-0007-0007-0007-000000000007"),
    "status": "suppressed",
}

# ---------------------------------------------------------------------------
# Valid exception request payloads
# ---------------------------------------------------------------------------

VALID_EXCEPTION_PAYLOAD = {
    "justification": "This vulnerability cannot be patched until Q3 due to vendor freeze.",
    "expires_at": _FUTURE_30D.isoformat(),
}

VALID_EXCEPTION_PAYLOAD_MAX = {
    "justification": "Long-standing known issue awaiting upstream library fix in next release.",
    "expires_at": _FUTURE_90D.isoformat(),
}

# ---------------------------------------------------------------------------
# Invalid exception request payloads
# ---------------------------------------------------------------------------

INVALID_JUSTIFICATION_TOO_SHORT = {
    "justification": "Too short",
    "expires_at": _FUTURE_30D.isoformat(),
}

INVALID_JUSTIFICATION_WHITESPACE = {
    "justification": "    " * 10,  # whitespace-only, trims to empty
    "expires_at": _FUTURE_30D.isoformat(),
}

INVALID_EXPIRES_AT_PAST = {
    "justification": "This vulnerability cannot be patched until Q3 due to vendor freeze.",
    "expires_at": (_NOW - timedelta(days=1)).isoformat(),
}

INVALID_EXPIRES_AT_TOO_FAR = {
    "justification": "This vulnerability cannot be patched until Q3 due to vendor freeze.",
    "expires_at": (_NOW + timedelta(days=91)).isoformat(),
}

INVALID_EXPIRES_AT_NOW = {
    "justification": "This vulnerability cannot be patched until Q3 due to vendor freeze.",
    "expires_at": _NOW.isoformat(),
}

# ---------------------------------------------------------------------------
# Exception row (as returned by ExceptionRepository.create)
# ---------------------------------------------------------------------------

EXCEPTION_ROW = {
    "id": EXCEPTION_ID_1,
    "finding_id": FINDING_SECURITY_ID,
    "requested_by": uuid.UUID("55555555-0001-0001-0001-000000000001"),
    "justification": "This vulnerability cannot be patched until Q3 due to vendor freeze.",
    "status": "pending",
    "approver_role": "security_reviewer",
    "decided_by": None,
    "decision_comment": None,
    "expires_at": _FUTURE_30D,
    "decided_at": None,
    "created_at": _NOW,
    "updated_at": _NOW,
}
