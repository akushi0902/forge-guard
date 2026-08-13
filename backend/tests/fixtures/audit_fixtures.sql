-- Audit domain test fixtures
--
-- Sample audit_logs records spanning multiple months for testing:
--   - Partition routing (records landing in the correct monthly partition)
--   - Cross-partition SELECT queries
--   - Retention enforcement testing (records in 2025 are well outside 365-day window)
--
-- Prerequisites:
--   1. identity_fixtures.sql must have been loaded (provides actor_id UUIDs).
--   2. The audit schema migration must have run:
--        alembic upgrade head
--   3. The target partition must exist.  If running standalone, call:
--        SELECT create_audit_partition('2025-01-01'::DATE);
--        SELECT create_audit_partition('2025-06-01'::DATE);
--        SELECT create_audit_partition('2025-12-01'::DATE);
--
-- Usage:
--   psql $DATABASE_URL -f backend/tests/fixtures/identity_fixtures.sql
--   psql $DATABASE_URL -f backend/tests/fixtures/audit_fixtures.sql
--
-- Fixed actor UUIDs (from identity_fixtures.sql):
--   alice   (developer):           '11111111-0000-4000-8000-000000000001'
--   bob     (tech_lead):           '22222222-0000-4000-8000-000000000002'
--   carol   (security_reviewer):   '33333333-0000-4000-8000-000000000003'
--   dave    (platform_admin):      '44444444-0000-4000-8000-000000000004'
--   eve     (engineering_manager): '55555555-0000-4000-8000-000000000005'
--   frank   (operator):            '66666666-0000-4000-8000-000000000006'

BEGIN;

-- ─────────────────────────────────────────────────────────────────────────────
-- January 2025 events (in partition audit_logs_2025_01)
-- ─────────────────────────────────────────────────────────────────────────────

INSERT INTO audit_logs (
    id, actor_id, actor_role, action, resource_type, resource_id,
    before_state, after_state, ip_address_masked, correlation_id, created_at
) VALUES (
    'dddddddd-0001-4000-8000-000000000001',
    '22222222-0000-4000-8000-000000000002',
    'tech_lead',
    'policy.created',
    'policy',
    'bbbbbbbb-0000-4000-8000-000000000001',
    NULL,
    '{"name": "Code Quality Standards", "dimension": "code_quality", "is_active": true}',
    '192.168.xxx.xxx',
    'req-aaa-001',
    '2025-01-10 09:00:00+00'
);

INSERT INTO audit_logs (
    id, actor_id, actor_role, action, resource_type, resource_id,
    before_state, after_state, ip_address_masked, correlation_id, created_at
) VALUES (
    'dddddddd-0001-4000-8000-000000000002',
    '22222222-0000-4000-8000-000000000002',
    'tech_lead',
    'policy_rule.created',
    'policy_rule',
    'cccccccc-0000-4000-8000-000000000001',
    NULL,
    '{"name": "Cyclomatic Complexity Limit", "severity": "high", "threshold_config": {"operator": "lte", "value": 10}}',
    '192.168.xxx.xxx',
    'req-aaa-002',
    '2025-01-10 09:15:00+00'
);

INSERT INTO audit_logs (
    id, actor_id, actor_role, action, resource_type, resource_id,
    before_state, after_state, ip_address_masked, correlation_id, created_at
) VALUES (
    'dddddddd-0001-4000-8000-000000000003',
    '11111111-0000-4000-8000-000000000001',
    'developer',
    'service.registered',
    'service',
    'aaaaaaaa-0000-4000-8000-000000000001',
    NULL,
    '{"name": "Payment Service", "is_demo": true}',
    '10.0.xxx.xxx',
    'req-aaa-003',
    '2025-01-15 14:30:00+00'
);

-- ─────────────────────────────────────────────────────────────────────────────
-- June 2025 events (in partition audit_logs_2025_06)
-- ─────────────────────────────────────────────────────────────────────────────

INSERT INTO audit_logs (
    id, actor_id, actor_role, action, resource_type, resource_id,
    before_state, after_state, ip_address_masked, correlation_id, created_at
) VALUES (
    'dddddddd-0006-4000-8000-000000000001',
    '33333333-0000-4000-8000-000000000003',
    'security_reviewer',
    'policy_rule.updated',
    'policy_rule',
    'cccccccc-0000-4000-8000-000000000009',
    '{"severity": "high"}',
    '{"severity": "critical"}',
    '172.16.xxx.xxx',
    'req-bbb-001',
    '2025-06-01 11:00:00+00'
);

INSERT INTO audit_logs (
    id, actor_id, actor_role, action, resource_type, resource_id,
    before_state, after_state, ip_address_masked, correlation_id, created_at
) VALUES (
    'dddddddd-0006-4000-8000-000000000002',
    '44444444-0000-4000-8000-000000000004',
    'platform_admin',
    'release.approved',
    'release_decision',
    NULL,
    NULL,
    '{"outcome": "approve", "rationale": "All gates passed", "service": "Payment Service"}',
    '10.10.xxx.xxx',
    'req-bbb-002',
    '2025-06-15 16:45:00+00'
);

-- ─────────────────────────────────────────────────────────────────────────────
-- December 2025 events (in partition audit_logs_2025_12)
-- ─────────────────────────────────────────────────────────────────────────────

INSERT INTO audit_logs (
    id, actor_id, actor_role, action, resource_type, resource_id,
    before_state, after_state, ip_address_masked, correlation_id, created_at
) VALUES (
    'dddddddd-0012-4000-8000-000000000001',
    '55555555-0000-4000-8000-000000000005',
    'engineering_manager',
    'policy.deactivated',
    'policy',
    'bbbbbbbb-0000-4000-8000-000000000004',
    '{"is_active": true}',
    '{"is_active": false}',
    '192.168.xxx.xxx',
    'req-ccc-001',
    '2025-12-20 08:00:00+00'
);

INSERT INTO audit_logs (
    id, actor_id, actor_role, action, resource_type, resource_id,
    before_state, after_state, ip_address_masked, correlation_id, created_at
) VALUES (
    'dddddddd-0012-4000-8000-000000000002',
    NULL,
    'system',
    'partition.maintenance',
    'database',
    NULL,
    NULL,
    '{"action": "partition_created", "partition": "audit_logs_2026_01"}',
    NULL,
    NULL,
    '2025-12-31 23:59:00+00'
);

COMMIT;

-- ─────────────────────────────────────────────────────────────────────────────
-- Verification queries (run manually to inspect the data)
-- ─────────────────────────────────────────────────────────────────────────────
-- SELECT COUNT(*) FROM audit_logs;                           -- 7 total
-- SELECT COUNT(*) FROM audit_logs_2025_01;                   -- 3 records
-- SELECT COUNT(*) FROM audit_logs_2025_06;                   -- 2 records
-- SELECT COUNT(*) FROM audit_logs_2025_12;                   -- 2 records
-- SELECT DISTINCT resource_type FROM audit_logs;             -- 5 types
-- SELECT actor_role, COUNT(*) FROM audit_logs GROUP BY 1;    -- role breakdown
