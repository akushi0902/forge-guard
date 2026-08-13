"""Expand findings.dimension CHECK constraint for release_guardian dimensions.

The original constraint (from WO-009 assessments schema) allowed only policy
guardian dimension values.  The Release Guardian (WO-046 / WO-047) uses a
different set of dimension names.  This migration replaces the constraint with a
broader one that includes both sets.

Old values: code_quality, test_coverage, security, documentation, operations_readiness
New values (added): code_complexity, dependencies, historical

Revision ID: f2a3b4c5d6e7
Revises:     e1f2a3b4c5d6 (seed_anonymized_user)
Create Date: 2026-08-11 00:11:00 UTC
"""

from __future__ import annotations

from alembic import op

revision: str = "f2a3b4c5d6e7"
down_revision: str | None = "e1f2a3b4c5d6"
branch_labels: str | None = None
depends_on: str | None = None

_OLD_CONSTRAINT = "ck_findings_valid_dimension"
_NEW_CONSTRAINT = "ck_findings_valid_dimension"

_OLD_CHECK = (
    "dimension IN ("
    "'code_quality','test_coverage','security',"
    "'documentation','operations_readiness'"
    ")"
)
_NEW_CHECK = (
    "dimension IN ("
    "'code_quality','test_coverage','security',"
    "'documentation','operations_readiness',"
    "'code_complexity','dependencies','historical'"
    ")"
)


def upgrade() -> None:
    op.drop_constraint(_OLD_CONSTRAINT, "findings", type_="check")
    op.create_check_constraint(_NEW_CONSTRAINT, "findings", _NEW_CHECK)


def downgrade() -> None:
    op.drop_constraint(_NEW_CONSTRAINT, "findings", type_="check")
    op.create_check_constraint(_OLD_CONSTRAINT, "findings", _OLD_CHECK)
