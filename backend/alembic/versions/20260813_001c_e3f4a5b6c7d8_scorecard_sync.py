"""Add forge scorecard sync: pending_sync_jobs table and assessment_scores.forge_sync_status (WO-090).

Revision ID: e3f4a5b6c7d8
Revises: d2e3f4a5b6c7
Create Date: 2026-08-13 00:02:00.000000

Changes:
  1. ALTER TABLE assessment_scores ADD COLUMN forge_sync_status VARCHAR(30) DEFAULT 'pending'
  2. ALTER TABLE assessment_scores ADD COLUMN last_scorecard_sync_at TIMESTAMPTZ nullable
  3. CREATE TABLE pending_sync_jobs (...)
  4. INDEX idx_pending_sync_jobs_status_next_retry ON pending_sync_jobs(status, next_retry_at)
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "e3f4a5b6c7d8"
down_revision = "d2e3f4a5b6c7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── assessment_scores additions ─────────────────────────────────────────
    op.add_column(
        "assessment_scores",
        sa.Column(
            "forge_sync_status",
            sa.String(30),
            nullable=False,
            server_default="pending",
        ),
    )
    op.add_column(
        "assessment_scores",
        sa.Column(
            "last_scorecard_sync_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )

    # ── pending_sync_jobs table ─────────────────────────────────────────────
    op.create_table(
        "pending_sync_jobs",
        sa.Column(
            "id",
            sa.UUID(),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("job_type", sa.String(50), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column(
            "status",
            sa.String(20),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_retries", sa.Integer(), nullable=False, server_default="5"),
        sa.Column("next_retry_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index(
        "idx_pending_sync_jobs_status_next_retry",
        "pending_sync_jobs",
        ["status", "next_retry_at"],
    )


def downgrade() -> None:
    op.drop_index("idx_pending_sync_jobs_status_next_retry", table_name="pending_sync_jobs")
    op.drop_table("pending_sync_jobs")
    op.drop_column("assessment_scores", "last_scorecard_sync_at")
    op.drop_column("assessment_scores", "forge_sync_status")
