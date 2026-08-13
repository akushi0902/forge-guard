"""add workflow fields to release_decisions (WO-092)

Revision ID: d2e3f4a5b6c7
Revises: c1d2e3f4a5b6
Create Date: 2026-08-13 00:01:00.000000

Adds workflow_id, routing_method, workflow_status, and workflow_timeout_at
to the release_decisions table to support the Forge Workflow Engine integration.

A partial index on workflow_status improves polling query performance by only
indexing rows that still require polling (pending, in_review).
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "d2e3f4a5b6c7"
down_revision = "c1d2e3f4a5b6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "release_decisions",
        sa.Column("workflow_id", sa.UUID(), nullable=True),
    )
    op.add_column(
        "release_decisions",
        sa.Column(
            "routing_method",
            sa.String(30),
            nullable=True,
        ),
    )
    op.add_column(
        "release_decisions",
        sa.Column(
            "workflow_status",
            sa.String(30),
            nullable=True,
        ),
    )
    op.add_column(
        "release_decisions",
        sa.Column(
            "workflow_timeout_at",
            sa.TIMESTAMP(timezone=True),
            nullable=True,
        ),
    )

    # Partial index: only rows actively being polled (pending or in_review).
    op.create_index(
        "idx_release_decisions_workflow_status_active",
        "release_decisions",
        ["workflow_status"],
        postgresql_where=sa.text("workflow_status IN ('pending', 'in_review')"),
    )


def downgrade() -> None:
    op.drop_index(
        "idx_release_decisions_workflow_status_active",
        table_name="release_decisions",
    )
    op.drop_column("release_decisions", "workflow_timeout_at")
    op.drop_column("release_decisions", "workflow_status")
    op.drop_column("release_decisions", "routing_method")
    op.drop_column("release_decisions", "workflow_id")
