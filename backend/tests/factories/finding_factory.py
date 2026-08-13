"""Factory for the Finding domain entity.

Uses a Python dataclass as the target because the SQLAlchemy Finding model
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

_DIMENSIONS = (
    "test_coverage",
    "documentation",
    "security",
    "dependency_health",
    "code_quality",
)

_SEVERITIES = ("critical", "high", "medium", "low", "info")

_STATUSES = ("open", "in_progress", "resolved", "excepted")


@dataclass
class FindingData:
    """In-memory representation of a policy Finding domain entity."""

    id: uuid.UUID = field(default_factory=uuid.uuid4)
    service_id: uuid.UUID = field(default_factory=uuid.uuid4)
    policy_rule_id: uuid.UUID = field(default_factory=uuid.uuid4)
    dimension: str = "security"
    severity: str = "medium"
    title: str = ""
    description: str = ""
    status: str = "open"
    detected_at: datetime = field(
        default_factory=lambda: datetime.now(tz=timezone.utc)
    )
    resolved_at: Optional[datetime] = None


class FindingFactory(factory.Factory):
    """Factory producing FindingData objects with Faker-generated defaults.

    Usage::

        finding = FindingFactory()
        critical = FindingFactory(severity="critical", dimension="security")
        resolved = FindingFactory(status="resolved")
    """

    class Meta:
        model = FindingData

    id = factory.LazyFunction(uuid.uuid4)
    service_id = factory.LazyFunction(uuid.uuid4)
    policy_rule_id = factory.LazyFunction(uuid.uuid4)
    dimension = factory.Iterator(_DIMENSIONS)
    severity = factory.Iterator(_SEVERITIES)
    title = factory.LazyFunction(lambda: _fake.sentence(nb_words=6).rstrip("."))
    description = factory.LazyFunction(lambda: _fake.paragraph(nb_sentences=2))
    status = factory.Iterator(_STATUSES)
    detected_at = factory.LazyFunction(lambda: datetime.now(tz=timezone.utc))
    resolved_at = None
