"""Add rule_type CHECK constraint, weight range check, and unique active policy index.

Revision ID: a2b3c4d5e6f7
Revises: f2a3b4c5d6e7
Create Date: 2026-08-11

Adds the missing constraints from WO-035 that were not present in the
initial governance schema migration (WO-008):
  - CHECK constraint on policy_rules.rule_type (enum enforcement)
  - CHECK constraint on policy_rules.weight (0-100 range)
  - Unique partial index on policies(name, dimension) WHERE is_active = TRUE
    to prevent duplicate active policy names within the same dimension.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "a2b3c4d5e6f7"
down_revision: str | None = "f2a3b4c5d6e7"
branch_labels = None
depends_on = None

_RULE_TYPE_CHECK = (
    "rule_type IN ("
    "'threshold_gte','threshold_lte','threshold_eq',"
    "'regex_match','regex_no_match'"
    ")"
)

_WEIGHT_CHECK = "weight >= 0 AND weight <= 100"


def upgrade() -> None:
    # Enforce rule_type enumeration at DB level.
    op.create_check_constraint(
        "ck_policy_rules_valid_rule_type",
        "policy_rules",
        _RULE_TYPE_CHECK,
    )

    # Enforce weight is within 0-100 scoring range.
    op.create_check_constraint(
        "ck_policy_rules_weight_range",
        "policy_rules",
        _WEIGHT_CHECK,
    )

    # Prevent two active policies with the same name in the same dimension.
    op.create_index(
        "uq_policies_name_dimension_active",
        "policies",
        ["name", "dimension"],
        unique=True,
        postgresql_where=sa.text("is_active = TRUE"),
    )


def downgrade() -> None:
    op.drop_index("uq_policies_name_dimension_active", table_name="policies")
    op.drop_constraint("ck_policy_rules_weight_range", "policy_rules", type_="check")
    op.drop_constraint("ck_policy_rules_valid_rule_type", "policy_rules", type_="check")
