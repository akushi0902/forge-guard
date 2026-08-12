"""Add version column to findings table for optimistic locking (WO-061).

Revision ID: e2f3a4b5c6d7
Revises: d1e2f3a4b5c6
Create Date: 2026-08-12 00:16:00

Changes:
  - ADD version INTEGER NOT NULL DEFAULT 1 to findings table
    Used for optimistic locking in concurrent re-evaluation scenarios.
    The application increments this column on each status update;
    a WHERE version = $expected clause detects mid-air collisions.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "e2f3a4b5c6d7"
down_revision: str = "d1e2f3a4b5c6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "findings",
        sa.Column(
            "version",
            sa.Integer(),
            nullable=False,
            server_default="1",
        ),
    )


def downgrade() -> None:
    op.drop_column("findings", "version")
