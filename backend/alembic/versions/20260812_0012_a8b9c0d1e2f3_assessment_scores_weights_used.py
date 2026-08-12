"""Add weights_used to assessment_scores; make overall_score nullable (WO-040).

Revision ID: a8b9c0d1e2f3
Revises: f7a8b9c0d1e2
Create Date: 2026-08-12

Changes:
  - ALTER TABLE assessment_scores ADD COLUMN weights_used JSONB NOT NULL DEFAULT '{}'
  - ALTER TABLE assessment_scores ALTER COLUMN overall_score DROP NOT NULL
    [overall_score is null when all dimensions have no evaluation data]
  - CREATE INDEX idx_scores_assessment ON assessment_scores(assessment_id)
    [referenced in WO-040 DB Changes for assessment-level score lookup]
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "a8b9c0d1e2f3"
down_revision: str = "f7a8b9c0d1e2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "assessment_scores",
        sa.Column(
            "weights_used",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
    )
    op.alter_column("assessment_scores", "overall_score", nullable=True)
    op.create_index(
        "idx_scores_assessment",
        "assessment_scores",
        ["assessment_id"],
    )


def downgrade() -> None:
    op.drop_index("idx_scores_assessment", table_name="assessment_scores")
    op.alter_column("assessment_scores", "overall_score", nullable=False)
    op.drop_column("assessment_scores", "weights_used")
