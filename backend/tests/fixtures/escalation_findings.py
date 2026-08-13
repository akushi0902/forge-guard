"""Test fixtures for security escalation scenarios (WO-050).

Provides pre-built finding collections covering all severity/dimension
permutations needed by SecurityEscalationService unit tests.

Usage:
    from tests.fixtures.escalation_findings import (
        CRITICAL_SECURITY_FINDING,
        HIGH_SECURITY_FINDING,
        CRITICAL_NON_SECURITY_FINDING,
        EMPTY_FINDINGS,
        ALL_ESCALATION_SCENARIOS,
    )
"""

from __future__ import annotations

import uuid

# ---------------------------------------------------------------------------
# Stable IDs for deterministic tests
# ---------------------------------------------------------------------------

_F1 = uuid.UUID("ee000000-0000-0000-0000-000000000001")
_F2 = uuid.UUID("ee000000-0000-0000-0000-000000000002")
_F3 = uuid.UUID("ee000000-0000-0000-0000-000000000003")
_F4 = uuid.UUID("ee000000-0000-0000-0000-000000000004")
_F5 = uuid.UUID("ee000000-0000-0000-0000-000000000005")
_F6 = uuid.UUID("ee000000-0000-0000-0000-000000000006")


def _finding(
    *,
    finding_id: uuid.UUID,
    severity: str,
    dimension: str,
    title: str,
) -> dict:
    """Minimal finding dict suitable for SecurityEscalationService.check_escalation()."""
    return {
        "id": str(finding_id),
        "severity": severity,
        "dimension": dimension,
        "title": title,
    }


# ---------------------------------------------------------------------------
# Single findings — one per severity × dimension combination of interest
# ---------------------------------------------------------------------------

CRITICAL_SECURITY_FINDING = _finding(
    finding_id=_F1,
    severity="critical",
    dimension="security",
    title="Critical CVE detected in dependency",
)

CRITICAL_CODE_QUALITY_FINDING = _finding(
    finding_id=_F2,
    severity="critical",
    dimension="code_quality",
    title="Critical complexity threshold exceeded",
)

HIGH_SECURITY_FINDING = _finding(
    finding_id=_F3,
    severity="high",
    dimension="security",
    title="High-severity secrets pattern detected",
)

HIGH_CODE_QUALITY_FINDING = _finding(
    finding_id=_F4,
    severity="high",
    dimension="code_quality",
    title="High cyclomatic complexity in payment handler",
)

MEDIUM_SECURITY_FINDING = _finding(
    finding_id=_F5,
    severity="medium",
    dimension="security",
    title="Medium-severity dependency outdated",
)

LOW_SECURITY_FINDING = _finding(
    finding_id=_F6,
    severity="low",
    dimension="security",
    title="Low-risk configuration note",
)

# ---------------------------------------------------------------------------
# Findings with non-security dimensions (should NOT trigger escalation)
# ---------------------------------------------------------------------------

NON_SECURITY_DIMENSIONS = [
    _finding(finding_id=uuid.UUID("ee000000-0000-0000-0000-0000000000a1"), severity="critical", dimension="code_quality",         title="Critical code quality"),
    _finding(finding_id=uuid.UUID("ee000000-0000-0000-0000-0000000000a2"), severity="critical", dimension="test_coverage",        title="Critical test coverage"),
    _finding(finding_id=uuid.UUID("ee000000-0000-0000-0000-0000000000a3"), severity="critical", dimension="documentation",        title="Critical documentation"),
    _finding(finding_id=uuid.UUID("ee000000-0000-0000-0000-0000000000a4"), severity="critical", dimension="operations_readiness", title="Critical ops readiness"),
]

# ---------------------------------------------------------------------------
# Multi-finding collections
# ---------------------------------------------------------------------------

EMPTY_FINDINGS: list[dict] = []

ONLY_HIGH_SECURITY_FINDINGS: list[dict] = [HIGH_SECURITY_FINDING]

ONLY_MEDIUM_SECURITY_FINDINGS: list[dict] = [MEDIUM_SECURITY_FINDING]

ONE_CRITICAL_SECURITY: list[dict] = [CRITICAL_SECURITY_FINDING]

MULTIPLE_CRITICAL_SECURITY: list[dict] = [
    CRITICAL_SECURITY_FINDING,
    _finding(
        finding_id=uuid.UUID("ee000000-0000-0000-0000-000000000007"),
        severity="critical",
        dimension="security",
        title="Second critical security violation",
    ),
    _finding(
        finding_id=uuid.UUID("ee000000-0000-0000-0000-000000000008"),
        severity="critical",
        dimension="security",
        title="Third critical security violation",
    ),
]

MIXED_WITH_CRITICAL_SECURITY: list[dict] = [
    HIGH_SECURITY_FINDING,       # should not escalate alone
    CRITICAL_SECURITY_FINDING,   # should escalate
    MEDIUM_SECURITY_FINDING,     # should not escalate
    HIGH_CODE_QUALITY_FINDING,   # should not escalate
]

ONLY_NON_SECURITY_CRITICALS: list[dict] = NON_SECURITY_DIMENSIONS

ALL_SEVERITIES_SECURITY_ONLY: list[dict] = [
    CRITICAL_SECURITY_FINDING,
    HIGH_SECURITY_FINDING,
    MEDIUM_SECURITY_FINDING,
    LOW_SECURITY_FINDING,
]

# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

FINDINGS_WITH_MISSING_FIELDS: list[dict] = [
    {"severity": "critical", "dimension": "security"},     # missing id + title
    {"id": str(uuid.uuid4()), "dimension": "security"},    # missing severity
    {"id": str(uuid.uuid4()), "severity": "critical"},     # missing dimension
    {},                                                      # fully empty
]

FINDINGS_WITH_UNKNOWN_SEVERITY: list[dict] = [
    {"id": str(uuid.uuid4()), "severity": "unknown_level", "dimension": "security", "title": "Unknown severity"},
]

# Perfect Health Score scenario — must still escalate
PERFECT_SCORE_WITH_CRITICAL_SECURITY: list[dict] = [
    CRITICAL_SECURITY_FINDING,
    HIGH_CODE_QUALITY_FINDING,
]
