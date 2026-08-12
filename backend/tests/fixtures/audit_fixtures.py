"""Test fixtures for the audit logging module (WO-030).

Provides:
  - Sample AuditLog record dicts for each event type
  - Mock AuditService factory helper
  - Mock request objects with actor identity

All fixtures are in-memory only — no database required.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock


# ---------------------------------------------------------------------------
# Sample audit record dicts
# ---------------------------------------------------------------------------

_NOW = datetime(2026, 8, 11, 0, 0, 0, tzinfo=timezone.utc)


def make_audit_record(
    *,
    actor_id: str | None = None,
    actor_role: str = "developer",
    action: str = "service.created",
    resource_type: str = "services",
    resource_id: str | None = None,
    before_state: dict[str, Any] | None = None,
    after_state: dict[str, Any] | None = None,
    ip_address_masked: str = "10.0.0.xxx",
    correlation_id: str | None = None,
) -> dict[str, Any]:
    """Return a sample audit log record dict (matches DB schema)."""
    return {
        "id": str(uuid.uuid4()),
        "actor_id": actor_id or str(uuid.uuid4()),
        "actor_role": actor_role,
        "action": action,
        "resource_type": resource_type,
        "resource_id": resource_id or str(uuid.uuid4()),
        "before_state": before_state,
        "after_state": after_state,
        "ip_address_masked": ip_address_masked,
        "correlation_id": correlation_id or str(uuid.uuid4()),
        "created_at": _NOW,
    }


def create_audit_record() -> dict[str, Any]:
    return make_audit_record(
        action="service.created",
        before_state=None,
        after_state={"id": str(uuid.uuid4()), "name": "payments-api", "status": "active"},
    )


def update_audit_record() -> dict[str, Any]:
    resource_id = str(uuid.uuid4())
    return make_audit_record(
        action="service.updated",
        resource_id=resource_id,
        before_state={"id": resource_id, "name": "payments-api", "status": "active"},
        after_state={"id": resource_id, "name": "payments-api", "status": "deprecated"},
    )


def delete_audit_record() -> dict[str, Any]:
    resource_id = str(uuid.uuid4())
    return make_audit_record(
        action="service.deleted",
        resource_id=resource_id,
        before_state={"id": resource_id, "name": "old-service", "status": "active"},
        after_state=None,
    )


def auth_event_record() -> dict[str, Any]:
    return make_audit_record(
        action="user.login",
        resource_type="users",
        after_state={"result": "success"},
    )


def system_event_record() -> dict[str, Any]:
    return make_audit_record(
        actor_id=None,
        actor_role="system",
        action="partition.created",
        resource_type="audit_logs",
    )


ALL_SAMPLE_RECORDS: list[dict[str, Any]] = [
    create_audit_record(),
    update_audit_record(),
    delete_audit_record(),
    auth_event_record(),
    system_event_record(),
]


# ---------------------------------------------------------------------------
# Large diverse record factory — WO-031 (200+ seeded records)
# ---------------------------------------------------------------------------

_ACTIONS = [
    "auth.login",
    "auth.login_failed",
    "auth.logout",
    "auth.token_refresh",
    "auth.account_locked",
    "auth.password_changed",
    "rbac.role_change",
    "rbac.status_change",
    "service.created",
    "service.updated",
    "service.deleted",
    "assessment.requested",
    "assessment.completed",
    "release.approved",
    "release.blocked",
    "policy.created",
    "policy.updated",
    "exception.requested",
    "exception.approved",
    "user.created",
]

_RESOURCE_TYPES = [
    "users",
    "services",
    "assessments",
    "releases",
    "policies",
    "exceptions",
    "audit_logs",
    "refresh_tokens",
]

_ROLES = [
    "developer",
    "tech_lead",
    "security_reviewer",
    "platform_admin",
    "engineering_manager",
    "operator",
]

_IPS = [
    "10.0.xxx.xxx",
    "192.168.xxx.xxx",
    "172.16.xxx.xxx",
    "203.0.xxx.xxx",
    "unknown",
]

# Stable actor UUIDs for cross-test consistency.
_ACTOR_IDS = [uuid.UUID(f"a{i:07d}-0000-0000-0000-000000000000") for i in range(1, 11)]
_RESOURCE_IDS = [uuid.UUID(f"b{i:07d}-0000-0000-0000-000000000000") for i in range(1, 21)]


def generate_diverse_audit_records(count: int = 220) -> list[dict[str, Any]]:
    """Generate *count* diverse audit records spanning multiple actors, actions,
    resource types, and time periods.  Records are deterministic — given the same
    *count*, the output is always identical, enabling reproducible test assertions.
    """
    from datetime import timedelta  # noqa: PLC0415

    base_ts = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    records: list[dict[str, Any]] = []

    for i in range(count):
        # Spread across 3 months (Jan–Mar 2026).
        days_offset = (i * 90) // count
        created_at = base_ts + timedelta(days=days_offset, hours=i % 24, minutes=(i * 7) % 60)

        action = _ACTIONS[i % len(_ACTIONS)]
        resource_type = _RESOURCE_TYPES[i % len(_RESOURCE_TYPES)]
        role = _ROLES[i % len(_ROLES)]
        actor_id = _ACTOR_IDS[i % len(_ACTOR_IDS)]
        resource_id = _RESOURCE_IDS[i % len(_RESOURCE_IDS)]
        ip = _IPS[i % len(_IPS)]
        correlation_id = str(uuid.UUID(f"c{i:07d}-0000-0000-0000-000000000000"))

        before_state: dict[str, Any] | None = None
        after_state: dict[str, Any] | None = None
        if "change" in action or "updated" in action:
            before_state = {"status": "active", "version": i}
            after_state = {"status": "updated", "version": i + 1}
        elif action in {"rbac.role_change"}:
            before_state = {"role": _ROLES[(i + 1) % len(_ROLES)]}
            after_state = {"role": role}

        records.append({
            "id": uuid.UUID(f"d{i:07d}-0000-0000-0000-000000000000"),
            "actor_id": actor_id,
            "actor_role": role,
            "action": action,
            "resource_type": resource_type,
            "resource_id": resource_id,
            "before_state": before_state,
            "after_state": after_state,
            "ip_address_masked": ip,
            "correlation_id": correlation_id,
            "created_at": created_at,
        })

    return records


# 220 pre-generated diverse records for use in tests without a database.
SEEDED_AUDIT_RECORDS: list[dict[str, Any]] = generate_diverse_audit_records(220)


# ---------------------------------------------------------------------------
# Mock user context objects
# ---------------------------------------------------------------------------

def make_mock_user_context(
    *,
    user_id: str | None = None,
    role: str = "developer",
) -> MagicMock:
    """Return a mock ``request.state`` with actor identity fields."""
    state = MagicMock()
    state.actor_id = user_id or str(uuid.uuid4())
    state.user_role = role
    return state


# ---------------------------------------------------------------------------
# Mock AuditService
# ---------------------------------------------------------------------------

def make_mock_audit_service() -> MagicMock:
    """Return a mock :class:`~forgeguard.services.audit.AuditService`.

    ``log_event`` and ``log_mutation`` return a sample audit record.
    """
    svc = MagicMock()
    sample = create_audit_record()
    svc.log_event = AsyncMock(return_value=sample)
    svc.log_mutation = AsyncMock(return_value=sample)
    return svc


# ---------------------------------------------------------------------------
# Mock request objects
# ---------------------------------------------------------------------------

def make_mock_request(
    method: str = "POST",
    path: str = "/api/v1/services",
    role: str = "platform_admin",
    user_id: str | None = None,
    correlation_id: str | None = None,
) -> MagicMock:
    """Return a mock Starlette Request for middleware/service tests."""
    from forgeguard.core.audit_models import AuditContext  # noqa: PLC0415

    request = MagicMock()
    request.method = method
    request.url.path = path
    state = MagicMock()
    state.actor_id = user_id or str(uuid.uuid4())
    state.user_role = role
    state.correlation_id = correlation_id or str(uuid.uuid4())
    state.audit_context = AuditContext(
        correlation_id=state.correlation_id,
        client_ip_masked="192.168.1.xxx",
        http_method=method,
        request_path=path,
        resource_type="services",
        resource_id=str(uuid.uuid4()),
        before_state={"id": str(uuid.uuid4()), "name": "test-svc"},
    )
    request.state = state
    return request
