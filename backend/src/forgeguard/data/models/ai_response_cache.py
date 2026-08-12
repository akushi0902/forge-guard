"""AI Response Cache SQLAlchemy ORM model (WO-060).

Stores structured AI-generated remediation responses keyed by a SHA-256 hash
of content attributes (dimension + severity + policy_rule_id + template_version).
Entries expire after a configurable TTL and can be invalidated by policy_rule_id
when a policy rule is modified.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from forgeguard.data.models import Base

_SOURCE_CHECK = "source IN ('ai_generated','template_fallback','manual')"
_CONFIDENCE_RANGE_CHECK = "confidence_score >= 0 AND confidence_score <= 1"


class AIResponseCache(Base):
    """Content-addressable DB cache for AI-generated remediation responses.

    Column notes:
        cache_key            — SHA-256 hex digest (64 chars) of
                               (dimension:severity:policy_rule_id:template_version).
                               UNIQUE — ON CONFLICT DO UPDATE for concurrent upserts.
        response_text        — Primary remediation guidance text.
        implementation_guide — Step-by-step implementation detail.
        confidence_score     — DECIMAL(3,2) AI confidence 0.00–1.00.
        source               — ai_generated or template_fallback.
        policy_rule_id       — FK used for targeted invalidation on rule change;
                               SET NULL on rule deletion so entries expire naturally.
        expires_at           — NOT NULL; must always be time-bounded per business rule.
    """

    __tablename__ = "ai_response_cache"
    __table_args__ = (
        CheckConstraint(_SOURCE_CHECK, name="valid_source"),
        CheckConstraint(_CONFIDENCE_RANGE_CHECK, name="valid_confidence_score"),
        UniqueConstraint("cache_key", name="uq_ai_response_cache_cache_key"),
        Index("ix_ai_response_cache_expires_at", "expires_at"),
        Index("ix_ai_response_cache_policy_rule_id", "policy_rule_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=func.gen_random_uuid(),
    )
    cache_key: Mapped[str] = mapped_column(String(64), nullable=False)
    response_text: Mapped[str] = mapped_column(Text, nullable=False)
    implementation_guide: Mapped[str] = mapped_column(Text, nullable=False)
    confidence_score: Mapped[Decimal] = mapped_column(Numeric(3, 2), nullable=False)
    source: Mapped[str] = mapped_column(String(20), nullable=False)
    policy_rule_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("policy_rules.id", ondelete="SET NULL"),
        nullable=True,
    )
    prompt_template_version: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
