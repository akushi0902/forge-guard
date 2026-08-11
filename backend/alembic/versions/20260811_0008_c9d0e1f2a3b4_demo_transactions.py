"""Create demo_transactions table.

Revision ID: c9d0e1f2a3b4
Revises:     b8c9d0e1f2a3 (audit_immutability_trigger)
Create Date: 2026-08-11 00:08:00 UTC

The Payment Service seed record is already present from migration 0006
(seed_demo_data).  This migration only creates the demo_transactions table
for synthetic transaction storage.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "c9d0e1f2a3b4"
down_revision = "b8c9d0e1f2a3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "demo_transactions",
        sa.Column(
            "id",
            sa.UUID(),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
            primary_key=True,
        ),
        sa.Column("amount", sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("merchant", sa.String(255), nullable=False),
        sa.Column("card_last_four", sa.String(4), nullable=False),
        sa.Column(
            "status",
            sa.String(20),
            server_default=sa.text("'pending'"),
            nullable=False,
        ),
        sa.Column("authorization_code", sa.String(20), nullable=True),
        sa.Column(
            "metadata",
            JSONB,
            server_default=sa.text("'{}'::jsonb"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'approved', 'declined')",
            name="demo_transactions_status",
        ),
        sa.CheckConstraint(
            "char_length(currency) = 3",
            name="demo_transactions_currency_len",
        ),
        sa.CheckConstraint(
            "char_length(card_last_four) = 4",
            name="demo_transactions_card_four_len",
        ),
        sa.CheckConstraint(
            "amount >= 0.01 AND amount <= 9999.99",
            name="demo_transactions_amount_range",
        ),
    )
    op.create_index(
        "ix_demo_transactions_created_at",
        "demo_transactions",
        ["created_at"],
    )
    op.create_index(
        "ix_demo_transactions_status",
        "demo_transactions",
        ["status"],
    )


def downgrade() -> None:
    op.drop_index("ix_demo_transactions_status", table_name="demo_transactions")
    op.drop_index("ix_demo_transactions_created_at", table_name="demo_transactions")
    op.drop_table("demo_transactions")
