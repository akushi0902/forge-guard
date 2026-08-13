"""Factory for the AuditLog domain entity.

Uses a Python dataclass as the target because the SQLAlchemy AuditLog model
has not been created yet.  Upgrade to ``SQLAlchemyModelFactory`` when available.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

import factory
from faker import Faker

_fake = Faker()

_ACTIONS = (
    "user.login",
    "user.logout",
    "release.approve",
    "release.block",
    "finding.create",
    "finding.resolve",
    "policy.update",
    "exception.request",
    "exception.approve",
)

_RESOURCE_TYPES = (
    "user",
    "service",
    "finding",
    "assessment",
    "policy_rule",
    "release_decision",
    "exception",
)

_ACTOR_ROLES = (
    "developer",
    "tech_lead",
    "security_reviewer",
    "platform_admin",
    "engineering_manager",
    "operator",
)


@dataclass
class AuditLogData:
    """In-memory representation of an immutable AuditLog entry."""

    id: uuid.UUID = field(default_factory=uuid.uuid4)
    actor_id: uuid.UUID = field(default_factory=uuid.uuid4)
    actor_role: str = "developer"
    action: str = "user.login"
    resource_type: str = "user"
    resource_id: uuid.UUID = field(default_factory=uuid.uuid4)
    before_state: Optional[dict] = None
    after_state: Optional[dict] = None
    request_id: Optional[str] = None
    ip_address: Optional[str] = None
    created_at: datetime = field(
        default_factory=lambda: datetime.now(tz=timezone.utc)
    )


class AuditLogFactory(factory.Factory):
    """Factory producing AuditLogData objects with Faker-generated defaults.

    Usage::

        log = AuditLogFactory()
        login_log = AuditLogFactory(action="user.login", actor_role="developer")
        mutation_log = AuditLogFactory(
            action="finding.resolve",
            before_state={"status": "open"},
            after_state={"status": "resolved"},
        )
    """

    class Meta:
        model = AuditLogData

    id = factory.LazyFunction(uuid.uuid4)
    actor_id = factory.LazyFunction(uuid.uuid4)
    actor_role = factory.Iterator(_ACTOR_ROLES)
    action = factory.Iterator(_ACTIONS)
    resource_type = factory.Iterator(_RESOURCE_TYPES)
    resource_id = factory.LazyFunction(uuid.uuid4)
    before_state = None
    after_state = None
    request_id = factory.LazyFunction(lambda: str(uuid.uuid4()))
    ip_address = factory.LazyFunction(lambda: _fake.ipv4_private())
    created_at = factory.LazyFunction(lambda: datetime.now(tz=timezone.utc))
