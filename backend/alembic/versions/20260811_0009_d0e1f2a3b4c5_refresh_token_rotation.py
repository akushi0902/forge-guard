"""Add replaced_by_id and token_hash index to refresh_tokens.

Revision ID: d0e1f2a3b4c5
Revises:     c9d0e1f2a3b4 (demo_transactions)
Create Date: 2026-08-11 00:09:00 UTC

The refresh_tokens table was created in migration 0000 (identity_access_schema)
without the replaced_by_id self-referential FK needed for token rotation chains,
and without an index on token_hash needed for efficient hash lookups.

This migration adds:
  1. replaced_by_id UUID FK(self) nullable — links old token to its replacement
     for family-wide revocation (reuse detection).
  2. ix_refresh_tokens_token_hash — covering index on token_hash for O(log n)
     lookup by SHA-256 hash.
  3. ix_refresh_tokens_expires_at — index for expiry-based cleanup queries.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "d0e1f2a3b4c5"
down_revision = "c9d0e1f2a3b4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "refresh_tokens",
        sa.Column(
            "replaced_by_id",
            sa.UUID(),
            sa.ForeignKey("refresh_tokens.id", ondelete="SET NULL", name="fk_refresh_tokens_replaced_by_id"),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_refresh_tokens_token_hash",
        "refresh_tokens",
        ["token_hash"],
    )
    op.create_index(
        "ix_refresh_tokens_expires_at",
        "refresh_tokens",
        ["expires_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_refresh_tokens_expires_at", table_name="refresh_tokens")
    op.drop_index("ix_refresh_tokens_token_hash", table_name="refresh_tokens")
    op.drop_column("refresh_tokens", "replaced_by_id")
