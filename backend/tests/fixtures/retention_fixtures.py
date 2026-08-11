"""Test fixtures for data retention tests (WO-032).

Provides factory functions that generate record dicts for each data category
with configurable timestamps.  All fixtures are in-memory only — no database
required for unit tests.  Integration tests that need real DB rows can use
these dicts as INSERT payloads.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any


# ---------------------------------------------------------------------------
# Timestamp helpers
# ---------------------------------------------------------------------------

def _now() -> datetime:
    return datetime.now(tz=timezone.utc)


def ts_days_ago(days: int) -> datetime:
    """Return a UTC datetime ``days`` in the past."""
    return _now() - timedelta(days=days)


def ts_days_ahead(days: int) -> datetime:
    """Return a UTC datetime ``days`` in the future."""
    return _now() + timedelta(days=days)


# ---------------------------------------------------------------------------
# Assessment score fixtures
# ---------------------------------------------------------------------------

def make_assessment_score_record(
    *,
    created_at: datetime | None = None,
    age_days: int = 200,
) -> dict[str, Any]:
    """Return a dict matching the assessment_scores table schema."""
    return {
        "id": uuid.uuid4(),
        "assessment_id": uuid.uuid4(),
        "dimension_scores": {
            "security": 0.85,
            "test_coverage": 0.72,
            "dependency_hygiene": 0.91,
        },
        "contributing_factors": {
            "open_vulnerabilities": 2,
            "days_since_last_scan": 14,
        },
        "overall_score": 0.83,
        "created_at": created_at or ts_days_ago(age_days),
    }


def make_expired_assessment_score(age_days: int = 200) -> dict[str, Any]:
    """Return an assessment record older than the 180-day retention period."""
    return make_assessment_score_record(age_days=age_days)


def make_active_assessment_score(age_days: int = 30) -> dict[str, Any]:
    """Return an assessment record within the 180-day retention window."""
    return make_assessment_score_record(age_days=age_days)


# ---------------------------------------------------------------------------
# Finding fixtures
# ---------------------------------------------------------------------------

def make_finding_record(
    *,
    created_at: datetime | None = None,
    age_days: int = 200,
) -> dict[str, Any]:
    """Return a dict matching the findings table schema."""
    return {
        "id": uuid.uuid4(),
        "assessment_id": uuid.uuid4(),
        "title": "Missing security header: X-Content-Type-Options",
        "description": "The response does not include X-Content-Type-Options header.",
        "severity": "medium",
        "category": "security",
        "status": "open",
        "created_at": created_at or ts_days_ago(age_days),
        "updated_at": created_at or ts_days_ago(age_days),
    }


def make_expired_finding(age_days: int = 200) -> dict[str, Any]:
    return make_finding_record(age_days=age_days)


def make_active_finding(age_days: int = 30) -> dict[str, Any]:
    return make_finding_record(age_days=age_days)


# ---------------------------------------------------------------------------
# Release decision fixtures
# ---------------------------------------------------------------------------

def make_release_decision_record(
    *,
    created_at: datetime | None = None,
    age_days: int = 400,
) -> dict[str, Any]:
    """Return a dict matching the release_decisions table schema."""
    return {
        "id": uuid.uuid4(),
        "assessment_id": uuid.uuid4(),
        "outcome": "approve",
        "rationale": "All critical checks passed. Security score 0.92.",
        "comment": "Reviewed by tech lead on 2025-01-15.",
        "decided_by": uuid.uuid4(),
        "created_at": created_at or ts_days_ago(age_days),
    }


def make_expired_release_decision(age_days: int = 400) -> dict[str, Any]:
    return make_release_decision_record(age_days=age_days)


def make_active_release_decision(age_days: int = 30) -> dict[str, Any]:
    return make_release_decision_record(age_days=age_days)


# ---------------------------------------------------------------------------
# AI conversation fixtures
# ---------------------------------------------------------------------------

def make_ai_conversation_record(
    *,
    created_at: datetime | None = None,
    age_days: int = 100,
) -> dict[str, Any]:
    """Return a dict matching the ai_conversations table schema."""
    return {
        "id": uuid.uuid4(),
        "user_id": uuid.uuid4(),
        "title": "Security review Q&A",
        "message_count": 8,
        "created_at": created_at or ts_days_ago(age_days),
        "updated_at": created_at or ts_days_ago(age_days),
    }


def make_expired_ai_conversation(age_days: int = 100) -> dict[str, Any]:
    return make_ai_conversation_record(age_days=age_days)


def make_active_ai_conversation(age_days: int = 30) -> dict[str, Any]:
    return make_ai_conversation_record(age_days=age_days)


# ---------------------------------------------------------------------------
# Exception fixtures
# ---------------------------------------------------------------------------

def make_exception_record(
    *,
    expires_at: datetime | None = None,
    expired_days_ago: int = 35,
    created_at: datetime | None = None,
) -> dict[str, Any]:
    """Return a dict matching the exceptions table schema.

    Args:
        expires_at:        Explicit expires_at value.
        expired_days_ago:  Days since the exception expired (default 35 — past
                           the 30-day post-expiry retention window).
        created_at:        Explicit created_at; defaults to 2 months before expires_at.
    """
    if expires_at is None:
        expires_at = ts_days_ago(expired_days_ago)
    if created_at is None:
        created_at = expires_at - timedelta(days=60)
    return {
        "id": uuid.uuid4(),
        "finding_id": uuid.uuid4(),
        "user_id": uuid.uuid4(),
        "reason": "Accepted risk — tracked in security backlog #1234.",
        "expires_at": expires_at,
        "created_at": created_at,
    }


def make_purgeable_exception(expired_days_ago: int = 35) -> dict[str, Any]:
    """Exception past the 30-day post-expiry window — eligible for purge."""
    return make_exception_record(expired_days_ago=expired_days_ago)


def make_recently_expired_exception(expired_days_ago: int = 10) -> dict[str, Any]:
    """Exception that expired recently — still within the 30-day grace period."""
    return make_exception_record(expired_days_ago=expired_days_ago)


def make_active_exception(days_until_expiry: int = 30) -> dict[str, Any]:
    """Exception that has not yet expired."""
    expires_at = ts_days_ahead(days_until_expiry)
    created_at = _now() - timedelta(days=30)
    return make_exception_record(expires_at=expires_at, created_at=created_at)


# ---------------------------------------------------------------------------
# Bulk fixture generators
# ---------------------------------------------------------------------------

def make_expired_records_for_all_categories() -> dict[str, list[dict[str, Any]]]:
    """Return a dict of expired records for each category (3 each)."""
    return {
        "assessment_scores": [make_expired_assessment_score() for _ in range(3)],
        "findings": [make_expired_finding() for _ in range(3)],
        "release_decisions": [make_expired_release_decision() for _ in range(3)],
        "ai_conversations": [make_expired_ai_conversation() for _ in range(3)],
        "exceptions": [make_purgeable_exception() for _ in range(3)],
    }


def make_active_records_for_all_categories() -> dict[str, list[dict[str, Any]]]:
    """Return a dict of non-expired records for each category (2 each)."""
    return {
        "assessment_scores": [make_active_assessment_score() for _ in range(2)],
        "findings": [make_active_finding() for _ in range(2)],
        "release_decisions": [make_active_release_decision() for _ in range(2)],
        "ai_conversations": [make_active_ai_conversation() for _ in range(2)],
        "exceptions": [make_active_exception() for _ in range(2)],
    }
