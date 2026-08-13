"""Test fixtures for GDPR data subject rights tests (WO-034).

Provides factory functions that generate a realistic user with associated
audit logs, assessments, and decisions for full lifecycle testing.

All fixtures are in-memory dicts — no database required.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

# ---------------------------------------------------------------------------
# Sentinel timestamp
# ---------------------------------------------------------------------------

_NOW = datetime(2026, 8, 11, 0, 0, 0, tzinfo=timezone.utc)

# ---------------------------------------------------------------------------
# Canonical test user
# ---------------------------------------------------------------------------

#: Pre-determined UUID used across all data subject fixtures for consistency.
DATA_SUBJECT_USER_ID = uuid.UUID("c2000000-0000-0000-0000-000000000002")
DATA_SUBJECT_EMAIL = "data.subject@example.com"
DATA_SUBJECT_NAME = "Data Subject User"
DATA_SUBJECT_ROLE = "developer"


def make_data_subject_user(
    *,
    user_id: uuid.UUID = DATA_SUBJECT_USER_ID,
    email: str = DATA_SUBJECT_EMAIL,
    name: str = DATA_SUBJECT_NAME,
    role: str = DATA_SUBJECT_ROLE,
    is_active: bool = True,
    deleted_at: datetime | None = None,
) -> dict[str, Any]:
    """Return a users-table row dict for a data subject test user."""
    return {
        "id": user_id,
        "email": email,
        "name_encrypted": name.encode("utf-8"),
        "password_hash": "$2b$12$PLACEHOLDER_HASH_FOR_TESTS_ONLY_XXXXXXXXXXXXXXXX",
        "role": role,
        "is_active": is_active,
        "failed_login_attempts": 0,
        "locked_until": None,
        "deleted_at": deleted_at,
        "created_at": _NOW,
        "updated_at": _NOW,
    }


# ---------------------------------------------------------------------------
# Audit log fixtures
# ---------------------------------------------------------------------------

def make_audit_log_for_user(
    *,
    actor_id: uuid.UUID = DATA_SUBJECT_USER_ID,
    action: str = "service.viewed",
    resource_type: str = "services",
    resource_id: uuid.UUID | None = None,
    after_state: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return a single audit_logs-table row dict referencing a specific user."""
    return {
        "id": uuid.uuid4(),
        "actor_id": actor_id,
        "actor_role": DATA_SUBJECT_ROLE,
        "action": action,
        "resource_type": resource_type,
        "resource_id": resource_id or uuid.uuid4(),
        "before_state": None,
        "after_state": after_state,
        "ip_address_masked": "10.0.0.xxx",
        "correlation_id": str(uuid.uuid4()),
        "created_at": _NOW,
    }


def make_audit_log_set(
    count: int = 10,
    *,
    actor_id: uuid.UUID = DATA_SUBJECT_USER_ID,
) -> list[dict[str, Any]]:
    """Return *count* audit_logs rows for the given actor_id."""
    actions = [
        "service.viewed",
        "assessment.requested",
        "decision.created",
        "policy.viewed",
        "auth.login",
        "auth.logout",
        "gdpr.access_data",
        "gdpr.export_data",
        "score.viewed",
        "finding.acknowledged",
    ]
    return [
        make_audit_log_for_user(
            actor_id=actor_id,
            action=actions[i % len(actions)],
        )
        for i in range(count)
    ]


# ---------------------------------------------------------------------------
# Assessment fixtures
# ---------------------------------------------------------------------------

def make_assessment_for_user(
    *,
    requested_by: uuid.UUID = DATA_SUBJECT_USER_ID,
    service_id: uuid.UUID | None = None,
    overall_score: float = 78.5,
    status: str = "completed",
) -> dict[str, Any]:
    """Return an assessments-table row dict requested by the given user."""
    return {
        "id": uuid.uuid4(),
        "service_id": service_id or uuid.uuid4(),
        "requested_by": requested_by,
        "overall_score": overall_score,
        "health_score": 82.0,
        "risk_score": 22.0,
        "commit_sha": "abc123def456",
        "status": status,
        "created_at": _NOW,
    }


def make_assessment_set(
    count: int = 3,
    *,
    requested_by: uuid.UUID = DATA_SUBJECT_USER_ID,
) -> list[dict[str, Any]]:
    """Return *count* assessment rows for the given user."""
    statuses = ["completed", "pending", "failed"]
    return [
        make_assessment_for_user(
            requested_by=requested_by,
            overall_score=70.0 + i * 5,
            status=statuses[i % len(statuses)],
        )
        for i in range(count)
    ]


# ---------------------------------------------------------------------------
# Decision fixtures
# ---------------------------------------------------------------------------

def make_decision_for_user(
    *,
    decided_by: uuid.UUID = DATA_SUBJECT_USER_ID,
    assessment_id: uuid.UUID | None = None,
    outcome: str = "approved",
    rationale: str = "All checks passed.",
) -> dict[str, Any]:
    """Return a release_decisions-table row dict for the given user."""
    return {
        "id": uuid.uuid4(),
        "assessment_id": assessment_id or uuid.uuid4(),
        "decided_by": decided_by,
        "outcome": outcome,
        "rationale": rationale,
        "comment": None,
        "conditions": None,
        "created_at": _NOW,
    }


def make_decision_set(
    count: int = 2,
    *,
    decided_by: uuid.UUID = DATA_SUBJECT_USER_ID,
) -> list[dict[str, Any]]:
    """Return *count* release_decision rows for the given user."""
    outcomes = ["approved", "rejected"]
    return [
        make_decision_for_user(
            decided_by=decided_by,
            outcome=outcomes[i % len(outcomes)],
        )
        for i in range(count)
    ]


# ---------------------------------------------------------------------------
# Full lifecycle bundle
# ---------------------------------------------------------------------------

def make_data_subject_bundle(
    *,
    user_id: uuid.UUID = DATA_SUBJECT_USER_ID,
    audit_count: int = 10,
    assessment_count: int = 3,
    decision_count: int = 2,
) -> dict[str, Any]:
    """Return a dict with a user row + all related records for lifecycle testing.

    Structure::

        {
            "user": { ... },
            "audit_logs": [ ... ],        # 10 entries
            "assessments": [ ... ],       # 3 entries
            "decisions": [ ... ],         # 2 entries
        }
    """
    return {
        "user": make_data_subject_user(user_id=user_id),
        "audit_logs": make_audit_log_set(audit_count, actor_id=user_id),
        "assessments": make_assessment_set(assessment_count, requested_by=user_id),
        "decisions": make_decision_set(decision_count, decided_by=user_id),
    }
