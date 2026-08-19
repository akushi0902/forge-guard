"""Update findings status lifecycle to WO-041 values (WO-041).

Revision ID: f7a8b9c0d1e2
Revises: e6f7a8b9c0d1
Create Date: 2026-08-12

Changes:
  - DROP old valid_finding_status CHECK constraint ('open','in_progress','resolved','suppressed')
  - ADD new valid_finding_status CHECK constraint ('open','acknowledged','remediated',
    'exception_granted','reopened')
  - ADD unique partial index idx_findings_dedup ON findings(service_id, policy_rule_id)
    WHERE status = 'open'  [prevents duplicate open findings for the same rule+service]
  - ADD composite index idx_findings_service_policy_rule_status for duplicate-detection queries
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "f7a8b9c0d1e2"
down_revision: str = "e6f7a8b9c0d1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Replace the finding status CHECK constraint with new lifecycle values.
    op.drop_constraint("ck_findings_valid_finding_status", "findings", type_="check")
    op.create_check_constraint(
        "valid_finding_status",
        "findings",
        "status IN ('open','acknowledged','remediated','exception_granted','reopened')",
    )

    # Unique partial index: only one open finding per (service, rule) pair.
    op.create_index(
        "idx_findings_dedup",
        "findings",
        ["service_id", "policy_rule_id"],
        unique=True,
        postgresql_where=sa.text("status = 'open'"),
    )

    # Composite index used by find_existing_open_finding and list_by_service.
    op.create_index(
        "idx_findings_service_policy_rule_status",
        "findings",
        ["service_id", "policy_rule_id", "status"],
    )


def downgrade() -> None:
    op.drop_index("idx_findings_service_policy_rule_status", table_name="findings")
    op.drop_index("idx_findings_dedup", table_name="findings")
    op.drop_constraint("ck_findings_valid_finding_status", "findings", type_="check")
    op.create_check_constraint(
        "valid_finding_status",
        "findings",
        "status IN ('open','in_progress','resolved','suppressed')",
    )
