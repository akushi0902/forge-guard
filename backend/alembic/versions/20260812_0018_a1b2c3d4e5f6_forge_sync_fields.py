"""Add forge_sync_status and last_synced_at to services table.

Revision ID: a1b2c3d4e5f6
Revises: f3a4b5c6d7e8
Create Date: 2026-08-12

Adds two columns to SERVICES for Forge Catalog bidirectional sync (WO-089):
  forge_sync_status — VARCHAR(20) NOT NULL DEFAULT 'pending'
  last_synced_at    — TIMESTAMPTZ nullable

Also adds an index on forge_sync_status for efficient status queries.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "a1b2c3d4e5f6"
down_revision = "f3a4b5c6d7e8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "services",
        sa.Column(
            "forge_sync_status",
            sa.String(20),
            nullable=False,
            server_default="pending",
        ),
    )
    op.add_column(
        "services",
        sa.Column(
            "last_synced_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )
    op.create_index(
        "idx_services_forge_sync_status",
        "services",
        ["forge_sync_status"],
    )


def downgrade() -> None:
    op.drop_index("idx_services_forge_sync_status", table_name="services")
    op.drop_column("services", "last_synced_at")
    op.drop_column("services", "forge_sync_status")
