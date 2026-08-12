"""Audit log test fixtures for WO-029.

Factory functions generating audit log entry dicts shaped like
``AuditLogRepository.insert()`` return values.  All UUIDs are stable
within a test session but randomly generated at import time so individual
test runs remain isolated.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any


def _now() -> datetime:
    return datetime.now(tz=timezone.utc)


def _base_row(
    actor_id: uuid.UUID | None,
    actor_role: str,
    action: str,
    resource_type: str,
    resource_id: uuid.UUID | None = None,
    before_state: dict[str, Any] | None = None,
    after_state: dict[str, Any] | None = None,
    ip_address_masked: str | None = "10.0.xxx.xxx",
    correlation_id: str | None = None,
) -> dict[str, Any]:
    return {
        "id": uuid.uuid4(),
        "actor_id": actor_id,
        "actor_role": actor_role,
        "action": action,
        "resource_type": resource_type,
        "resource_id": resource_id,
        "before_state": before_state,
        "after_state": after_state,
        "ip_address_masked": ip_address_masked,
        "correlation_id": correlation_id or str(uuid.uuid4()),
        "created_at": _now(),
    }


# ---------------------------------------------------------------------------
# Authentication event factories
# ---------------------------------------------------------------------------

def login_event(
    user_id: uuid.UUID | None = None,
    role: str = "developer",
    ip: str = "10.0.xxx.xxx",
) -> dict[str, Any]:
    """Successful login audit record."""
    uid = user_id or uuid.uuid4()
    return _base_row(
        actor_id=uid,
        actor_role=role,
        action="auth.login",
        resource_type="users",
        resource_id=uid,
        ip_address_masked=ip,
    )


def login_failed_event(
    user_id: uuid.UUID | None = None,
    reason: str = "invalid_credentials",
    ip: str = "10.0.xxx.xxx",
) -> dict[str, Any]:
    """Failed login audit record (actor_id may be None for unknown email)."""
    return _base_row(
        actor_id=user_id,
        actor_role="",
        action="auth.login_failed",
        resource_type="users",
        resource_id=user_id,
        after_state={"reason": reason},
        ip_address_masked=ip,
    )


def account_locked_event(
    user_id: uuid.UUID | None = None,
    role: str = "developer",
    duration_seconds: int = 60,
) -> dict[str, Any]:
    """Account lockout audit record."""
    uid = user_id or uuid.uuid4()
    return _base_row(
        actor_id=uid,
        actor_role=role,
        action="auth.account_locked",
        resource_type="users",
        resource_id=uid,
        after_state={"lockout_count": 1, "duration_seconds": duration_seconds},
    )


def token_refresh_event(
    user_id: uuid.UUID | None = None,
    role: str = "developer",
) -> dict[str, Any]:
    """Token refresh audit record."""
    uid = user_id or uuid.uuid4()
    return _base_row(
        actor_id=uid,
        actor_role=role,
        action="auth.token_refresh",
        resource_type="users",
        resource_id=uid,
    )


def logout_event(
    user_id: uuid.UUID | None = None,
    role: str = "developer",
) -> dict[str, Any]:
    """Logout audit record."""
    uid = user_id or uuid.uuid4()
    return _base_row(
        actor_id=uid,
        actor_role=role,
        action="auth.logout",
        resource_type="users",
        resource_id=uid,
    )


def password_changed_event(
    user_id: uuid.UUID | None = None,
    role: str = "developer",
) -> dict[str, Any]:
    """Password change audit record."""
    uid = user_id or uuid.uuid4()
    return _base_row(
        actor_id=uid,
        actor_role=role,
        action="auth.password_changed",
        resource_type="users",
        resource_id=uid,
    )


# ---------------------------------------------------------------------------
# RBAC mutation event factories
# ---------------------------------------------------------------------------

def role_change_event(
    admin_id: uuid.UUID | None = None,
    target_user_id: uuid.UUID | None = None,
    old_role: str = "developer",
    new_role: str = "tech_lead",
) -> dict[str, Any]:
    """Role change audit record (admin actor)."""
    aid = admin_id or uuid.uuid4()
    tid = target_user_id or uuid.uuid4()
    return _base_row(
        actor_id=aid,
        actor_role="platform_admin",
        action="role_change",
        resource_type="users",
        resource_id=tid,
        before_state={"role": old_role},
        after_state={"role": new_role},
    )


def status_change_event(
    admin_id: uuid.UUID | None = None,
    target_user_id: uuid.UUID | None = None,
    was_active: bool = True,
    is_now_active: bool = False,
) -> dict[str, Any]:
    """Status change audit record (admin actor)."""
    aid = admin_id or uuid.uuid4()
    tid = target_user_id or uuid.uuid4()
    return _base_row(
        actor_id=aid,
        actor_role="platform_admin",
        action="status_change",
        resource_type="users",
        resource_id=tid,
        before_state={"is_active": was_active},
        after_state={"is_active": is_now_active},
    )


# ---------------------------------------------------------------------------
# Convenience list of one of each event type
# ---------------------------------------------------------------------------

ALL_EVENT_TYPES: list[dict[str, Any]] = [
    login_event(),
    login_failed_event(),
    account_locked_event(),
    token_refresh_event(),
    logout_event(),
    password_changed_event(),
    role_change_event(),
    status_change_event(),
]
