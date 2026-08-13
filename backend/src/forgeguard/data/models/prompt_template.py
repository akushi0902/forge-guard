"""PromptTemplate SQLAlchemy ORM model.

Stores versioned prompt templates for the AI recommendation generator.
Each row is a specific version of a named template; updates create new
version rows (previous versions are never overwritten — immutable audit trail).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from forgeguard.data.models import Base

# Kept in sync with governance.py VALID_DIMENSIONS.
_DIMENSION_CHECK_EXPR = (
    "dimension IN ("
    "'code_quality','test_coverage','security',"
    "'documentation','operations_readiness'"
    ")"
)

_SEVERITY_CHECK_EXPR = (
    "severity_level IN ('critical','high','medium','low')"
)


class PromptTemplate(Base):
    """A versioned LLM prompt template for a specific dimension and severity.

    Column notes:
        name           — Human-readable identifier; unique per version.
        version        — Auto-incremented on update; 1 for new templates.
        template_text  — Prompt text with ``$variable`` substitution placeholders.
        variables      — JSONB schema describing expected substitution variables
                         (e.g. ``{"finding_title": "str", "evidence": "str"}``).
        dimension      — One of VALID_DIMENSIONS; enforced by CHECK constraint.
        severity_level — One of ``critical|high|medium|low``.
        is_active      — Only one active version per (name, dimension, severity_level)
                         is used at runtime; previous versions are retained.
        created_by     — FK to users.id; NULL if created by seed/migration.
    """

    __tablename__ = "prompt_templates"
    __table_args__ = (
        CheckConstraint(_DIMENSION_CHECK_EXPR, name="valid_dimension"),
        CheckConstraint(_SEVERITY_CHECK_EXPR, name="valid_severity_level"),
        UniqueConstraint("name", "version", name="uq_prompt_templates_name_version"),
        # Fast lookup: get active template for a given dimension + severity.
        Index(
            "ix_prompt_templates_dimension_severity_is_active",
            "dimension",
            "severity_level",
            "is_active",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=func.gen_random_uuid(),
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default="1"
    )
    template_text: Mapped[str] = mapped_column(Text, nullable=False)
    variables: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default="{}"
    )
    dimension: Mapped[str] = mapped_column(String(50), nullable=False)
    severity_level: Mapped[str] = mapped_column(String(20), nullable=False)
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    created_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
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
