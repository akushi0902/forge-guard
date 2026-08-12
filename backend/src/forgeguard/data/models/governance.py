"""Governance domain SQLAlchemy ORM models.

Tables defined here power the Policy Guardian evaluation engine:

    Service     — registered applications under governance evaluation
    Policy      — a named set of rules grouped by engineering dimension
    PolicyRule  — an individual evaluation criterion with JSONB threshold config

Design constraints:
    - JSONB for threshold_config enables diverse rule types without schema changes.
    - VARCHAR + CHECK constraint for dimension / severity (no PostgreSQL ENUM types).
    - Policy versioning uses an integer version column — no separate versions table.
    - Soft-delete via deleted_at IS NULL; callers must apply this filter.
    - All timestamps are timezone-aware (TIMESTAMPTZ).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any, Optional

from forgeguard.services.domain.severity import SeverityLevel

from sqlalchemy import (
    Boolean,
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
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from forgeguard.data.models import Base

# ---------------------------------------------------------------------------
# Valid values — kept in sync with CHECK constraints below.
# ---------------------------------------------------------------------------

VALID_DIMENSIONS: tuple[str, ...] = (
    "code_quality",
    "test_coverage",
    "security",
    "documentation",
    "operations_readiness",
)

VALID_SEVERITIES: tuple[str, ...] = (
    "critical",
    "high",
    "medium",
    "low",
)

VALID_RULE_TYPES: tuple[str, ...] = (
    "threshold_gte",
    "threshold_lte",
    "threshold_eq",
    "regex_match",
    "regex_no_match",
)

_DIMENSION_CHECK_EXPR = (
    "dimension IN ("
    "'code_quality','test_coverage','security',"
    "'documentation','operations_readiness'"
    ")"
)

_SEVERITY_CHECK_EXPR = (
    "severity IN ('critical','high','medium','low')"
)


class Service(Base):
    """A registered application under ForgeGuard governance.

    Column notes:
        service_metadata — JSONB store for extensible attributes (language,
                           framework, team size, etc.).  Maps to the 'metadata'
                           database column; named service_metadata in Python to
                           avoid shadowing Base.metadata on the class.
        forge_catalog_id — Reference pointer to the Forge Catalog entry; NULL
                           means the service has not been synced yet.
        is_demo          — True for demo services (e.g. Payment Service fixture).
        deleted_at       — NULL means active; non-NULL means soft-deleted.
    """

    __tablename__ = "services"
    __table_args__ = (
        UniqueConstraint("name", name="uq_services_name"),
        Index("ix_services_deleted_at", "deleted_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=func.gen_random_uuid(),
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    repository_url: Mapped[Optional[str]] = mapped_column(String(2048), nullable=True)
    owner_team: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    # Mapped to the 'metadata' column in PostgreSQL.
    service_metadata: Mapped[dict[str, Any]] = mapped_column(
        "metadata",
        JSONB,
        nullable=False,
        default=dict,
        server_default="{}",
    )
    forge_catalog_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    is_demo: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    deleted_at: Mapped[Optional[datetime]] = mapped_column(
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

    policies: Mapped[list[Policy]] = relationship(
        "Policy",
        back_populates="service",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class Policy(Base):
    """A named collection of rules for one engineering dimension.

    Column notes:
        dimension   — one of VALID_DIMENSIONS; enforced by CHECK constraint.
        version     — integer incremented at the application layer on update.
        created_by  — FK to users.id; nullable if created by system/migration.
        deleted_at  — NULL means active.
    """

    __tablename__ = "policies"
    __table_args__ = (
        CheckConstraint(_DIMENSION_CHECK_EXPR, name="valid_dimension"),
        Index("ix_policies_dimension", "dimension"),
        Index("ix_policies_deleted_at", "deleted_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=func.gen_random_uuid(),
    )
    service_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("services.id", ondelete="CASCADE"),
        nullable=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    dimension: Mapped[str] = mapped_column(String(50), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default="1"
    )
    created_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    deleted_at: Mapped[Optional[datetime]] = mapped_column(
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

    service: Mapped[Optional[Service]] = relationship(
        "Service", back_populates="policies"
    )
    rules: Mapped[list[PolicyRule]] = relationship(
        "PolicyRule",
        back_populates="policy",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class PolicyRule(Base):
    """An individual evaluation criterion within a Policy.

    Column notes:
        threshold_config — JSONB rule-specific configuration, e.g.:
                           {"operator": "gte", "value": 80, "unit": "percent"}
                           A GIN index enables efficient containment queries.
        severity         — one of VALID_SEVERITIES; enforced by CHECK constraint.
        weight           — DECIMAL(5,2) contribution to Health Score calculation.
        deleted_at       — NULL means active.
    """

    __tablename__ = "policy_rules"
    __table_args__ = (
        CheckConstraint(_SEVERITY_CHECK_EXPR, name="valid_severity"),
        # GIN index: efficient JSONB containment queries (threshold_config @> '{}')
        Index(
            "ix_policy_rules_threshold_config_gin",
            "threshold_config",
            postgresql_using="gin",
        ),
        # Composite index: most common query pattern — active rules for a policy
        Index("ix_policy_rules_policy_id_is_active", "policy_id", "is_active"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=func.gen_random_uuid(),
    )
    policy_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("policies.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    rule_type: Mapped[str] = mapped_column(String(100), nullable=False)
    threshold_config: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    severity: Mapped[SeverityLevel] = mapped_column(String(20), nullable=False)
    weight: Mapped[Decimal] = mapped_column(
        Numeric(5, 2),
        nullable=False,
        default=Decimal("1.0"),
        server_default="1.0",
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    deleted_at: Mapped[Optional[datetime]] = mapped_column(
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

    policy: Mapped[Policy] = relationship("Policy", back_populates="rules")
