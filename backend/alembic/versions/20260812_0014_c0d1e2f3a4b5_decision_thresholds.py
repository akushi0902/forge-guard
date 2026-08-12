"""Create DECISION_THRESHOLDS table (WO-049).

Revision ID: c0d1e2f3a4b5
Revises: b9c0d1e2f3a4
Create Date: 2026-08-12

Changes:
  - CREATE TABLE decision_thresholds with configurable APPROVE/CONDITIONAL_APPROVE thresholds
  - PARTIAL UNIQUE INDEX on (is_active) WHERE is_active = true enforces single-active config
  - Composite index on created_at DESC for efficient list ordering
  - Default seed: one active threshold configuration with documented defaults
"""

from __future__ import annotations

import uuid

from alembic import op
import sqlalchemy as sa

revision = "c0d1e2f3a4b5"
down_revision = "b9c0d1e2f3a4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE decision_thresholds (
            id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            name                    VARCHAR(255) NOT NULL,
            approve_health_min      DECIMAL(5,2) NOT NULL DEFAULT 70.00
                                        CHECK (approve_health_min >= 0 AND approve_health_min <= 100),
            approve_risk_max        DECIMAL(5,2) NOT NULL DEFAULT 30.00
                                        CHECK (approve_risk_max >= 0 AND approve_risk_max <= 100),
            conditional_health_min  DECIMAL(5,2) NOT NULL DEFAULT 50.00
                                        CHECK (conditional_health_min >= 0 AND conditional_health_min <= 100),
            conditional_risk_max    DECIMAL(5,2) NOT NULL DEFAULT 60.00
                                        CHECK (conditional_risk_max >= 0 AND conditional_risk_max <= 100),
            is_active               BOOLEAN NOT NULL DEFAULT false,
            created_by              UUID REFERENCES users(id) ON DELETE SET NULL,
            updated_by              UUID REFERENCES users(id) ON DELETE SET NULL,
            created_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at              TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)

    # Partial unique index: only one row may have is_active = true at a time.
    op.execute("""
        CREATE UNIQUE INDEX uq_decision_thresholds_active
            ON decision_thresholds (is_active)
            WHERE is_active = true
    """)

    # Ordering index for list endpoints.
    op.execute("""
        CREATE INDEX idx_decision_thresholds_created_at
            ON decision_thresholds (created_at DESC)
    """)

    # Seed the default threshold configuration.
    default_id = str(uuid.UUID("f0000000-0000-0000-0000-000000000001"))
    op.execute(f"""
        INSERT INTO decision_thresholds
            (id, name, approve_health_min, approve_risk_max,
             conditional_health_min, conditional_risk_max, is_active)
        VALUES
            ('{default_id}',
             'Default Threshold',
             70.00, 30.00, 50.00, 60.00,
             true)
        ON CONFLICT DO NOTHING
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS decision_thresholds CASCADE")
