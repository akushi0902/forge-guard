"""Test fixtures for RBAC admin unit and integration tests (WO-028).

Provides factory functions that build pre-seeded user dicts across all six
roles, suitable for injecting into mocked UserRepository instances or writing
to a test database.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from forgeguard.core.permissions import UserRole


def _make_user(
    *,
    role: str,
    email: str,
    name: str = "",
    is_active: bool = True,
    user_id: uuid.UUID | None = None,
) -> dict:
    """Return a user row dict in the shape returned by UserRepository.get_by_id()."""
    now = datetime.now(tz=timezone.utc)
    return {
        "id": user_id or uuid.uuid4(),
        "email": email,
        "name_encrypted": name.encode("utf-8"),
        "password_hash": "$2b$04$" + "x" * 53,
        "role": role,
        "is_active": is_active,
        "failed_login_attempts": 0,
        "locked_until": None,
        "deleted_at": None,
        "created_at": now,
        "updated_at": now,
    }


def developer_user(user_id: uuid.UUID | None = None) -> dict:
    return _make_user(
        role=UserRole.developer.value,
        email="dev@example.com",
        name="Dev User",
        user_id=user_id,
    )


def tech_lead_user(user_id: uuid.UUID | None = None) -> dict:
    return _make_user(
        role=UserRole.tech_lead.value,
        email="tl@example.com",
        name="Tech Lead",
        user_id=user_id,
    )


def security_reviewer_user(user_id: uuid.UUID | None = None) -> dict:
    return _make_user(
        role=UserRole.security_reviewer.value,
        email="sr@example.com",
        name="Security Reviewer",
        user_id=user_id,
    )


def platform_admin_user(user_id: uuid.UUID | None = None) -> dict:
    return _make_user(
        role=UserRole.platform_admin.value,
        email="admin@example.com",
        name="Platform Admin",
        user_id=user_id,
    )


def engineering_manager_user(user_id: uuid.UUID | None = None) -> dict:
    return _make_user(
        role=UserRole.engineering_manager.value,
        email="em@example.com",
        name="Engineering Manager",
        user_id=user_id,
    )


def operator_user(user_id: uuid.UUID | None = None) -> dict:
    return _make_user(
        role=UserRole.operator.value,
        email="operator@example.com",
        name="Operator",
        user_id=user_id,
    )


#: One user per role — useful for seeding a test DB.
ALL_ROLE_USERS: list[dict] = [
    developer_user(),
    tech_lead_user(),
    security_reviewer_user(),
    platform_admin_user(),
    engineering_manager_user(),
    operator_user(),
]
