"""Create agent_feedback table for AI Agent conversation ratings.

Revision ID: f3a4b5c6d7e8
Revises: e2f3a4b5c6d7
Create Date: 2026-08-12

ai_conversations was created in migration c3d4e5f6a7b8 (audit schema).
This migration adds the AGENT_FEEDBACK table only.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "f3a4b5c6d7e8"
down_revision = "e2f3a4b5c6d7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "agent_feedback",
        sa.Column(
            "id",
            sa.UUID(),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column(
            "conversation_id",
            sa.UUID(),
            sa.ForeignKey("ai_conversations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("message_index", sa.Integer(), nullable=False),
        sa.Column(
            "user_id",
            sa.UUID(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "rating",
            sa.String(10),
            sa.CheckConstraint("rating IN ('thumbs_up', 'thumbs_down')", name="ck_agent_feedback_rating"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index(
        "idx_agent_feedback_unique",
        "agent_feedback",
        ["conversation_id", "message_index", "user_id"],
        unique=True,
    )
    op.create_index(
        "ix_agent_feedback_user_id",
        "agent_feedback",
        ["user_id"],
    )
    op.create_index(
        "ix_ai_conversations_created_at",
        "ai_conversations",
        ["created_at"],
        postgresql_ops={"created_at": "DESC"},
    )

    op.execute("GRANT INSERT, SELECT ON agent_feedback TO forgeguard_app")
    op.execute("GRANT ALL ON agent_feedback TO forgeguard_admin")


def downgrade() -> None:
    op.execute("REVOKE ALL ON agent_feedback FROM forgeguard_app, forgeguard_admin")
    op.drop_index("ix_agent_feedback_user_id", table_name="agent_feedback")
    op.drop_index("idx_agent_feedback_unique", table_name="agent_feedback")
    op.drop_index("ix_ai_conversations_created_at", table_name="ai_conversations")
    op.drop_table("agent_feedback")
