"""Test fixtures for decision_assignments (WO-053).

Provides pre-built assignment dicts and factory helpers for unit and integration
tests covering the DecisionRouter, pending queue endpoints, and expiration logic.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

# Fixed UUIDs for test stability.
ASSESSMENT_ID_PENDING_TECH_LEAD = uuid.UUID("d1000000-0000-0000-0000-000000000001")
ASSESSMENT_ID_PENDING_SECURITY = uuid.UUID("d1000000-0000-0000-0000-000000000002")
ASSESSMENT_ID_COMPLETED = uuid.UUID("d1000000-0000-0000-0000-000000000003")
ASSESSMENT_ID_EXPIRED = uuid.UUID("d1000000-0000-0000-0000-000000000004")

ASSIGNMENT_ID_TECH_LEAD = uuid.UUID("a1000000-0000-0000-0000-000000000001")
ASSIGNMENT_ID_SECURITY = uuid.UUID("a1000000-0000-0000-0000-000000000002")
ASSIGNMENT_ID_COMPLETED = uuid.UUID("a1000000-0000-0000-0000-000000000003")
ASSIGNMENT_ID_EXPIRED = uuid.UUID("a1000000-0000-0000-0000-000000000004")

REVIEWER_USER_ID = uuid.UUID("e1000000-0000-0000-0000-000000000001")
SERVICE_ID = uuid.UUID("f1000000-0000-0000-0000-000000000001")

_NOW = datetime(2026, 8, 12, 12, 0, 0, tzinfo=timezone.utc)
_25_HOURS_AGO = _NOW - timedelta(hours=25)
_1_HOUR_AGO = _NOW - timedelta(hours=1)
_5_MIN_AGO = _NOW - timedelta(minutes=5)


def make_assignment(
    *,
    id: uuid.UUID | None = None,
    release_assessment_id: uuid.UUID | None = None,
    assigned_role: str = "tech_lead",
    assigned_at: datetime | None = None,
    status: str = "pending",
    completed_by: uuid.UUID | None = None,
    completed_at: datetime | None = None,
    service_id: uuid.UUID | None = None,
    commit_sha: str | None = "abc123def456abc123def456abc123def456abc1",
    pr_reference: str | None = None,
) -> dict[str, Any]:
    """Build a decision_assignment row dict."""
    now = _NOW
    return {
        "id": id or uuid.uuid4(),
        "release_assessment_id": release_assessment_id or uuid.uuid4(),
        "assigned_role": assigned_role,
        "assigned_at": assigned_at or now,
        "status": status,
        "completed_by": completed_by,
        "completed_at": completed_at,
        "service_id": service_id or SERVICE_ID,
        "commit_sha": commit_sha,
        "pr_reference": pr_reference,
        "created_at": assigned_at or now,
        "updated_at": assigned_at or now,
    }


# ---------------------------------------------------------------------------
# Pre-built assignment scenarios
# ---------------------------------------------------------------------------

PENDING_TECH_LEAD_ASSIGNMENT = make_assignment(
    id=ASSIGNMENT_ID_TECH_LEAD,
    release_assessment_id=ASSESSMENT_ID_PENDING_TECH_LEAD,
    assigned_role="tech_lead",
    status="pending",
    assigned_at=_1_HOUR_AGO,
)

PENDING_SECURITY_ASSIGNMENT = make_assignment(
    id=ASSIGNMENT_ID_SECURITY,
    release_assessment_id=ASSESSMENT_ID_PENDING_SECURITY,
    assigned_role="security_reviewer",
    status="pending",
    assigned_at=_1_HOUR_AGO,
)

COMPLETED_ASSIGNMENT = make_assignment(
    id=ASSIGNMENT_ID_COMPLETED,
    release_assessment_id=ASSESSMENT_ID_COMPLETED,
    assigned_role="tech_lead",
    status="completed",
    assigned_at=_5_MIN_AGO,
    completed_by=REVIEWER_USER_ID,
    completed_at=_NOW,
)

EXPIRED_ASSIGNMENT = make_assignment(
    id=ASSIGNMENT_ID_EXPIRED,
    release_assessment_id=ASSESSMENT_ID_EXPIRED,
    assigned_role="tech_lead",
    status="expired",
    assigned_at=_25_HOURS_AGO,
)

# Collected list for parametrized tests covering all statuses / roles.
ALL_ASSIGNMENT_FIXTURES: list[dict[str, Any]] = [
    PENDING_TECH_LEAD_ASSIGNMENT,
    PENDING_SECURITY_ASSIGNMENT,
    COMPLETED_ASSIGNMENT,
    EXPIRED_ASSIGNMENT,
]
