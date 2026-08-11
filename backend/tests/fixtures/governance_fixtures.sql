-- Governance domain seed fixtures
--
-- Inserts demo data for:
--   3 services   (Payment Service [is_demo=true], Auth Service, Catalog Service)
--   5 policies   (one per engineering dimension)
--   15 policy rules (3 per policy, covering all severity levels + JSONB configs)
--
-- Prerequisites:
--   1. identity_fixtures.sql must have been loaded (provides the created_by user).
--   2. The governance_schema migration must have run:
--        alembic upgrade head
--
-- Usage:
--   psql $DATABASE_URL -f backend/tests/fixtures/identity_fixtures.sql
--   psql $DATABASE_URL -f backend/tests/fixtures/governance_fixtures.sql
--
-- Fixed UUIDs are used for deterministic cross-fixture references.
-- The 'created_by' FK references bob@example.com (tech_lead) from identity_fixtures.
--
-- created_by user: '22222222-0000-4000-8000-000000000002' (bob@example.com, tech_lead)

BEGIN;

-- ─────────────────────────────────────────────────────────────────────────────
-- Services
-- ─────────────────────────────────────────────────────────────────────────────

-- Payment Service — demo service representing the canonical ForgeGuard example
INSERT INTO services (
    id, name, description, repository_url, owner_team,
    metadata, forge_catalog_id, is_demo,
    deleted_at, created_at, updated_at
) VALUES (
    'aaaaaaaa-0000-4000-8000-000000000001',
    'Payment Service',
    'Handles payment processing and transaction management for the platform.',
    'https://github.com/example/payment-service',
    'Payments Team',
    '{"language": "Python", "framework": "FastAPI", "team_size": 6, "tier": "critical", "sla": "99.99%"}',
    NULL,
    TRUE,
    NULL, NOW(), NOW()
);

-- Auth Service — handles authentication and token issuance
INSERT INTO services (
    id, name, description, repository_url, owner_team,
    metadata, forge_catalog_id, is_demo,
    deleted_at, created_at, updated_at
) VALUES (
    'aaaaaaaa-0000-4000-8000-000000000002',
    'Auth Service',
    'JWT-based authentication and RBAC enforcement service.',
    'https://github.com/example/auth-service',
    'Platform Team',
    '{"language": "Go", "framework": "gin", "team_size": 4, "tier": "critical", "sla": "99.99%"}',
    NULL,
    FALSE,
    NULL, NOW(), NOW()
);

-- Catalog Service — integrates with Forge Catalog for service discovery
INSERT INTO services (
    id, name, description, repository_url, owner_team,
    metadata, forge_catalog_id, is_demo,
    deleted_at, created_at, updated_at
) VALUES (
    'aaaaaaaa-0000-4000-8000-000000000003',
    'Catalog Service',
    'Service discovery and metadata management integrated with Forge Catalog.',
    'https://github.com/example/catalog-service',
    'Engineering Platform Team',
    '{"language": "TypeScript", "framework": "NestJS", "team_size": 3, "tier": "standard", "sla": "99.9%"}',
    'cccccccc-0000-4000-8000-000000000099',
    FALSE,
    NULL, NOW(), NOW()
);


-- ─────────────────────────────────────────────────────────────────────────────
-- Policies — one per engineering dimension
-- All policies are linked to Payment Service (the demo service).
-- created_by: bob@example.com (tech_lead)
-- ─────────────────────────────────────────────────────────────────────────────

-- code_quality policy
INSERT INTO policies (
    id, service_id, name, dimension, description,
    is_active, version, created_by, deleted_at, created_at, updated_at
) VALUES (
    'bbbbbbbb-0000-4000-8000-000000000001',
    'aaaaaaaa-0000-4000-8000-000000000001',
    'Code Quality Standards',
    'code_quality',
    'Enforces code complexity, maintainability, and style standards.',
    TRUE, 1, '22222222-0000-4000-8000-000000000002',
    NULL, NOW(), NOW()
);

-- test_coverage policy
INSERT INTO policies (
    id, service_id, name, dimension, description,
    is_active, version, created_by, deleted_at, created_at, updated_at
) VALUES (
    'bbbbbbbb-0000-4000-8000-000000000002',
    'aaaaaaaa-0000-4000-8000-000000000001',
    'Test Coverage Requirements',
    'test_coverage',
    'Requires minimum coverage thresholds for unit, integration, and branch coverage.',
    TRUE, 1, '22222222-0000-4000-8000-000000000002',
    NULL, NOW(), NOW()
);

-- security policy
INSERT INTO policies (
    id, service_id, name, dimension, description,
    is_active, version, created_by, deleted_at, created_at, updated_at
) VALUES (
    'bbbbbbbb-0000-4000-8000-000000000003',
    'aaaaaaaa-0000-4000-8000-000000000001',
    'Security Compliance Policy',
    'security',
    'Enforces SAST, SCA, secrets detection, and vulnerability thresholds.',
    TRUE, 1, '22222222-0000-4000-8000-000000000002',
    NULL, NOW(), NOW()
);

