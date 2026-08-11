-- Remediation domain seed fixtures
--
-- Inserts remediation recommendations and exceptions for the Payment Service demo:
--   3 recommendations  (ai_generated with high confidence, template_fallback, manual)
--   3 exceptions       (requested, approved, expired statuses)
--
-- Prerequisites (must be loaded in order):
--   1. identity_fixtures.sql   — provides users (alice, bob, charlie)
--   2. governance_fixtures.sql — provides services and policy_rules
--   3. assessments_fixtures.sql — provides findings
--   4. remediation_schema migration must have run (alembic upgrade head)
--
-- Usage:
--   psql $DATABASE_URL -f backend/tests/fixtures/identity_fixtures.sql
--   psql $DATABASE_URL -f backend/tests/fixtures/governance_fixtures.sql
--   psql $DATABASE_URL -f backend/tests/fixtures/assessments_fixtures.sql
--   psql $DATABASE_URL -f backend/tests/fixtures/remediation_fixtures.sql
--
-- Fixed UUID namespaces used in this file:
--   aaaaaaaa-r... : remediation_recommendations
--   bbbbbbbb-e... : exceptions
--
-- Cross-fixture references:
--   Finding  'ffffffff-0000-4000-8000-000000000001' (critical SQL injection)
--   Finding  'ffffffff-0000-4000-8000-000000000002' (high test_coverage)
--   Finding  'ffffffff-0000-4000-8000-000000000003' (medium code_quality)
--   User     '11111111-0000-4000-8000-000000000001' (alice, developer — requester)
--   User     '22222222-0000-4000-8000-000000000002' (bob, tech_lead — reviewer)

BEGIN;

-- ─────────────────────────────────────────────────────────────────────────────
-- Remediation Recommendations
-- ─────────────────────────────────────────────────────────────────────────────

-- Recommendation 1: AI-generated fix for the SQL injection finding (high confidence)
INSERT INTO remediation_recommendations (
    id, finding_id, recommendation_text, implementation_guide,
    confidence_score, source, created_at
) VALUES (
    'aaaaaaaa-r000-4000-8000-000000000001',
    'ffffffff-0000-4000-8000-000000000001',  -- critical SQL injection finding
    'Replace the raw f-string SQL query with a parameterised query to prevent SQL injection. Use cursor.execute(query, (user_id,)) instead of cursor.execute(f"... {user_id} ...").',
    E'Step 1: Locate the vulnerable line in src/payments/query_builder.py at line 142.\n'
    E'Step 2: Replace:\n'
    E'    cursor.execute(f"SELECT * FROM transactions WHERE user_id = {user_id}")\n'
    E'Step 3: With parameterised form:\n'
    E'    cursor.execute("SELECT * FROM transactions WHERE user_id = %s", (user_id,))\n'
    E'Step 4: Add an integration test that passes a SQL injection payload (e.g., "1 OR 1=1") '
    E'and asserts it returns zero rows.\n'
    E'Step 5: Re-run bandit security scan to confirm CWE-89 finding is resolved.\n'
    E'Step 6: Request a re-evaluation to update the Security dimension score.',
    0.97,
    'ai_generated',
    NOW() - INTERVAL '1 hour 40 minutes'
);

-- Recommendation 2: Template fallback for the test coverage finding (lower confidence)
INSERT INTO remediation_recommendations (
    id, finding_id, recommendation_text, implementation_guide,
    confidence_score, source, created_at
) VALUES (
    'aaaaaaaa-r000-4000-8000-000000000002',
    'ffffffff-0000-4000-8000-000000000002',  -- high test_coverage finding
    'Increase unit test coverage for the payment module to meet the 80% threshold. Focus on the reversal, refund, and reconciliation sub-modules that are currently uncovered.',
    E'Step 1: Run pytest --cov=src/payments to identify the lowest-coverage modules.\n'
    E'Step 2: Create test_reversal.py covering: successful reversal, duplicate reversal rejection, reversal of non-existent transaction.\n'
    E'Step 3: Create test_refund.py covering: full refund, partial refund, refund after reversal.\n'
    E'Step 4: Create test_reconciliation.py covering: daily reconciliation run, mismatch detection.\n'
    E'Step 5: Run coverage again and verify overall coverage exceeds 80%.\n'
    E'Step 6: Commit tests and request re-evaluation.',
    0.72,
    'template_fallback',
    NOW() - INTERVAL '1 hour 40 minutes'
);

