"""Add approver_role to exceptions; composite indexes for routing (WO-062).

Revision ID: b3c4d5e6f7a8
Revises: a2b3c4d5e6f7
Create Date: 2026-08-12

Changes:
  - Add exceptions.approver_role VARCHAR(30) NOT NULL (backfill: 'platform_admin')
  - Extend status CHECK to also accept 'pending' (synonym for the initial state)
  - Add composite indexes:
      ix_exceptions_finding_id_status  (finding_id, status)
      ix_exceptions_expires_at_status  (expires_at, status)
      ix_exceptions_approver_role_status (approver_role, status)
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "b3c4d5e6f7a8"
down_revision: str | None = "a2b3c4d5e6f7"
branch_labels = None
depends_on = None

_NEW_STATUS_CHECK = (
    "status IN ('pending','requested','approved','denied','expired')"
)
_OLD_STATUS_CHECK = "status IN ('requested','approved','denied','expired')"


def upgrade() -> None:
    # Add approver_role column — backfill existing rows with 'platform_admin'.
    op.add_column(
        "exceptions",
        sa.Column(
            "approver_role",
            sa.String(30),
            nullable=True,
        ),
    )
    op.execute(
        "UPDATE exceptions SET approver_role = 'platform_admin' WHERE approver_role IS NULL"
    )
    op.alter_column("exceptions", "approver_role", nullable=False)

    # Extend status CHECK to accept 'pending' as an alias for the initial state.
    op.drop_constraint("ck_exceptions_valid_exception_status", "exceptions", type_="check")
    op.create_check_constraint(
        "valid_exception_status",
        "exceptions",
        _NEW_STATUS_CHECK,
    )

    # Composite indexes for the routing and expiry query patterns.
    op.create_index(
        "ix_exceptions_finding_id_status",
        "exceptions",
        ["finding_id", "status"],
    )
    op.create_index(
        "ix_exceptions_expires_at_status",
        "exceptions",
        ["expires_at", "status"],
    )
    op.create_index(
        "ix_exceptions_approver_role_status",
        "exceptions",
        ["approver_role", "status"],
    )


def downgrade() -> None:
    op.drop_index("ix_exceptions_approver_role_status", table_name="exceptions")
    op.drop_index("ix_exceptions_expires_at_status", table_name="exceptions")
    op.drop_index("ix_exceptions_finding_id_status", table_name="exceptions")

    op.drop_constraint("ck_exceptions_valid_exception_status", "exceptions", type_="check")
    op.create_check_constraint(
        "valid_exception_status",
        "exceptions",
        _OLD_STATUS_CHECK,
    )

    op.drop_column("exceptions", "approver_role")
