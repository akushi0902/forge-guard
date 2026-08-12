"""Add webhook_events table and trigger_type on release_assessments (WO-091).

Revision ID: c4d5e6f7a8b9
Revises: b3c4d5e6f7a8
Create Date: 2026-08-12

Changes:
  - CREATE TABLE webhook_events: idempotency store for GitHub webhook deliveries
      id UUID PK, delivery_id UNIQUE VARCHAR(100), event_type VARCHAR(50),
      repository VARCHAR(255), payload_summary JSONB, processing_status VARCHAR(20),
      assessment_id FK → release_assessments(id), received_at TIMESTAMPTZ,
      processed_at TIMESTAMPTZ
  - CREATE INDEX idx_webhook_events_delivery_id ON webhook_events(delivery_id)
  - ALTER TABLE release_assessments ADD COLUMN trigger_type VARCHAR(30) DEFAULT 'manual'
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# ---------------------------------------------------------------------------
# Revision identifiers
# ---------------------------------------------------------------------------

revision: str = "c4d5e6f7a8b9"
down_revision: str = "b3c4d5e6f7a8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # Add trigger_type to release_assessments
    # ------------------------------------------------------------------
    op.add_column(
        "release_assessments",
        sa.Column(
            "trigger_type",
            sa.String(30),
            nullable=False,
            server_default="manual",
        ),
    )
    op.create_check_constraint(
        "valid_release_assessment_trigger_type",
        "release_assessments",
        "trigger_type IN ('manual','scheduled','webhook','github_webhook')",
    )

    # ------------------------------------------------------------------
    # Create webhook_events table
    # ------------------------------------------------------------------
    op.create_table(
        "webhook_events",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("delivery_id", sa.String(100), nullable=False, unique=True),
        sa.Column("event_type", sa.String(50), nullable=False),
        sa.Column("repository", sa.String(255), nullable=False),
        sa.Column("payload_summary", postgresql.JSONB(), nullable=True),
        sa.Column(
            "processing_status",
            sa.String(20),
            nullable=False,
            server_default="received",
        ),
        sa.Column(
            "assessment_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("release_assessments.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "received_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_index(
        "idx_webhook_events_delivery_id",
        "webhook_events",
        ["delivery_id"],
        unique=True,
    )
    op.create_index(
        "idx_webhook_events_repository_received_at",
        "webhook_events",
        ["repository", "received_at"],
    )


def downgrade() -> None:
    op.drop_index("idx_webhook_events_repository_received_at", table_name="webhook_events")
    op.drop_index("idx_webhook_events_delivery_id", table_name="webhook_events")
    op.drop_table("webhook_events")

    op.drop_constraint(
        "valid_release_assessment_trigger_type",
        "release_assessments",
        type_="check",
    )
    op.drop_column("release_assessments", "trigger_type")
