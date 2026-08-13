"""Add BEFORE UPDATE/DELETE immutability trigger on audit_logs.

The audit_schema migration (0002) already enforces immutability via role-based
GRANTs (forgeguard_app has INSERT/SELECT only, no UPDATE/DELETE).  This
migration adds a second, independent layer of protection: a PL/pgSQL trigger
that fires BEFORE any UPDATE or DELETE on audit_logs and raises an exception.

This provides defence-in-depth:
  - Application layer: AuditLogRepository.update/soft_delete raise NotImplementedError.
  - Role layer: forgeguard_app role has no UPDATE/DELETE privilege (migration 0002).
  - Trigger layer (this migration): BEFORE UPDATE OR DELETE trigger rejects any
    attempt regardless of the database role performing it.

The trigger is intentionally NOT dropped by downgrade — removing immutability
protection from a live database is a manual DBA operation requiring explicit
sign-off, not an automated rollback.

Revision ID: b8c9d0e1f2a3
Revises:     a7b8c9d0e1f2 (seed_demo_data)
Create Date: 2026-08-11 00:07:00 UTC
"""

from __future__ import annotations

from alembic import op

revision: str = "b8c9d0e1f2a3"
down_revision: str | None = "a7b8c9d0e1f2"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    # Create the trigger function that rejects all UPDATE and DELETE attempts.
    op.execute("""
        CREATE OR REPLACE FUNCTION prevent_audit_modification()
        RETURNS TRIGGER
        LANGUAGE plpgsql
        AS $$
        BEGIN
            RAISE EXCEPTION
                'Audit records are immutable — UPDATE and DELETE are not permitted '
                'on the audit_logs table. Attempted operation: %', TG_OP;
            RETURN NULL;
        END;
        $$
    """)

    # Attach the trigger to the partitioned parent.  PostgreSQL 13+ automatically
    # propagates triggers to existing and future child partitions when attached to
    # the parent with FOR EACH ROW.
    op.execute("""
        CREATE TRIGGER trg_audit_logs_immutability
        BEFORE UPDATE OR DELETE ON audit_logs
        FOR EACH ROW EXECUTE FUNCTION prevent_audit_modification()
    """)


def downgrade() -> None:
    # Intentionally left as a no-op: removing immutability protection from
    # audit_logs requires explicit DBA action, not an automated rollback.
    # To manually revert: DROP TRIGGER trg_audit_logs_immutability ON audit_logs;
    pass
