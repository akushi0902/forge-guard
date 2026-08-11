-- Assessments domain seed fixtures
--
-- Inserts a complete assessment lifecycle for the Payment Service demo:
--   1 health assessment    (completed, with scores and findings)
--   3 findings             (critical, high, medium — across dimensions)
--   1 assessment score     (overall health score with dimension breakdown)
--   1 release assessment   (completed, for commit abc123def456)
--   1 release decision     (BLOCK — escalated due to critical security finding)
--
-- Prerequisites (must be loaded in order):
--   1. identity_fixtures.sql  — provides users (alice, bob, charlie)
--   2. governance_fixtures.sql — provides services and policy_rules
--   3. assessments_schema migration must have run (alembic upgrade head)
--
-- Usage:
--   psql $DATABASE_URL -f backend/tests/fixtures/identity_fixtures.sql
--   psql $DATABASE_URL -f backend/tests/fixtures/governance_fixtures.sql
--   psql $DATABASE_URL -f backend/tests/fixtures/assessments_fixtures.sql
--
-- Fixed UUID namespaces used in this file:
--   dddddddd-... : assessments
--   eeeeeeee-... : assessment_scores
--   ffffffff-... : findings
--   11111111-1... : release_assessments
--   11111111-2... : release_decisions
--
-- Cross-fixture references:
--   Service UUID  'aaaaaaaa-0000-4000-8000-000000000001' (Payment Service)
--   User UUID     '11111111-0000-4000-8000-000000000001' (alice@example.com, developer)
--   User UUID     '22222222-0000-4000-8000-000000000002' (bob@example.com, tech_lead)
--   PolicyRule    'cccccccc-0000-4000-8000-000000000001' (security rule)
--   PolicyRule    'cccccccc-0000-4000-8000-000000000002' (test_coverage rule)
--   PolicyRule    'cccccccc-0000-4000-8000-000000000003' (code_quality rule)

BEGIN;

-- ─────────────────────────────────────────────────────────────────────────────
-- Health Assessment (completed)
-- ─────────────────────────────────────────────────────────────────────────────

INSERT INTO assessments (
    id, service_id, assessment_type, trigger_type, triggered_by,
    status, collected_data, started_at, completed_at, created_at, updated_at
) VALUES (
    'dddddddd-0000-4000-8000-000000000001',
    'aaaaaaaa-0000-4000-8000-000000000001',  -- Payment Service
    'health_check',
    'scheduled',
    NULL,  -- scheduled trigger has no triggering user
    'completed',
    '{
        "repository_url": "https://github.com/example/payment-service",
        "commit_sha": "abc123def456",
        "branch": "main",
        "test_coverage_percent": 67.5,
        "security_scan_findings": 2,
        "dependency_vulnerabilities": 1,
        "documentation_score": 72.0,
        "cyclomatic_complexity_avg": 8.3
    }',
    NOW() - INTERVAL '2 hours',
    NOW() - INTERVAL '1 hour 45 minutes',
    NOW() - INTERVAL '2 hours',
    NOW() - INTERVAL '1 hour 45 minutes'
);

-- ─────────────────────────────────────────────────────────────────────────────
-- Assessment Score (health score with full dimension breakdown)
-- ─────────────────────────────────────────────────────────────────────────────

INSERT INTO assessment_scores (
    id, assessment_id, service_id, score_type, overall_score,
    dimension_scores, contributing_factors, created_at
) VALUES (
    'eeeeeeee-0000-4000-8000-000000000001',
    'dddddddd-0000-4000-8000-000000000001',  -- the health assessment above
    'aaaaaaaa-0000-4000-8000-000000000001',  -- Payment Service
    'health',
    72.40,
    '{
        "code_quality": 85.0,
        "test_coverage": 67.5,
        "security": 58.0,
        "documentation": 72.0,
        "operations_readiness": 79.5
    }',
    '{
        "blocking_findings": 1,
        "high_severity_findings": 1,
        "medium_severity_findings": 1,
        "improvement_since_last_assessment": -3.2,
        "trend": "declining",
        "ai_summary": "Security dimension decline driven by unresolved SQL injection finding."
    }',
    NOW() - INTERVAL '1 hour 45 minutes'
);

