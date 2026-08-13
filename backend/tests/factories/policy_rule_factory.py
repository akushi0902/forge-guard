"""Factory for the PolicyRule domain entity.

Uses a Python dataclass as the target because the SQLAlchemy PolicyRule model
has not been created yet.  Upgrade to ``SQLAlchemyModelFactory`` when the model
is available.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone

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


@dataclass
class PolicyRuleData:
    """In-memory representation of a PolicyRule domain entity."""

    id: uuid.UUID = field(default_factory=uuid.uuid4)
    name: str = ""
    dimension: str = "security"
    severity: str = "medium"
    threshold: float = 80.0
    description: str = ""
    is_enabled: bool = True
    created_at: datetime = field(
        default_factory=lambda: datetime.now(tz=timezone.utc)
    )
    updated_at: datetime = field(
        default_factory=lambda: datetime.now(tz=timezone.utc)
    )


class PolicyRuleFactory(factory.Factory):
    """Factory producing PolicyRuleData objects.

    Usage::

        rule = PolicyRuleFactory()
        rule = PolicyRuleFactory(dimension="security", severity="critical")
    """

    class Meta:
        model = PolicyRuleData

    id = factory.LazyFunction(uuid.uuid4)
    name = factory.Sequence(lambda n: f"rule-{n:04d}-{_fake.word()}")
    dimension = factory.Iterator(_DIMENSIONS)
    severity = factory.Iterator(_SEVERITIES)
    threshold = factory.LazyFunction(lambda: round(_fake.pyfloat(min_value=50, max_value=95), 1))
    description = factory.LazyFunction(lambda: _fake.sentence(nb_words=8))
    is_enabled = True
    created_at = factory.LazyFunction(lambda: datetime.now(tz=timezone.utc))
    updated_at = factory.LazyFunction(lambda: datetime.now(tz=timezone.utc))
