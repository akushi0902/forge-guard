"""Add composite indexes for knowledge base retrieval performance (WO-067).

Revision ID: c1d2e3f4a5b6
Revises: b0c1d2e3f4a5
Create Date: 2026-08-13

Adds three composite indexes to support the 2-second latency SLA for
agent knowledge base retrieval queries:

    1. (service_id, severity) on findings           — FindingsRetriever filters
    2. (service_id, created_at DESC) on assessments — HealthRetriever latest-assessment lookup
    3. (service_id, created_at DESC) on release_assessments — ReleaseRetriever latest-assessment lookup

The assessments index already exists as ix_assessments_service_id_created_at
and the release_assessments index as ix_release_assessments_service_id_created_at
(created in migration 20260811_0004). We only add the findings composite index
here if it does not already exist.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "c1d2e3f4a5b6"
down_revision = "b0c1d2e3f4a5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── findings (service_id, severity) ──────────────────────────────────
    # The existing index ix_findings_service_id_severity_status covers
    # (service_id, severity, status).  We add a more targeted 2-column
    # index for severity-only filter queries used by FindingsRetriever.
    op.execute(
        """
        CREATE INDEX CONCURRENTLY IF NOT EXISTS
            ix_findings_service_id_severity
        ON findings (service_id, severity)
        """
    )

    # ── assessments (service_id, created_at DESC) ─────────────────────────
    # ix_assessments_service_id_created_at already covers (service_id, created_at)
    # in ASC order.  Add a DESC-specific index for the ORDER BY created_at DESC
    # pattern in HealthRetriever.
    op.execute(
        """
        CREATE INDEX CONCURRENTLY IF NOT EXISTS
            ix_assessments_service_id_created_at_desc
        ON assessments (service_id, created_at DESC)
        """
    )

    # ── release_assessments (service_id, created_at DESC) ────────────────
    # ix_release_assessments_service_id_created_at covers ASC order.
    # Add a DESC-specific index for ReleaseRetriever.
    op.execute(
        """
        CREATE INDEX CONCURRENTLY IF NOT EXISTS
            ix_release_assessments_service_id_created_at_desc
        ON release_assessments (service_id, created_at DESC)
        """
    )


def downgrade() -> None:
    op.execute(
        "DROP INDEX CONCURRENTLY IF EXISTS ix_findings_service_id_severity"
    )
    op.execute(
        "DROP INDEX CONCURRENTLY IF EXISTS ix_assessments_service_id_created_at_desc"
    )
    op.execute(
        "DROP INDEX CONCURRENTLY IF EXISTS ix_release_assessments_service_id_created_at_desc"
    )