-- Recommendation 3: Manual recommendation for the code quality finding
INSERT INTO remediation_recommendations (
    id, finding_id, recommendation_text, implementation_guide,
    confidence_score, source, created_at
) VALUES (
    'aaaaaaaa-r000-4000-8000-000000000003',
    'ffffffff-0000-4000-8000-000000000003',  -- medium code_quality finding
    'Refactor PaymentOrchestrator.process() to reduce cyclomatic complexity from 18 to below 10. Extract the validation, provider selection, execution, and recording steps into separate private methods.',
    E'Step 1: Identify the four logical blocks in process(): input validation, payment provider selection, payment execution, transaction recording.\n'
    E'Step 2: Extract _validate_payment_request(request) method.\n'
    E'Step 3: Extract _select_payment_provider(amount, currency) method.\n'
    E'Step 4: Extract _execute_payment(provider, request) method.\n'
    E'Step 5: Extract _record_transaction(result) method.\n'
    E'Step 6: Run radon cc src/payments/orchestrator.py to verify complexity drops below 10.\n'
    E'Step 7: Ensure existing tests still pass after refactoring.',
    NULL,  -- NULL: manually authored, no AI confidence score
    'manual',
    NOW() - INTERVAL '30 minutes'
);

-- ─────────────────────────────────────────────────────────────────────────────
-- Exceptions
-- ─────────────────────────────────────────────────────────────────────────────

-- Exception 1: Requested — developer asked for a 30-day exception on test coverage
-- (status=requested, no reviewer yet)
INSERT INTO exceptions (
    id, finding_id, requested_by,
    justification, status,
    decided_by, decision_comment,
    expires_at, decided_at,
    created_at, updated_at
) VALUES (
    'bbbbbbbb-e000-4000-8000-000000000001',
    'ffffffff-0000-4000-8000-000000000002',  -- high test_coverage finding
    '11111111-0000-4000-8000-000000000001',  -- alice (developer)
    'The payment reversal and refund modules are scheduled for a complete rewrite in the next sprint (Q3 2026 roadmap item PAYM-234). Writing tests against the current implementation would be wasted effort and would need to be rewritten immediately. Requesting a 30-day exception to cover the period until the rewrite is complete and new tests are authored.',
    'requested',
    NULL,   -- no reviewer decision yet
    NULL,
    NOW() + INTERVAL '30 days',  -- expires in 30 days
    NULL,
    NOW() - INTERVAL '20 minutes',
    NOW() - INTERVAL '20 minutes'
);

-- Exception 2: Approved — tech lead approved a 14-day exception on code quality
INSERT INTO exceptions (
    id, finding_id, requested_by,
    justification, status,
    decided_by, decision_comment,
    expires_at, decided_at,
    created_at, updated_at
) VALUES (
    'bbbbbbbb-e000-4000-8000-000000000002',
    'ffffffff-0000-4000-8000-000000000003',  -- medium code_quality finding
    '11111111-0000-4000-8000-000000000001',  -- alice (developer)
    'The PaymentOrchestrator refactor is a non-trivial change that requires careful planning to avoid regressions in the payment processing flow. The current complexity is technical debt from the original implementation. Requesting a 14-day exception to allow time to plan and execute the refactor safely.',
    'approved',
    '22222222-0000-4000-8000-000000000002',  -- bob (tech_lead) approved
    'Approved for 14 days. Ensure the refactor is tracked in the sprint backlog and the re-evaluation is requested by the expiry date.',
    NOW() + INTERVAL '14 days',  -- expires in 14 days
    NOW() - INTERVAL '10 minutes',
    NOW() - INTERVAL '15 minutes',
    NOW() - INTERVAL '10 minutes'
);

-- Exception 3: Expired — a previous exception on the SQL injection finding that was
-- approved but has now expired (the finding was not resolved in time)
INSERT INTO exceptions (
    id, finding_id, requested_by,
    justification, status,
    decided_by, decision_comment,
    expires_at, decided_at,
    created_at, updated_at
) VALUES (
    'bbbbbbbb-e000-4000-8000-000000000003',
    'ffffffff-0000-4000-8000-000000000001',  -- critical SQL injection finding
    '11111111-0000-4000-8000-000000000001',  -- alice (developer)
    'Originally requested exception while the dev team investigated the full scope of the SQL injection. Believed impact was limited to internal admin tools only.',
    'expired',
    '22222222-0000-4000-8000-000000000002',  -- bob (tech_lead) originally approved
    'Approved for 7 days pending investigation. Finding must be remediated by expiry.',
    NOW() - INTERVAL '1 day',  -- already expired yesterday
    NOW() - INTERVAL '8 days',
    NOW() - INTERVAL '9 days',
    NOW() - INTERVAL '1 day'
);

COMMIT;
