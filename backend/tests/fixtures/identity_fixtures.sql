-- Identity and Access domain seed fixtures
--
-- These INSERT statements populate six demo users (one per ForgeGuard persona)
-- for use in integration and acceptance tests.
--
-- Passwords are "ForgeGuard123!" hashed with bcrypt cost-factor 12.
-- These hashes are pre-computed for testing only; rotate for production.
--
-- Usage:
--   psql $DATABASE_URL -f backend/tests/fixtures/identity_fixtures.sql
--
-- Prerequisites: the identity_access migration must have run first:
--   alembic upgrade head

BEGIN;

-- --------------------------------------------------------------------
-- Demo users — one per role
-- Use fixed UUIDs for deterministic cross-fixture references.
-- --------------------------------------------------------------------

-- developer: alice@example.com
INSERT INTO users (
    id, email, password_hash, role, is_active, failed_login_attempts,
    deleted_at, created_at, updated_at
) VALUES (
    '11111111-0000-4000-8000-000000000001',
    'alice@example.com',
    '$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8y7.xXj4pF.mY0gLXWc',
    'developer',
    TRUE, 0, NULL, NOW(), NOW()
);

-- tech_lead: bob@example.com
INSERT INTO users (
    id, email, password_hash, role, is_active, failed_login_attempts,
    deleted_at, created_at, updated_at
) VALUES (
    '22222222-0000-4000-8000-000000000002',
    'bob@example.com',
    '$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8y7.xXj4pF.mY0gLXWc',
    'tech_lead',
    TRUE, 0, NULL, NOW(), NOW()
);

-- security_reviewer: carol@example.com
INSERT INTO users (
    id, email, password_hash, role, is_active, failed_login_attempts,
    deleted_at, created_at, updated_at
) VALUES (
    '33333333-0000-4000-8000-000000000003',
    'carol@example.com',
    '$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8y7.xXj4pF.mY0gLXWc',
    'security_reviewer',
    TRUE, 0, NULL, NOW(), NOW()
);

-- platform_admin: dave@example.com
INSERT INTO users (
    id, email, password_hash, role, is_active, failed_login_attempts,
    deleted_at, created_at, updated_at
) VALUES (
    '44444444-0000-4000-8000-000000000004',
    'dave@example.com',
    '$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8y7.xXj4pF.mY0gLXWc',
    'platform_admin',
    TRUE, 0, NULL, NOW(), NOW()
);

-- engineering_manager: eve@example.com
INSERT INTO users (
    id, email, password_hash, role, is_active, failed_login_attempts,
    deleted_at, created_at, updated_at
) VALUES (
    '55555555-0000-4000-8000-000000000005',
    'eve@example.com',
    '$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8y7.xXj4pF.mY0gLXWc',
    'engineering_manager',
    TRUE, 0, NULL, NOW(), NOW()
);

-- operator: frank@example.com
INSERT INTO users (
    id, email, password_hash, role, is_active, failed_login_attempts,
    deleted_at, created_at, updated_at
) VALUES (
    '66666666-0000-4000-8000-000000000006',
    'frank@example.com',
    '$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8y7.xXj4pF.mY0gLXWc',
    'operator',
    TRUE, 0, NULL, NOW(), NOW()
);

COMMIT;
