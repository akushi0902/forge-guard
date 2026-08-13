"""Audit domain schema: audit_logs (partitioned) + ai_conversations.

Creates:
    audit_logs         — range-partitioned (monthly) on created_at; immutable
                         for the application role (INSERT/SELECT only).
    ai_conversations   — AI Agent interaction history linked to users.
    Partition functions: create_audit_partition, drop_expired_audit_partitions
    Initial partitions: current month + 3 future months (dynamic DO block)
    Database roles:     forgeguard_app (INSERT/SELECT), forgeguard_admin (ALL)

Revision ID: c3d4e5f6a7b8
Revises:     b2c3d4e5f6a7 (governance_schema)
Create Date: 2026-08-11 00:02:00 UTC
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# ---------------------------------------------------------------------------
# Revision identifiers
# ---------------------------------------------------------------------------
revision: str = "c3d4e5f6a7b8"
down_revision: str | None = "b2c3d4e5f6a7"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    # ── audit_logs — partitioned parent table ────────────────────────────── #
    # SQLAlchemy's declarative `create_all` cannot create partitioned tables,
    # so we use raw SQL via op.execute() for the entire audit_logs DDL.
    op.execute("""
        CREATE TABLE audit_logs (
            id                UUID        NOT NULL DEFAULT gen_random_uuid(),
            actor_id          UUID        REFERENCES users(id) ON DELETE SET NULL,
            actor_role        VARCHAR(50) NOT NULL,
            action            VARCHAR(255) NOT NULL,
            resource_type     VARCHAR(100) NOT NULL,
            resource_id       UUID,
            before_state      JSONB,
            after_state       JSONB,
            ip_address_masked VARCHAR(45),
            correlation_id    VARCHAR(36),
            created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
            PRIMARY KEY (id, created_at)
        ) PARTITION BY RANGE (created_at)
    """)

    # Composite indexes on parent — PostgreSQL 11+ propagates to all partitions.
    op.execute("""
        CREATE INDEX ix_audit_logs_actor_id_created_at
            ON audit_logs (actor_id, created_at)
    """)
    op.execute("""
        CREATE INDEX ix_audit_logs_resource_type_resource_id_created_at
            ON audit_logs (resource_type, resource_id, created_at)
    """)
    op.execute("""
        CREATE INDEX ix_audit_logs_correlation_id
            ON audit_logs (correlation_id)
    """)

    # ── Initial monthly partitions: current month + 3 future months ─────── #
    # Uses a DO block so the partition dates are computed dynamically at
    # migration time — correct regardless of when the migration runs.
    op.execute("""
        DO $$
        DECLARE
            i             INT;
            month_start   DATE;
            month_end     DATE;
            partition_name TEXT;
        BEGIN
            FOR i IN 0..3 LOOP
                month_start    := date_trunc('month', CURRENT_DATE + (i || ' months')::INTERVAL)::DATE;
                month_end      := (month_start + INTERVAL '1 month')::DATE;
                partition_name := 'audit_logs_' || to_char(month_start, 'YYYY_MM');

                IF NOT EXISTS (
                    SELECT 1 FROM pg_class c
                    JOIN pg_namespace n ON n.oid = c.relnamespace
                    WHERE c.relname = partition_name
                    AND n.nspname = current_schema()
                ) THEN
                    EXECUTE format(
                        'CREATE TABLE %I PARTITION OF audit_logs '
                        'FOR VALUES FROM (%L) TO (%L)',
                        partition_name,
                        month_start::TEXT,
                        month_end::TEXT
                    );
                END IF;
            END LOOP;
        END;
        $$
    """)

    # ── PL/pgSQL partition management functions ──────────────────────────── #
    op.execute("""
        CREATE OR REPLACE FUNCTION create_audit_partition(month_start DATE)
        RETURNS VOID
        LANGUAGE plpgsql
        AS $func$
        DECLARE
            partition_name TEXT;
            range_start    DATE;
            range_end      DATE;
        BEGIN
            range_start    := date_trunc('month', month_start)::DATE;
            range_end      := (range_start + INTERVAL '1 month')::DATE;
            partition_name := 'audit_logs_' || to_char(range_start, 'YYYY_MM');

            IF NOT EXISTS (
                SELECT 1
                FROM   pg_class     c
                JOIN   pg_namespace n ON n.oid = c.relnamespace
                WHERE  c.relname = partition_name
                AND    n.nspname = current_schema()
            ) THEN
                EXECUTE format(
                    'CREATE TABLE %I PARTITION OF audit_logs '
                    'FOR VALUES FROM (%L) TO (%L)',
                    partition_name,
                    range_start::TEXT,
                    range_end::TEXT
                );
                RAISE NOTICE 'Created partition %', partition_name;
            ELSE
                RAISE NOTICE 'Partition % already exists — skipping', partition_name;
            END IF;
        END;
        $func$
    """)

    op.execute("""
        CREATE OR REPLACE FUNCTION drop_expired_audit_partitions(
            retention_days INTEGER DEFAULT 365
        )
        RETURNS INTEGER
        LANGUAGE plpgsql
        AS $func$
        DECLARE
            rec             RECORD;
            cutoff_date     DATE;
            partition_end   DATE;
            dropped_count   INTEGER := 0;
        BEGIN
            cutoff_date := (CURRENT_DATE - retention_days * INTERVAL '1 day')::DATE;

            FOR rec IN
                SELECT c.relname AS partition_name
                FROM   pg_class     p
                JOIN   pg_inherits   i ON i.inhparent = p.oid
                JOIN   pg_class      c ON c.oid = i.inhrelid
                JOIN   pg_namespace  n ON n.oid = p.relnamespace
                WHERE  p.relname  = 'audit_logs'
                AND    n.nspname  = current_schema()
                ORDER BY c.relname
            LOOP
                BEGIN
                    partition_end := (
                        to_date(
                            substring(rec.partition_name FROM 'audit_logs_(.+)$'),
                            'YYYY_MM'
                        ) + INTERVAL '1 month'
                    )::DATE;
                EXCEPTION WHEN OTHERS THEN
                    CONTINUE;
                END;

                IF partition_end <= cutoff_date THEN
                    EXECUTE format('DROP TABLE IF EXISTS %I', rec.partition_name);
                    dropped_count := dropped_count + 1;
                END IF;
            END LOOP;

            RETURN dropped_count;
        END;
        $func$
    """)

    # ── ai_conversations ─────────────────────────────────────────────────── #
    op.create_table(
        "ai_conversations",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "messages",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="[]",
            nullable=False,
        ),
        sa.Column(
            "context_refs",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_ai_conversations_user_id_users",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_ai_conversations"),
    )
    op.create_index(
        "ix_ai_conversations_user_id", "ai_conversations", ["user_id"]
    )

    # ── Database roles for immutability enforcement ───────────────────────── #
    # CREATE ROLE uses IF NOT EXISTS (PG 9.6+) to be idempotent.
    # Roles are created at the database level outside of any transaction; we
    # COMMIT the current transaction first then run role DDL in autocommit.
    # In practice, role creation is idempotent and safe to run multiple times.
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'forgeguard_app') THEN
                CREATE ROLE forgeguard_app;
            END IF;
            IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'forgeguard_admin') THEN
                CREATE ROLE forgeguard_admin;
            END IF;
        END;
        $$
    """)
    # Grant INSERT and SELECT to the application role (no UPDATE/DELETE).
    op.execute("GRANT INSERT, SELECT ON audit_logs TO forgeguard_app")
    op.execute("GRANT ALL ON audit_logs TO forgeguard_admin")
    op.execute("GRANT INSERT, SELECT, UPDATE, DELETE ON ai_conversations TO forgeguard_app")
    op.execute("GRANT ALL ON ai_conversations TO forgeguard_admin")