-- documentation policy
INSERT INTO policies (
    id, service_id, name, dimension, description,
    is_active, version, created_by, deleted_at, created_at, updated_at
) VALUES (
    'bbbbbbbb-0000-4000-8000-000000000004',
    'aaaaaaaa-0000-4000-8000-000000000001',
    'Documentation Standards',
    'documentation',
    'Requires API docs, architecture decision records, and README completeness.',
    TRUE, 1, '22222222-0000-4000-8000-000000000002',
    NULL, NOW(), NOW()
);

-- operations_readiness policy
INSERT INTO policies (
    id, service_id, name, dimension, description,
    is_active, version, created_by, deleted_at, created_at, updated_at
) VALUES (
    'bbbbbbbb-0000-4000-8000-000000000005',
    'aaaaaaaa-0000-4000-8000-000000000001',
    'Operations Readiness Checklist',
    'operations_readiness',
    'Verifies runbook, alerting, on-call rotation, and deployment automation.',
    TRUE, 1, '22222222-0000-4000-8000-000000000002',
    NULL, NOW(), NOW()
);


-- ─────────────────────────────────────────────────────────────────────────────
-- Policy Rules — 3 rules per policy = 15 rules total
-- Covers all severity levels: critical, high, medium, low
-- Demonstrates diverse JSONB threshold_config shapes
-- ─────────────────────────────────────────────────────────────────────────────

-- ── code_quality rules ────────────────────────────────────────────────────

INSERT INTO policy_rules (
    id, policy_id, name, rule_type,
    threshold_config, severity, weight, is_active,
    deleted_at, created_at, updated_at
) VALUES (
    'cccccccc-0000-4000-8000-000000000001',
    'bbbbbbbb-0000-4000-8000-000000000001',
    'Cyclomatic Complexity Limit',
    'complexity_threshold',
    '{"operator": "lte", "value": 10, "unit": "complexity_score", "per_function": true}',
    'high', 2.0, TRUE, NULL, NOW(), NOW()
);

INSERT INTO policy_rules (
    id, policy_id, name, rule_type,
    threshold_config, severity, weight, is_active,
    deleted_at, created_at, updated_at
) VALUES (
    'cccccccc-0000-4000-8000-000000000002',
    'bbbbbbbb-0000-4000-8000-000000000001',
    'No Critical Linting Violations',
    'lint_check',
    '{"operator": "eq", "value": 0, "unit": "violations", "severity_filter": ["error"], "tool": "ruff"}',
    'critical', 3.0, TRUE, NULL, NOW(), NOW()
);

INSERT INTO policy_rules (
    id, policy_id, name, rule_type,
    threshold_config, severity, weight, is_active,
    deleted_at, created_at, updated_at
) VALUES (
    'cccccccc-0000-4000-8000-000000000003',
    'bbbbbbbb-0000-4000-8000-000000000001',
    'Maximum Function Length',
    'size_threshold',
    '{"operator": "lte", "value": 50, "unit": "lines", "per_function": true, "exclude_tests": true}',
    'medium', 1.0, TRUE, NULL, NOW(), NOW()
);

-- ── test_coverage rules ───────────────────────────────────────────────────

INSERT INTO policy_rules (
    id, policy_id, name, rule_type,
    threshold_config, severity, weight, is_active,
    deleted_at, created_at, updated_at
) VALUES (
    'cccccccc-0000-4000-8000-000000000004',
    'bbbbbbbb-0000-4000-8000-000000000002',
    'Minimum Line Coverage',
    'coverage_threshold',
    '{"operator": "gte", "value": 80, "unit": "percent", "scope": "lines", "report_path": "backend/coverage.xml"}',
    'critical', 3.0, TRUE, NULL, NOW(), NOW()
);

INSERT INTO policy_rules (
    id, policy_id, name, rule_type,
    threshold_config, severity, weight, is_active,
    deleted_at, created_at, updated_at
) VALUES (
    'cccccccc-0000-4000-8000-000000000005',
    'bbbbbbbb-0000-4000-8000-000000000002',
    'Minimum Branch Coverage',
    'coverage_threshold',
    '{"operator": "gte", "value": 70, "unit": "percent", "scope": "branches", "report_path": "backend/coverage.xml"}',
    'high', 2.0, TRUE, NULL, NOW(), NOW()
);

INSERT INTO policy_rules (
    id, policy_id, name, rule_type,
    threshold_config, severity, weight, is_active,
    deleted_at, created_at, updated_at
) VALUES (
    'cccccccc-0000-4000-8000-000000000006',
    'bbbbbbbb-0000-4000-8000-000000000002',
    'New Code Coverage Gate',
    'coverage_threshold',
    '{"operator": "gte", "value": 90, "unit": "percent", "scope": "new_code", "sonarqube": {"quality_gate": true}}',
    'high', 2.5, TRUE, NULL, NOW(), NOW()
);

-- ── security rules ────────────────────────────────────────────────────────

