"""Remediation domain SQLAlchemy ORM models.

Tables defined here support the RECOMMEND → REMEDIATE → VALIDATE lifecycle:

    RemediationRecommendation — AI-generated or template-based fix guidance for a finding
    FindingException          — Time-bounded suppression request with approval workflow

Design constraints:
    - VARCHAR + CHECK constraints for source and status (no PG ENUM types).
    - DECIMAL(3,2) with CHECK(0 ≤ confidence_score ≤ 1) for AI confidence.
    - RemediationRecommendation uses ON DELETE CASCADE from findings (cleanup with finding).
    - FindingException uses ON DELETE RESTRICT from findings (audit trail preserved).
    - expires_at is NOT NULL — all exceptions must be time-bounded per business rules.
    - Python class named FindingException to avoid shadowing the built-in Exception.
    - Table name is 'exceptions' to match the domain schema.
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
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from forgeguard.data.models import Base

# ---------------------------------------------------------------------------
# Valid values — kept in sync with CHECK constraints below.
# ---------------------------------------------------------------------------

VALID_RECOMMENDATION_SOURCES: tuple[str, ...] = (
    "ai_generated",
    "template_fallback",
    "manual",
)
VALID_EXCEPTION_STATUSES: tuple[str, ...] = (
    "requested",
    "approved",
    "denied",
    "expired",
)

_SOURCE_CHECK = "source IN ('ai_generated','template_fallback','manual')"
_EXCEPTION_STATUS_CHECK = "status IN ('requested','approved','denied','expired')"
_CONFIDENCE_RANGE_CHECK = (
    "confidence_score IS NULL OR (confidence_score >= 0 AND confidence_score <= 1)"
)


class RemediationRecommendation(Base):
    """AI-generated or template-based fix guidance linked to a specific finding.

    Column notes:
        recommendation_text  — primary human-readable remediation guidance.
        implementation_guide — optional step-by-step implementation detail; NULL
                               when the source is template_fallback and no guide
                               was available.
        confidence_score     — DECIMAL(3,2) AI confidence 0.00–1.00; NULL when
                               source is manual or AI engine unavailable.
        source               — ai_generated: LLM output; template_fallback: static
                               template used when AI unavailable; manual: authored
                               by a human reviewer.
    """

    __tablename__ = "remediation_recommendations"
    __table_args__ = (
        CheckConstraint(_SOURCE_CHECK, name="valid_source"),
        CheckConstraint(_CONFIDENCE_RANGE_CHECK, name="valid_confidence_score"),
        Index("ix_remediation_recommendations_finding_id", "finding_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=func.gen_random_uuid(),
    )
    finding_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("findings.id", ondelete="CASCADE"),
        nullable=False,
    )
    recommendation_text: Mapped[str] = mapped_column(Text, nullable=False)
    implementation_guide: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    business_impact: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    confidence_score: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(3, 2), nullable=True
    )
    source: Mapped[str] = mapped_column(String(50), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class FindingException(Base):
    """Time-bounded exception request for suppressing a finding.

    Named FindingException in Python to avoid shadowing the built-in Exception.
    The database table name is 'exceptions'.

    Column notes:
        finding_id       — FK with ON DELETE RESTRICT; exceptions are preserved
                           for audit trail even if the finding is eventually deleted.
        justification    — NOT NULL; every exception must carry a stated reason.
        expires_at       — NOT NULL; all exceptions must be time-bounded.
        decided_by       — NULL until the exception is reviewed; populated by the
                           Security Reviewer (security findings) or Platform Admin.
        decided_at       — NULL until a decision is made.
        decision_comment — optional additional context from the reviewer.
        status           — lifecycle state managed by the application layer:
                           requested → approved/denied; approved → expired (background
                           job triggers re-evaluation when expires_at passes).
    """

    __tablename__ = "exceptions"
    __table_args__ = (
        CheckConstraint(_EXCEPTION_STATUS_CHECK, name="valid_exception_status"),
        Index("ix_exceptions_finding_id", "finding_id"),
        Index("ix_exceptions_status", "status"),
        Index("ix_exceptions_expires_at", "expires_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=func.gen_random_uuid(),
    )
    finding_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("findings.id", ondelete="RESTRICT"),
        nullable=False,
    )
    requested_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    justification: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(
        String(50), nullable=False, default="requested", server_default="'requested'"
    )
    decided_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    decision_comment: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    decided_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
