"""Severity classification test fixtures (WO-036).

Sample finding records at each severity level across security and non-security
dimensions.  These dicts represent the database row shape returned by the
FindingRepository (matching the ORM model column names).

Use in unit and integration tests to exercise the SeverityClassifier, risk
scoring weights, dashboard filtering, and escalation logic without a database.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from forgeguard.services.domain.severity import SeverityLevel

# ---------------------------------------------------------------------------
# Deterministic UUIDs for reproducible assertions
# ---------------------------------------------------------------------------

ASSESSMENT_ID = uuid.UUID("aaaaaaaa-0001-0001-0001-000000000001")
SERVICE_ID = uuid.UUID("bbbbbbbb-0001-0001-0001-000000000001")
POLICY_RULE_IDS: dict[str, uuid.UUID] = {
    "critical_security": uuid.UUID("cccccccc-0001-0001-0001-000000000001"),
    "critical_code": uuid.UUID("cccccccc-0002-0001-0001-000000000002"),
    "high_security": uuid.UUID("cccccccc-0003-0001-0001-000000000003"),
    "high_test": uuid.UUID("cccccccc-0004-0001-0001-000000000004"),
    "medium_security": uuid.UUID("cccccccc-0005-0001-0001-000000000005"),
    "medium_code": uuid.UUID("cccccccc-0006-0001-0001-000000000006"),
    "low_docs": uuid.UUID("cccccccc-0007-0001-0001-000000000007"),
    "low_ops": uuid.UUID("cccccccc-0008-0001-0001-000000000008"),
}

_TS = datetime(2026, 8, 12, 0, 0, 0, tzinfo=timezone.utc)

# ---------------------------------------------------------------------------
# CRITICAL findings
# ---------------------------------------------------------------------------

FINDING_CRITICAL_SECURITY: dict = {
    "id": uuid.UUID("dddddddd-0001-0001-0001-000000000001"),
    "assessment_id": ASSESSMENT_ID,
    "service_id": SERVICE_ID,
    "policy_rule_id": POLICY_RULE_IDS["critical_security"],
    "severity": SeverityLevel.CRITICAL,
    "dimension": "security",
    "status": "open",
    "title": "Critical CVE detected in runtime dependency",
    "description": "CVE-2026-99999 (CVSS 9.8) found in cryptography==3.4.8",
    "evidence": {"cve_id": "CVE-2026-99999", "cvss_score": 9.8, "package": "cryptography"},
    "ai_explanation": None,
    "confidence_score": None,
    # escalation_required=True: CRITICAL + security dimension
    "escalation_required": True,
    "resolved_at": None,
    "created_at": _TS,
    "updated_at": _TS,
}

FINDING_CRITICAL_CODE_QUALITY: dict = {
    "id": uuid.UUID("dddddddd-0002-0002-0002-000000000002"),
    "assessment_id": ASSESSMENT_ID,
    "service_id": SERVICE_ID,
    "policy_rule_id": POLICY_RULE_IDS["critical_code"],
    "severity": SeverityLevel.CRITICAL,
    "dimension": "code_quality",
    "status": "open",
    "title": "Cyclomatic complexity exceeds maximum threshold",
    "description": "Function process_payload has complexity of 45 (limit: 10)",
    "evidence": {"function": "process_payload", "complexity": 45, "threshold": 10},
    "ai_explanation": None,
    "confidence_score": None,
    # escalation_required=False: CRITICAL but NOT security dimension
    "escalation_required": False,
    "resolved_at": None,
    "created_at": _TS,
    "updated_at": _TS,
}

# ---------------------------------------------------------------------------
# HIGH findings
# ---------------------------------------------------------------------------

FINDING_HIGH_SECURITY: dict = {
    "id": uuid.UUID("dddddddd-0003-0003-0003-000000000003"),
    "assessment_id": ASSESSMENT_ID,
    "service_id": SERVICE_ID,
    "policy_rule_id": POLICY_RULE_IDS["high_security"],
    "severity": SeverityLevel.HIGH,
    "dimension": "security",
    "status": "open",
    "title": "SAST score below minimum threshold",
    "description": "SAST scan returned score 65 (minimum required: 80)",
    "evidence": {"sast_score": 65, "threshold": 80, "tool": "semgrep"},
    "ai_explanation": None,
    "confidence_score": None,
    "escalation_required": False,
    "resolved_at": None,
    "created_at": _TS,
    "updated_at": _TS,
}

FINDING_HIGH_TEST_COVERAGE: dict = {
    "id": uuid.UUID("dddddddd-0004-0004-0004-000000000004"),
    "assessment_id": ASSESSMENT_ID,
    "service_id": SERVICE_ID,
    "policy_rule_id": POLICY_RULE_IDS["high_test"],
    "severity": SeverityLevel.HIGH,
    "dimension": "test_coverage",
    "status": "in_progress",
    "title": "Line coverage below 80% threshold",
    "description": "Current line coverage: 62% (minimum required: 80%)",
    "evidence": {"line_coverage": 62, "threshold": 80},
    "ai_explanation": None,
    "confidence_score": None,
    "escalation_required": False,
    "resolved_at": None,
    "created_at": _TS,
    "updated_at": _TS,
}

# ---------------------------------------------------------------------------
# MEDIUM findings
# ---------------------------------------------------------------------------

FINDING_MEDIUM_SECURITY: dict = {
    "id": uuid.UUID("dddddddd-0005-0005-0005-000000000005"),
    "assessment_id": ASSESSMENT_ID,
    "service_id": SERVICE_ID,
    "policy_rule_id": POLICY_RULE_IDS["medium_security"],
    "severity": SeverityLevel.MEDIUM,
    "dimension": "security",
    "status": "open",
    "title": "Dependency license check failed",
    "description": "Package async-utils uses GPL-3.0 license (only MIT/Apache/BSD allowed)",
    "evidence": {"package": "async-utils", "license": "GPL-3.0"},
    "ai_explanation": None,
    "confidence_score": None,
    "escalation_required": False,
    "resolved_at": None,
    "created_at": _TS,
    "updated_at": _TS,
}

FINDING_MEDIUM_CODE_QUALITY: dict = {
    "id": uuid.UUID("dddddddd-0006-0006-0006-000000000006"),
    "assessment_id": ASSESSMENT_ID,
    "service_id": SERVICE_ID,
    "policy_rule_id": POLICY_RULE_IDS["medium_code"],
    "severity": SeverityLevel.MEDIUM,
    "dimension": "code_quality",
    "status": "open",
    "title": "Function length exceeds maximum",
    "description": "Function render_report has 78 lines (limit: 50)",
    "evidence": {"function": "render_report", "length": 78, "limit": 50},
    "ai_explanation": None,
    "confidence_score": None,
    "escalation_required": False,
    "resolved_at": None,
    "created_at": _TS,
    "updated_at": _TS,
}

# ---------------------------------------------------------------------------
# LOW findings
# ---------------------------------------------------------------------------

FINDING_LOW_DOCUMENTATION: dict = {
    "id": uuid.UUID("dddddddd-0007-0007-0007-000000000007"),
    "assessment_id": ASSESSMENT_ID,
    "service_id": SERVICE_ID,
    "policy_rule_id": POLICY_RULE_IDS["low_docs"],
    "severity": SeverityLevel.LOW,
    "dimension": "documentation",
    "status": "open",
    "title": "TODO comment detected in production code",
    "description": "Found TODO comment in src/api/routes/releases.py",
    "evidence": {"file": "src/api/routes/releases.py", "line": 42, "text": "# TODO: add pagination"},
    "ai_explanation": None,
    "confidence_score": None,
    "escalation_required": False,
    "resolved_at": None,
    "created_at": _TS,
    "updated_at": _TS,
}

FINDING_LOW_OPERATIONS: dict = {
    "id": uuid.UUID("dddddddd-0008-0008-0008-000000000008"),
    "assessment_id": ASSESSMENT_ID,
    "service_id": SERVICE_ID,
    "policy_rule_id": POLICY_RULE_IDS["low_ops"],
    "severity": SeverityLevel.LOW,
    "dimension": "operations_readiness",
    "status": "suppressed",
    "title": "Missing docstring on public function",
    "description": "Function validate_request has no docstring",
    "evidence": {"function": "validate_request", "module": "utils.validation"},
    "ai_explanation": None,
    "confidence_score": None,
    "escalation_required": False,
    "resolved_at": None,
    "created_at": _TS,
    "updated_at": _TS,
}

# ---------------------------------------------------------------------------
# Aggregated collections
# ---------------------------------------------------------------------------

ALL_FINDINGS: list[dict] = [
    FINDING_CRITICAL_SECURITY,
    FINDING_CRITICAL_CODE_QUALITY,
    FINDING_HIGH_SECURITY,
    FINDING_HIGH_TEST_COVERAGE,
    FINDING_MEDIUM_SECURITY,
    FINDING_MEDIUM_CODE_QUALITY,
    FINDING_LOW_DOCUMENTATION,
    FINDING_LOW_OPERATIONS,
]

FINDINGS_BY_SEVERITY: dict[SeverityLevel, list[dict]] = {
    SeverityLevel.CRITICAL: [FINDING_CRITICAL_SECURITY, FINDING_CRITICAL_CODE_QUALITY],
    SeverityLevel.HIGH: [FINDING_HIGH_SECURITY, FINDING_HIGH_TEST_COVERAGE],
    SeverityLevel.MEDIUM: [FINDING_MEDIUM_SECURITY, FINDING_MEDIUM_CODE_QUALITY],
    SeverityLevel.LOW: [FINDING_LOW_DOCUMENTATION, FINDING_LOW_OPERATIONS],
}

# Findings that must trigger escalation (CRITICAL + security dimension only)
ESCALATION_FINDINGS: list[dict] = [FINDING_CRITICAL_SECURITY]

# Findings that must NOT trigger escalation (all other combinations)
NON_ESCALATION_FINDINGS: list[dict] = [
    f for f in ALL_FINDINGS if f not in ESCALATION_FINDINGS
]
