"""Create ai_response_cache table.

Revision ID: d1e2f3a4b5c6
Revises: c0d1e2f3a4b5
Create Date: 2026-08-12 00:15:00
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "d1e2f3a4b5c6"
down_revision = "c0d1e2f3a4b5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ai_response_cache",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=False),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("cache_key", sa.VARCHAR(64), nullable=False),
        sa.Column("response_text", sa.Text, nullable=False),
        sa.Column("implementation_guide", sa.Text, nullable=False),
        sa.Column("confidence_score", sa.Numeric(3, 2), nullable=False),
        sa.Column("source", sa.VARCHAR(20), nullable=False),
        sa.Column(
            "policy_rule_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("policy_rules.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("prompt_template_version", sa.Integer, nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("expires_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.UniqueConstraint("cache_key", name="uq_ai_response_cache_cache_key"),
        sa.CheckConstraint(
            "source IN ('ai_generated','template_fallback','manual')",
            name="valid_source",
        ),
        sa.CheckConstraint(
            "confidence_score >= 0 AND confidence_score <= 1",
            name="valid_confidence_score",
        ),
    )
    op.create_index(
        "ix_ai_response_cache_expires_at",
        "ai_response_cache",
        ["expires_at"],
    )
    op.create_index(
        "ix_ai_response_cache_policy_rule_id",
        "ai_response_cache",
        ["policy_rule_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_ai_response_cache_policy_rule_id", table_name="ai_response_cache")
    op.drop_index("ix_ai_response_cache_expires_at", table_name="ai_response_cache")
    op.drop_table("ai_response_cache")
