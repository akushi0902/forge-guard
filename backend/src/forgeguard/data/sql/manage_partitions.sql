-- manage_partitions.sql
--
-- PL/pgSQL functions for audit_logs partition lifecycle management.
-- Called by a scheduled cron job (or Forge Shipping scheduled task) to:
--   1. Pre-create future monthly partitions (create_audit_partition).
--   2. Drop expired partitions for retention enforcement (drop_expired_audit_partitions).
--
-- Usage:
--   psql $DATABASE_URL -f backend/src/forgeguard/data/sql/manage_partitions.sql
--   -- Then call:
--   SELECT create_audit_partition('2027-01-01'::DATE);
--   SELECT drop_expired_audit_partitions(365);

-- ── create_audit_partition ───────────────────────────────────────────────────
--
-- Creates a monthly partition for audit_logs if it does not already exist.
-- Idempotent: calling for an existing partition is a no-op.
--
-- Arguments:
--   month_start DATE — first day of the target month (e.g., '2026-09-01').
--
-- Example:
--   SELECT create_audit_partition('2026-09-01'::DATE);

CREATE OR REPLACE FUNCTION create_audit_partition(month_start DATE)
RETURNS VOID
LANGUAGE plpgsql
AS $$
DECLARE
    partition_name TEXT;
    range_start    DATE;
    range_end      DATE;
BEGIN
    -- Normalise to first day of the month regardless of input day.
    range_start    := date_trunc('month', month_start)::DATE;
    range_end      := (range_start + INTERVAL '1 month')::DATE;
    partition_name := 'audit_logs_' || to_char(range_start, 'YYYY_MM');

    -- IF NOT EXISTS: check pg_class before attempting CREATE to stay idempotent
    -- even under concurrent calls (both processes see the table already exists).
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
$$;

-- ── drop_expired_audit_partitions ────────────────────────────────────────────
--
-- Drops monthly partitions whose data is entirely older than retention_days.
-- Safety check: never drops a partition that contains records within the
-- retention window.
--
-- Arguments:
--   retention_days INTEGER — number of days to retain records (default 365).
--
-- Returns:
--   INTEGER — number of partitions dropped.
--
-- Example:
--   SELECT drop_expired_audit_partitions(365);

CREATE OR REPLACE FUNCTION drop_expired_audit_partitions(
    retention_days INTEGER DEFAULT 365
)
RETURNS INTEGER
LANGUAGE plpgsql
AS $$
DECLARE
    rec             RECORD;
    cutoff_date     DATE;
    partition_end   DATE;
    dropped_count   INTEGER := 0;
BEGIN
    cutoff_date := (CURRENT_DATE - retention_days * INTERVAL '1 day')::DATE;

    -- Iterate over all child partitions of audit_logs.
    FOR rec IN
        SELECT
            c.relname                                       AS partition_name,
            -- Extract the upper bound from pg_get_expr for the partition constraint.
            pg_get_expr(c.relpartbound, c.oid, TRUE)        AS partition_bound
        FROM   pg_class     p
        JOIN   pg_inherits   i ON i.inhparent = p.oid
        JOIN   pg_class      c ON c.oid = i.inhrelid
        JOIN   pg_namespace  n ON n.oid = p.relnamespace
        WHERE  p.relname  = 'audit_logs'
        AND    n.nspname  = current_schema()
        ORDER BY c.relname
    LOOP
        -- Parse the upper bound date from the partition name (YYYY_MM suffix).
        -- Format: audit_logs_YYYY_MM
        BEGIN
            partition_end := (
                to_date(
                    substring(rec.partition_name FROM 'audit_logs_(.+)$'),
                    'YYYY_MM'
                ) + INTERVAL '1 month'
            )::DATE;
        EXCEPTION WHEN OTHERS THEN
            -- Skip partitions whose names don't follow the expected pattern.
            CONTINUE;
        END;

        -- Only drop if the partition's entire date range is before the cutoff.
        IF partition_end <= cutoff_date THEN
            RAISE NOTICE 'Dropping expired partition %  (upper bound %)',
                         rec.partition_name, partition_end;
            EXECUTE format('DROP TABLE IF EXISTS %I', rec.partition_name);
            dropped_count := dropped_count + 1;
        END IF;
    END LOOP;

    RAISE NOTICE 'drop_expired_audit_partitions: dropped % partition(s) '
                 '(retention=% days, cutoff=%)',
                 dropped_count, retention_days, cutoff_date;

    RETURN dropped_count;
END;
$$;
