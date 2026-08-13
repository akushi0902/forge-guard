-- create_audit_partitions.sql
--
-- Creates the audit_logs partitioned table and initial monthly partitions.
-- Called by the Alembic migration via op.execute().
--
-- This file is also usable standalone for documentation or manual recovery:
--   psql $DATABASE_URL -f backend/src/forgeguard/data/sql/create_audit_partitions.sql
--
-- PostgreSQL 11+ automatically propagates parent-table indexes to new
-- partitions when you create indexes on the parent.

-- ── Partitioned parent table ─────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS audit_logs (
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
) PARTITION BY RANGE (created_at);

-- ── Composite indexes on the parent table ────────────────────────────────────
-- PG 11+ propagates these to all existing and future partitions automatically.

CREATE INDEX IF NOT EXISTS ix_audit_logs_actor_id_created_at
    ON audit_logs (actor_id, created_at);

CREATE INDEX IF NOT EXISTS ix_audit_logs_resource_type_resource_id_created_at
    ON audit_logs (resource_type, resource_id, created_at);

CREATE INDEX IF NOT EXISTS ix_audit_logs_correlation_id
    ON audit_logs (correlation_id);

-- ── Initial monthly partitions ───────────────────────────────────────────────
-- The migration's DO block creates current month + 3 future months dynamically.
-- This file documents the static DDL pattern for a single partition.
--
-- Example (not executed here — see DO block in migration):
--
-- CREATE TABLE audit_logs_2026_08
--     PARTITION OF audit_logs
--     FOR VALUES FROM ('2026-08-01') TO ('2026-09-01');