-- ─────────────────────────────────────────────────────────────────────────────
-- Findings (3 — critical security, high test_coverage, medium code_quality)
-- ─────────────────────────────────────────────────────────────────────────────

-- Finding 1: Critical security finding (SQL injection)
INSERT INTO findings (
    id, assessment_id, service_id, policy_rule_id,
    severity, dimension, status, title, description,
    evidence, ai_explanation, confidence_score,
    resolved_at, created_at, updated_at
) VALUES (
    'ffffffff-0000-4000-8000-000000000001',
    'dddddddd-0000-4000-8000-000000000001',
    'aaaaaaaa-0000-4000-8000-000000000001',
    'cccccccc-0000-4000-8000-000000000001',  -- security policy rule
    'critical',
    'security',
    'open',
    'SQL injection vulnerability in payment query builder',
    'Unsanitised user input is passed directly to a raw SQL query in the payment processing module. This allows an attacker to manipulate database queries.',
    '{
        "file": "src/payments/query_builder.py",
        "line": 142,
        "snippet": "cursor.execute(f\"SELECT * FROM transactions WHERE user_id = {user_id}\")",
        "cwe_id": "CWE-89",
        "cvss_score": 9.8,
        "scan_tool": "bandit",
        "scan_timestamp": "2026-08-11T08:00:00Z"
    }',
    '{
        "recommendation": "Replace raw SQL with parameterised queries or ORM calls.",
        "steps": [
            "Replace cursor.execute(f-string) with cursor.execute(query, (user_id,))",
            "Add integration test verifying parameterised query rejects injection payloads",
            "Run bandit scan to confirm finding is resolved"
        ],
        "references": ["https://owasp.org/www-community/attacks/SQL_Injection"],
        "estimated_effort": "low"
    }',
    0.97,
    NULL,
    NOW() - INTERVAL '1 hour 45 minutes',
    NOW() - INTERVAL '1 hour 45 minutes'
);

-- Finding 2: High severity — test coverage below threshold
INSERT INTO findings (
    id, assessment_id, service_id, policy_rule_id,
    severity, dimension, status, title, description,
    evidence, ai_explanation, confidence_score,
    resolved_at, created_at, updated_at
) VALUES (
    'ffffffff-0000-4000-8000-000000000002',
    'dddddddd-0000-4000-8000-000000000001',
    'aaaaaaaa-0000-4000-8000-000000000001',
    'cccccccc-0000-4000-8000-000000000002',  -- test_coverage policy rule
    'high',
    'test_coverage',
    'in_progress',
    'Unit test coverage below 80% threshold',
    'Current test coverage is 67.5%, below the required 80% threshold for the payment module. Key uncovered paths include payment reversal and refund processing flows.',
    '{
        "current_coverage_percent": 67.5,
        "required_coverage_percent": 80.0,
        "gap_percent": 12.5,
        "uncovered_modules": [
            "src/payments/reversal.py",
            "src/payments/refund.py",
            "src/payments/reconciliation.py"
        ],
        "coverage_tool": "pytest-cov",
        "report_url": "https://ci.example.com/coverage/payment-service/latest"
    }',
    '{
        "recommendation": "Add unit tests for payment reversal and refund flows.",
        "priority_modules": ["reversal.py", "refund.py"],
        "test_cases_suggested": [
            "test_successful_reversal_updates_transaction_status",
            "test_reversal_fails_for_already_reversed_transaction",
            "test_refund_creates_credit_entry"
        ],
        "estimated_effort": "medium"
    }',
    0.91,
    NULL,
    NOW() - INTERVAL '1 hour 45 minutes',
    NOW() - INTERVAL '30 minutes'
);

