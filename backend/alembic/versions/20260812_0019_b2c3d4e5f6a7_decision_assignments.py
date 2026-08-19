"""Create DECISION_ASSIGNMENTS table for workflow routing (WO-053).

Revision ID: b0c1d2e3f4a5
Revises: a9b0c1d2e3f4
Create Date: 2026-08-12

Tracks which reviewer role should act on each completed release assessment.
The router assigns the decision to security_reviewer (escalated) or tech_lead
(non-escalated) and monitors the assignment lifecycle: pending → completed /
pending → expired.

NOTE: This revision ID was originally "b2c3d4e5f6a7", an accidental
duplicate of the governance_schema migration's ID (20260811_0001).
Renamed to b0c1d2e3f4a5, and down_revision repointed to the renamed
20260812_0018 migration, to break the resulting cycle in the revision
graph.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "b0c1d2e3f4a5"
down_revision = "a9b0c1d2e3f4"
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
            name="status",
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
