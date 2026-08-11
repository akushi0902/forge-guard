"""Factories for Assessment / Release Assessment / ReleaseDecision domain entities.

Uses Python dataclasses as targets because the SQLAlchemy models for these
entities have not been created yet.  Upgrade to ``SQLAlchemyModelFactory`` when
models are available.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

import factory
from faker import Faker

_fake = Faker()

_DECISIONS = ("approve", "conditional_approve", "block", "pending")


# ---------------------------------------------------------------------------
# Assessment / Release Assessment
# ---------------------------------------------------------------------------

@dataclass
class AssessmentData:
    """In-memory representation of a Release Assessment domain entity."""

    id: uuid.UUID = field(default_factory=uuid.uuid4)
    service_id: uuid.UUID = field(default_factory=uuid.uuid4)
    commit_sha: str = ""
    pr_url: Optional[str] = None
    health_score: float = 0.0
    risk_score: float = 0.0
    decision: str = "pending"
    ai_explanation: Optional[str] = None
    created_at: datetime = field(
        default_factory=lambda: datetime.now(tz=timezone.utc)
    )


class AssessmentFactory(factory.Factory):
    """Factory producing AssessmentData objects.

    Usage::

        assessment = AssessmentFactory()
        approved = AssessmentFactory(decision="approve", health_score=90.0)
        blocked = AssessmentFactory(decision="block", risk_score=85.0)
    """

    class Meta:
        model = AssessmentData

    id = factory.LazyFunction(uuid.uuid4)
    service_id = factory.LazyFunction(uuid.uuid4)
    # 40-char hex commit SHA
    commit_sha = factory.LazyFunction(lambda: _fake.sha1())
    pr_url = factory.LazyAttribute(
        lambda obj: f"https://github.com/acme/repo/pull/{_fake.random_int(min=1, max=9999)}"
    )
    health_score = factory.LazyFunction(
        lambda: round(_fake.pyfloat(min_value=0, max_value=100), 1)
    )
    risk_score = factory.LazyFunction(
        lambda: round(_fake.pyfloat(min_value=0, max_value=100), 1)
    )
    decision = factory.Iterator(_DECISIONS)
    ai_explanation = factory.LazyFunction(lambda: _fake.paragraph(nb_sentences=3))
    created_at = factory.LazyFunction(lambda: datetime.now(tz=timezone.utc))


# ---------------------------------------------------------------------------
# ReleaseDecision
# ---------------------------------------------------------------------------

@dataclass
class ReleaseDecisionData:
    """In-memory representation of a ReleaseDecision domain entity."""

    id: uuid.UUID = field(default_factory=uuid.uuid4)
    assessment_id: uuid.UUID = field(default_factory=uuid.uuid4)
    outcome: str = "approve"
    rationale: str = ""
    decided_by: uuid.UUID = field(default_factory=uuid.uuid4)
    decided_at: datetime = field(
        default_factory=lambda: datetime.now(tz=timezone.utc)
    )
    conditions: list = field(default_factory=list)


class ReleaseDecisionFactory(factory.Factory):
    """Factory producing ReleaseDecisionData objects.

    Usage::

        decision = ReleaseDecisionFactory()
        conditional = ReleaseDecisionFactory(
            outcome="conditional_approve",
            conditions=["Address CVE-2024-1234 within 30 days"],
        )
    """

    class Meta:
        model = ReleaseDecisionData

    id = factory.LazyFunction(uuid.uuid4)
    assessment_id = factory.LazyFunction(uuid.uuid4)
    outcome = factory.Iterator(_DECISIONS)
    rationale = factory.LazyFunction(lambda: _fake.paragraph(nb_sentences=2))
    decided_by = factory.LazyFunction(uuid.uuid4)
    decided_at = factory.LazyFunction(lambda: datetime.now(tz=timezone.utc))
    conditions = factory.LazyFunction(list)
