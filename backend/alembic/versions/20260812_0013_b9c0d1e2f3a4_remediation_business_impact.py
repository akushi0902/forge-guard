"""Add business_impact to remediation_recommendations (WO-058).

Revision ID: b9c0d1e2f3a4
Revises: a8b9c0d1e2f3
Create Date: 2026-08-12

Changes:
  - ALTER TABLE remediation_recommendations ADD COLUMN business_impact TEXT
  - The column is nullable; existing rows remain valid (NULL means not yet populated).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "b9c0d1e2f3a4"
down_revision: str = "a8b9c0d1e2f3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "remediation_recommendations",
        sa.Column("business_impact", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("remediation_recommendations", "business_impact")
