"""SQLAlchemy ORM model for DECISION_ASSIGNMENTS (WO-053)."""

from __future__ import annotations

import uuid

from sqlalchemy import CheckConstraint, ForeignKey, String, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import TIMESTAMP

from forgeguard.data.models import Base


class DecisionAssignment(Base):
    """Tracks reviewer role assignment for each completed release assessment.

    Lifecycle: pending → completed (human decision submitted)
               pending → expired (24h timeout, soft — assignment still actionable)
    """

    __tablename__ = "decision_assignments"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    release_assessment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("release_assessments.id", ondelete="CASCADE"),
        nullable=False,
    )
    assigned_role: Mapped[str] = mapped_column(String(50), nullable=False)
    assigned_at: Mapped[object] = mapped_column(
        TIMESTAMP(timezone=True),
        server_default=text("now()"),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(
        String(20),
        server_default=text("'pending'"),
        nullable=False,
    )
    completed_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    completed_at: Mapped[object | None] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )
    created_at: Mapped[object] = mapped_column(
        TIMESTAMP(timezone=True),
        server_default=text("now()"),
        nullable=False,
    )
    updated_at: Mapped[object] = mapped_column(
        TIMESTAMP(timezone=True),
        server_default=text("now()"),
        nullable=False,
    )

    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'completed', 'expired')",
            name="ck_decision_assignments_status",
        ),
    )
