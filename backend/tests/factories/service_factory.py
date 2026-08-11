"""Factory for the Service domain entity.

Uses a Python dataclass as the target model because the SQLAlchemy Service
model has not been created yet (future WO).  When the model is added, update
``Meta.model`` to the SQLAlchemy class and switch to ``SQLAlchemyModelFactory``.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

import factory
from faker import Faker

_fake = Faker()


@dataclass
class ServiceData:
    """In-memory representation of a Service domain entity."""

    id: uuid.UUID = field(default_factory=uuid.uuid4)
    name: str = ""
    team: str = ""
    repository_url: str = ""
    last_evaluated_at: Optional[datetime] = None
    created_at: datetime = field(
        default_factory=lambda: datetime.now(tz=timezone.utc)
    )
    updated_at: datetime = field(
        default_factory=lambda: datetime.now(tz=timezone.utc)
    )


class ServiceFactory(factory.Factory):
    """Factory producing ServiceData objects with Faker-generated defaults.

    Usage::

        svc = ServiceFactory()
        assert svc.name.endswith("-service")

        svc = ServiceFactory(name="payment-api", team="Platform")
    """

    class Meta:
        model = ServiceData

    id = factory.LazyFunction(uuid.uuid4)
    name = factory.Sequence(lambda n: f"service-{n:03d}")
    team = factory.LazyFunction(lambda: _fake.word().capitalize() + " Team")
    repository_url = factory.LazyAttribute(
        lambda obj: f"https://github.com/acme/{obj.name}"
    )
    last_evaluated_at = None
    created_at = factory.LazyFunction(lambda: datetime.now(tz=timezone.utc))
    updated_at = factory.LazyFunction(lambda: datetime.now(tz=timezone.utc))
