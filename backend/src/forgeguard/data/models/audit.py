"""Audit domain SQLAlchemy ORM models.

Tables:
    AuditLog       — immutable audit trail for all governance decisions and
                     data mutations.  The underlying database table is a
                     range-partitioned table (PARTITION BY RANGE on created_at).
                     The ORM model is used for SELECT/INSERT queries only.
    AIConversation — AI Agent interaction history linked to a user session.

Design constraints:
    - audit_logs has NO updated_at column — records are write-once.
    - ip_address_masked stores only pre-masked IPs (e.g., 192.168.xxx.xxx);
      masking must happen at the application layer before INSERT.
    - actor_id is nullable — system-generated events have no human actor.
    - The database-level immutability guarantee (revoking UPDATE/DELETE from
      the application role) is enforced in the migration, not by the ORM.
    - All timestamps are timezone-aware (TIMESTAMPTZ).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from forgeguard.data.models import Base


class AuditLog(Base):
    """Immutable audit record for a governance action or data mutation.

    The underlying PostgreSQL table is partitioned by RANGE on created_at
    (monthly partitions).  SQLAlchemy queries against this model transparently
    span all partitions.

    Column notes:
        actor_id        — NULL for system-generated events (purge jobs, etc.).
        actor_role      — Snapshot of the actor's role at event time.
        action          — Past-tense verb, e.g. 'policy_rule.created'.
        resource_type   — Domain entity type, e.g. 'policy_rule', 'service'.
        resource_id     — UUID of the affected entity; nullable for bulk ops.
        before_state    — JSONB snapshot before the mutation (NULL for creates).
        after_state     — JSONB snapshot after the mutation (NULL for deletes).
        ip_address_masked — Pre-masked at application layer; never raw IP.
        correlation_id  — Links to the X-Request-ID from RequestIDMiddleware.
    """

    __tablename__ = "audit_logs"
    # Composite indexes defined here are used for ORM query planning.
    # The actual GIN/btree indexes on the partitioned table are created by
    # the Alembic migration using op.execute().
    __table_args__ = (
        Index("ix_audit_logs_actor_id_created_at", "actor_id", "created_at"),
        Index(
            "ix_audit_logs_resource_type_resource_id_created_at",
            "resource_type",
            "resource_id",
            "created_at",
        ),
        Index("ix_audit_logs_correlation_id", "correlation_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=func.gen_random_uuid(),
    )
    actor_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    actor_role: Mapped[str] = mapped_column(String(50), nullable=False)
    action: Mapped[str] = mapped_column(String(255), nullable=False)
    resource_type: Mapped[str] = mapped_column(String(100), nullable=False)
    resource_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    before_state: Mapped[Optional[dict[str, Any]]] = mapped_column(
        JSONB, nullable=True
    )
    after_state: Mapped[Optional[dict[str, Any]]] = mapped_column(
        JSONB, nullable=True
    )
    ip_address_masked: Mapped[Optional[str]] = mapped_column(
        String(45), nullable=True
    )
    correlation_id: Mapped[Optional[str]] = mapped_column(
        String(36), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    # No updated_at — audit records are write-once.


class AIConversation(Base):
    """AI Agent interaction history for a user session.

    Column notes:
        messages     — JSONB array of message objects, default empty array.
        context_refs — JSONB references to domain entities mentioned in the
                       conversation (service IDs, policy IDs, etc.).
    """

    __tablename__ = "ai_conversations"
    __table_args__ = (
        Index("ix_ai_conversations_user_id", "user_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=func.gen_random_uuid(),
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    messages: Mapped[list[Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        server_default="[]",
    )
    context_refs: Mapped[Optional[dict[str, Any]]] = mapped_column(
        JSONB, nullable=True
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
