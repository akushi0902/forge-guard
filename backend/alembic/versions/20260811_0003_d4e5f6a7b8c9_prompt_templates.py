"""Prompt templates table for versioned AI prompt management.

Creates:
    prompt_templates — versioned LLM prompt templates with JSONB variable schema,
                       dimension/severity classification, and active-flag versioning.

Revision ID: d4e5f6a7b8c9
Revises:     c3d4e5f6a7b8 (audit_schema)
Create Date: 2026-08-11 00:03:00 UTC
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# ---------------------------------------------------------------------------
# Revision identifiers
# ---------------------------------------------------------------------------
revision: str = "d4e5f6a7b8c9"
down_revision: str | None = "c3d4e5f6a7b8"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "prompt_templates",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column(
            "version",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("1"),
        ),
        sa.Column("template_text", sa.Text(), nullable=False),
        sa.Column(
            "variables",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("dimension", sa.String(50), nullable=False),
        sa.Column("severity_level", sa.String(20), nullable=False),
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
        sa.Column(
            "created_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        # Constraints
        sa.CheckConstraint(
            "dimension IN ('code_quality','test_coverage','security',"
            "'documentation','operations_readiness')",
            name="valid_dimension",
        ),
        sa.CheckConstraint(
            "severity_level IN ('critical','high','medium','low')",
            name="valid_severity_level",
        ),
        sa.UniqueConstraint("name", "version", name="uq_prompt_templates_name_version"),
    )

    # Composite index: fast active-template lookup by dimension + severity.
    op.create_index(
        "ix_prompt_templates_dimension_severity_is_active",
        "prompt_templates",
        ["dimension", "severity_level", "is_active"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_prompt_templates_dimension_severity_is_active",
        table_name="prompt_templates",
    )
    op.drop_table("prompt_templates")
