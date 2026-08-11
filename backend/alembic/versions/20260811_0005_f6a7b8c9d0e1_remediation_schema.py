"""Remediation domain schema: recommendations and exceptions.

Creates 2 tables for the Remediation domain:
    remediation_recommendations — AI-generated or template fix guidance per finding
    exceptions                  — time-bounded finding suppression with approval workflow

Key design decisions:
    - remediation_recommendations.finding_id: ON DELETE CASCADE (cleanup with finding)
    - exceptions.finding_id: ON DELETE RESTRICT (preserve audit trail)
    - exceptions.expires_at: NOT NULL (all exceptions must be time-bounded)
    - exceptions.justification: NOT NULL (every exception must carry a stated reason)
    - Indexes on exceptions(status) and exceptions(expires_at) support background
      expiry detection and approval workflow queries

Revision ID: f6a7b8c9d0e1
Revises:     e5f6a7b8c9d0 (assessments_schema)
Create Date: 2026-08-11 00:05:00 UTC
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# ---------------------------------------------------------------------------
# Revision identifiers
# ---------------------------------------------------------------------------
revision: str = "f6a7b8c9d0e1"
down_revision: str | None = "e5f6a7b8c9d0"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    # ------------------------------------------------------------------ #
    # remediation_recommendations
    # ------------------------------------------------------------------ #
    op.create_table(
        "remediation_recommendations",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("finding_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("recommendation_text", sa.Text(), nullable=False),
        sa.Column("implementation_guide", sa.Text(), nullable=True),
        sa.Column("confidence_score", sa.Numeric(3, 2), nullable=True),
        sa.Column("source", sa.String(50), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "source IN ('ai_generated','template_fallback','manual')",
            name="ck_remediation_recommendations_valid_source",
        ),
        sa.CheckConstraint(
            "confidence_score IS NULL OR (confidence_score >= 0 AND confidence_score <= 1)",
            name="ck_remediation_recommendations_valid_confidence_score",
        ),
        sa.ForeignKeyConstraint(
            ["finding_id"],
            ["findings.id"],
            name="fk_remediation_recommendations_finding_id_findings",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_remediation_recommendations"),
    )
    op.create_index(
        "ix_remediation_recommendations_finding_id",
        "remediation_recommendations",
        ["finding_id"],
    )

    # ------------------------------------------------------------------ #
    # exceptions
    # ------------------------------------------------------------------ #
    op.create_table(
        "exceptions",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("finding_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("requested_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("justification", sa.Text(), nullable=False),
        sa.Column(
            "status",
            sa.String(50),
            nullable=False,
            server_default=sa.text("'requested'"),
        ),
        sa.Column("decided_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("decision_comment", sa.Text(), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('requested','approved','denied','expired')",
            name="ck_exceptions_valid_exception_status",
        ),
        sa.ForeignKeyConstraint(
            ["finding_id"],
            ["findings.id"],
            name="fk_exceptions_finding_id_findings",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["requested_by"],
            ["users.id"],
            name="fk_exceptions_requested_by_users",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["decided_by"],
            ["users.id"],
            name="fk_exceptions_decided_by_users",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_exceptions"),
    )
    op.create_index("ix_exceptions_finding_id", "exceptions", ["finding_id"])
    op.create_index("ix_exceptions_status", "exceptions", ["status"])
    op.create_index("ix_exceptions_expires_at", "exceptions", ["expires_at"])


def downgrade() -> None:
    op.drop_table("exceptions")
    op.drop_table("remediation_recommendations")