def downgrade() -> None:
    # Revoke grants before dropping objects.
    op.execute("REVOKE ALL ON ai_conversations FROM forgeguard_app, forgeguard_admin")
    op.execute("REVOKE ALL ON audit_logs FROM forgeguard_app, forgeguard_admin")

    op.drop_index("ix_ai_conversations_user_id", table_name="ai_conversations")
    op.drop_table("ai_conversations")

    op.execute("DROP FUNCTION IF EXISTS drop_expired_audit_partitions(INTEGER)")
    op.execute("DROP FUNCTION IF EXISTS create_audit_partition(DATE)")

    # Drop all child partitions first, then the parent.
    op.execute("""
        DO $$
        DECLARE rec RECORD;
        BEGIN
            FOR rec IN
                SELECT c.relname
                FROM   pg_class p
                JOIN   pg_inherits i ON i.inhparent = p.oid
                JOIN   pg_class c ON c.oid = i.inhrelid
                JOIN   pg_namespace n ON n.oid = p.relnamespace
                WHERE  p.relname = 'audit_logs'
                AND    n.nspname = current_schema()
            LOOP
                EXECUTE format('DROP TABLE IF EXISTS %I', rec.relname);
            END LOOP;
        END;
        $$
    """)
    op.execute("DROP TABLE IF EXISTS audit_logs")

    # Note: database roles are intentionally NOT dropped on downgrade — they
    # may be shared across schema versions or used by other objects.
