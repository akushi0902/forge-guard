"""Add escalation_required to findings (WO-036).

Revision ID: d5e6f7a8b9c0
Revises: c4d5e6f7a8b9
Create Date: 2026-08-12

Changes:
  - ALTER TABLE findings ADD COLUMN escalation_required BOOLEAN NOT NULL DEFAULT false
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "d5e6f7a8b9c0"
down_revision: str = "c4d5e6f7a8b9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "findings",
        sa.Column(
            "escalation_required",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )


def downgrade() -> None:
    op.drop_column("findings", "escalation_required")