INSERT INTO policy_rules (
    id, policy_id, name, rule_type,
    threshold_config, severity, weight, is_active,
    deleted_at, created_at, updated_at
) VALUES (
    'cccccccc-0000-4000-8000-000000000007',
    'bbbbbbbb-0000-4000-8000-000000000003',
    'No High Severity SAST Findings',
    'sast_threshold',
    '{"operator": "eq", "value": 0, "unit": "findings", "severity_filter": ["critical", "high"], "tool": "semgrep"}',
    'critical', 4.0, TRUE, NULL, NOW(), NOW()
);

INSERT INTO policy_rules (
    id, policy_id, name, rule_type,
    threshold_config, severity, weight, is_active,
    deleted_at, created_at, updated_at
) VALUES (
    'cccccccc-0000-4000-8000-000000000008',
    'bbbbbbbb-0000-4000-8000-000000000003',
    'No High Severity Dependencies',
    'sca_threshold',
    '{"operator": "eq", "value": 0, "unit": "vulnerabilities", "severity_filter": ["critical", "high"], "tool": "snyk", "grace_period_days": 7}',
    'critical', 4.0, TRUE, NULL, NOW(), NOW()
);

INSERT INTO policy_rules (
    id, policy_id, name, rule_type,
    threshold_config, severity, weight, is_active,
    deleted_at, created_at, updated_at
) VALUES (
    'cccccccc-0000-4000-8000-000000000009',
    'bbbbbbbb-0000-4000-8000-000000000003',
    'No Secrets in Codebase',
    'secret_scan',
    '{"operator": "eq", "value": 0, "unit": "findings", "tool": "gitleaks", "config": ".gitleaks.toml"}',
    'critical', 5.0, TRUE, NULL, NOW(), NOW()
);

-- ── documentation rules ───────────────────────────────────────────────────

INSERT INTO policy_rules (
    id, policy_id, name, rule_type,
    threshold_config, severity, weight, is_active,
    deleted_at, created_at, updated_at
) VALUES (
    'cccccccc-0000-4000-8000-000000000010',
    'bbbbbbbb-0000-4000-8000-000000000004',
    'OpenAPI Spec Completeness',
    'docs_completeness',
    '{"operator": "gte", "value": 100, "unit": "percent", "scope": "endpoints", "require_examples": true}',
    'medium', 1.5, TRUE, NULL, NOW(), NOW()
);

INSERT INTO policy_rules (
    id, policy_id, name, rule_type,
    threshold_config, severity, weight, is_active,
    deleted_at, created_at, updated_at
) VALUES (
    'cccccccc-0000-4000-8000-000000000011',
    'bbbbbbbb-0000-4000-8000-000000000004',
    'Architecture Decision Records Present',
    'adr_check',
    '{"operator": "boolean", "value": true, "path": "docs/adr/", "minimum_count": 1}',
    'low', 1.0, TRUE, NULL, NOW(), NOW()
);

INSERT INTO policy_rules (
    id, policy_id, name, rule_type,
    threshold_config, severity, weight, is_active,
    deleted_at, created_at, updated_at
) VALUES (
    'cccccccc-0000-4000-8000-000000000012',
    'bbbbbbbb-0000-4000-8000-000000000004',
    'README Completeness',
    'docs_completeness',
    '{"operator": "boolean", "value": true, "required_sections": ["installation", "usage", "contributing", "license"]}',
    'low', 0.5, TRUE, NULL, NOW(), NOW()
);

-- ── operations_readiness rules ────────────────────────────────────────────

INSERT INTO policy_rules (
    id, policy_id, name, rule_type,
    threshold_config, severity, weight, is_active,
    deleted_at, created_at, updated_at
) VALUES (
    'cccccccc-0000-4000-8000-000000000013',
    'bbbbbbbb-0000-4000-8000-000000000005',
    'Runbook Present and Linked',
    'runbook_check',
    '{"operator": "boolean", "value": true, "require_link": true, "allowed_platforms": ["confluence", "notion", "github_wiki"]}',
    'high', 2.0, TRUE, NULL, NOW(), NOW()
);

INSERT INTO policy_rules (
    id, policy_id, name, rule_type,
    threshold_config, severity, weight, is_active,
    deleted_at, created_at, updated_at
) VALUES (
    'cccccccc-0000-4000-8000-000000000014',
    'bbbbbbbb-0000-4000-8000-000000000005',
    'Alerting Configured',
    'alerting_check',
    '{"operator": "boolean", "value": true, "require_oncall": true, "platforms": ["pagerduty", "opsgenie"], "minimum_alerts": 3}',
    'critical', 3.0, TRUE, NULL, NOW(), NOW()
);

INSERT INTO policy_rules (
    id, policy_id, name, rule_type,
    threshold_config, severity, weight, is_active,
    deleted_at, created_at, updated_at
) VALUES (
    'cccccccc-0000-4000-8000-000000000015',
    'bbbbbbbb-0000-4000-8000-000000000005',
    'Automated Deployment Pipeline',
    'pipeline_check',
    '{"operator": "boolean", "value": true, "require_smoke_test": true, "require_rollback": true, "stages": ["dev", "staging", "prod"]}',
    'high', 2.5, TRUE, NULL, NOW(), NOW()
);

COMMIT;