-- Finding 3: Medium severity — high cyclomatic complexity
INSERT INTO findings (
    id, assessment_id, service_id, policy_rule_id,
    severity, dimension, status, title, description,
    evidence, ai_explanation, confidence_score,
    resolved_at, created_at, updated_at
) VALUES (
    'ffffffff-0000-4000-8000-000000000003',
    'dddddddd-0000-4000-8000-000000000001',
    'aaaaaaaa-0000-4000-8000-000000000001',
    'cccccccc-0000-4000-8000-000000000003',  -- code_quality policy rule
    'medium',
    'code_quality',
    'open',
    'Cyclomatic complexity exceeds threshold in payment orchestrator',
    'The PaymentOrchestrator.process() method has a cyclomatic complexity of 18, exceeding the configured threshold of 10. This increases maintenance risk and reduces testability.',
    '{
        "file": "src/payments/orchestrator.py",
        "method": "PaymentOrchestrator.process",
        "cyclomatic_complexity": 18,
        "threshold": 10,
        "line_count": 187,
        "analysis_tool": "radon"
    }',
    '{
        "recommendation": "Refactor PaymentOrchestrator.process() by extracting sub-steps into smaller methods.",
        "refactoring_approach": "Extract method pattern: separate validation, provider selection, execution, and recording into individual private methods.",
        "estimated_effort": "medium"
    }',
    0.85,
    NULL,
    NOW() - INTERVAL '1 hour 45 minutes',
    NOW() - INTERVAL '1 hour 45 minutes'
);

-- ─────────────────────────────────────────────────────────────────────────────
-- Release Assessment (completed, same commit)
-- ─────────────────────────────────────────────────────────────────────────────

INSERT INTO release_assessments (
    id, service_id, commit_sha, pr_reference,
    requested_by, status, change_analysis,
    created_at, completed_at, updated_at
) VALUES (
    '11111111-1000-4000-8000-000000000001',
    'aaaaaaaa-0000-4000-8000-000000000001',  -- Payment Service
    'abc123def456',
    'https://github.com/example/payment-service/pull/47',
    '11111111-0000-4000-8000-000000000001',  -- alice (developer)
    'completed',
    '{
        "risk_score": 78.5,
        "risk_level": "high",
        "changed_files_count": 23,
        "lines_added": 412,
        "lines_deleted": 87,
        "new_dependencies": [],
        "modified_critical_paths": ["src/payments/query_builder.py"],
        "test_coverage_delta": -2.5,
        "ai_risk_summary": "This release introduces changes to the payment query builder with an unresolved SQL injection finding (CRITICAL). Release is blocked pending security remediation.",
        "dimensions": {
            "change_scope": 72.0,
            "test_coverage_delta": 45.0,
            "security_impact": 15.0,
            "dependency_risk": 95.0,
            "rollback_complexity": 60.0
        }
    }',
    NOW() - INTERVAL '1 hour 30 minutes',
    NOW() - INTERVAL '1 hour',
    NOW() - INTERVAL '1 hour'
);

-- ─────────────────────────────────────────────────────────────────────────────
-- Release Decision (BLOCK — escalated for critical security finding)
-- ─────────────────────────────────────────────────────────────────────────────

INSERT INTO release_decisions (
    id, release_assessment_id,
    health_score_at_decision, risk_score_at_decision,
    decision, decided_by_role, decided_by,
    rationale, comment, was_escalated,
    created_at
    -- NO updated_at column — this table is append-only
) VALUES (
    '11111111-2000-4000-8000-000000000001',
    '11111111-1000-4000-8000-000000000001',  -- the release assessment above
    72.40,
    78.50,
    'BLOCK',
    'security_reviewer',
    '22222222-0000-4000-8000-000000000002',  -- bob (tech_lead, acting as reviewer)
    'Release blocked due to unresolved critical security finding: SQL injection vulnerability (CWE-89, CVSS 9.8) in payment query builder. This finding must be fully remediated and re-verified before release approval.',
    'Finding ffffffff-0000-4000-8000-000000000001 must be resolved. Developer should replace raw SQL with parameterised queries and provide test evidence.',
    TRUE,  -- auto-escalated due to critical security finding
    NOW() - INTERVAL '45 minutes'
);

COMMIT;
