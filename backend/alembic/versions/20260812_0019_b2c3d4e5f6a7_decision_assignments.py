"""Create DECISION_ASSIGNMENTS table for workflow routing (WO-053).

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-08-12

Tracks which reviewer role should act on each completed release assessment.
The router assigns the decision to security_reviewer (escalated) or tech_lead
(non-escalated) and monitors the assignment lifecycle: pending → completed /
pending → expired.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "b2c3d4e5f6a7"
down_revision = "a1b2c3d4e5f6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "decision_assignments",
        sa.Column(
            "id",
            sa.UUID(),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("release_assessment_id", sa.UUID(), nullable=False),
        sa.Column("assigned_role", sa.String(50), nullable=False),
        sa.Column(
            "assigned_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.String(20),
            server_default=sa.text("'pending'"),
            nullable=False,
        ),
        sa.Column("completed_by", sa.UUID(), nullable=True),
        sa.Column("completed_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="pk_decision_assignments"),
        sa.ForeignKeyConstraint(
            ["release_assessment_id"],
            ["release_assessments.id"],
            name="fk_decision_assignments_release_assessment_id_release_assessments",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["completed_by"],
            ["users.id"],
            name="fk_decision_assignments_completed_by_users",
            ondelete="SET NULL",
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'completed', 'expired')",
            name="ck_decision_assignments_status",
        ),
    )

    # Index for pending queue queries (primary access pattern).
    op.create_index(
        "ix_decision_assignments_role_status",
        "decision_assignments",
        ["assigned_role", "status"],
    )

    # Index for lookup by assessment.
    op.create_index(
        "ix_decision_assignments_release_assessment_id",
        "decision_assignments",
        ["release_assessment_id"],
    )

    # Partial unique constraint: at most one pending assignment per assessment.
    op.execute(
        """
        CREATE UNIQUE INDEX uq_decision_assignments_assessment_pending
        ON decision_assignments (release_assessment_id)
        WHERE status = 'pending'
        """
    )


def downgrade() -> None:
    op.execute(
        "DROP INDEX IF EXISTS uq_decision_assignments_assessment_pending"
    )
    op.drop_index("ix_decision_assignments_release_assessment_id", "decision_assignments")
    op.drop_index("ix_decision_assignments_role_status", "decision_assignments")
    op.drop_table("decision_assignments")
