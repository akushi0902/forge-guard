/**
 * Test fixtures for RemediationDetail page tests (WO-082).
 *
 * Covers varied:
 *   - Finding severities (critical, high, medium, low)
 *   - Confidence levels (high ≥80%, medium 50-79%, low <50%, zero)
 *   - Remediation step counts (1, 3, 10+)
 *   - Before/after score comparisons (improved, worsened, unchanged)
 *   - Finding statuses (open, in_progress, resolved)
 */

import {
  FindingSeverity,
  FindingStatus,
  type FindingDetail,
  type FindingRecommendation,
  type ReEvaluationResult,
} from '@/types/api';

// ---------------------------------------------------------------------------
// Finding fixtures
// ---------------------------------------------------------------------------

/** Critical open finding — security dimension. */
export const CRITICAL_FINDING_DETAIL: FindingDetail = {
  id: 'fnd-detail-001',
  service_id: 'svc-001',
  title: 'Hardcoded credentials detected in payment module',
  description: 'AWS access key ID and secret found in src/payments/client.ts. Keys are valid and must be rotated immediately.',
  severity: FindingSeverity.Critical,
  dimension: 'security',
  status: FindingStatus.Open,
  created_at: '2026-08-10T08:00:00Z',
  ai_explanation:
    'Hardcoded secrets expose the application to credential theft if the repository is compromised. ' +
    'Attackers with repository access can immediately use these keys to access AWS resources, ' +
    'leading to data exfiltration, financial loss, and compliance violations.',
  evidence: 'src/payments/client.ts:42: AKIAIOSFODNN7EXAMPLE',
  escalation_required: true,
  resolved_at: null,
};

/** High severity open finding — test coverage dimension. */
export const HIGH_FINDING_DETAIL: FindingDetail = {
  id: 'fnd-detail-002',
  service_id: 'svc-001',
  title: 'Test coverage below 80% threshold',
  description: 'Current test coverage is 67%. Minimum required is 80% per engineering policy.',
  severity: FindingSeverity.High,
  dimension: 'test_coverage',
  status: FindingStatus.Open,
  created_at: '2026-08-10T09:00:00Z',
  ai_explanation:
    'Low test coverage increases the risk of undetected regressions reaching production. ' +
    'The payment module has only 52% coverage, which is the main contributor to the overall deficit.',
  evidence: 'coverage/lcov.info: 67% statements',
  escalation_required: false,
  resolved_at: null,
};

/** Medium severity in-progress finding — dependency dimension. */
export const MEDIUM_FINDING_DETAIL: FindingDetail = {
  id: 'fnd-detail-003',
  service_id: 'svc-001',
  title: 'Outdated dependency with known vulnerability',
  description: 'lodash@4.17.20 has CVE-2021-23337 (prototype pollution, CVSS 7.2).',
  severity: FindingSeverity.Medium,
  dimension: 'security',
  status: FindingStatus.InProgress,
  created_at: '2026-08-09T10:00:00Z',
  ai_explanation:
    'The lodash prototype pollution vulnerability can allow attackers to modify Object.prototype, ' +
    'potentially enabling privilege escalation or denial-of-service attacks.',
  evidence: 'package-lock.json: lodash@4.17.20',
  escalation_required: false,
  resolved_at: null,
};

/** Resolved finding — should hide action buttons. */
export const RESOLVED_FINDING_DETAIL: FindingDetail = {
  id: 'fnd-detail-004',
  service_id: 'svc-001',
  title: 'Missing API documentation',
  description: 'OpenAPI spec missing for 3 endpoints.',
  severity: FindingSeverity.Low,
  dimension: 'documentation',
  status: FindingStatus.Resolved,
  created_at: '2026-08-08T11:00:00Z',
  ai_explanation:
    'Missing API documentation makes it harder for consumers to integrate correctly, ' +
    'increasing support burden and integration errors.',
  evidence: 'openapi.yaml: endpoints POST /refunds, DELETE /cards not documented',
  escalation_required: false,
  resolved_at: '2026-08-12T14:30:00Z',
};

// ---------------------------------------------------------------------------
// Recommendation fixtures — varied confidence levels
// ---------------------------------------------------------------------------

/** High-confidence recommendation (≥80%) — renders green ring. */
export const HIGH_CONFIDENCE_DETAIL_RECOMMENDATION: FindingRecommendation = {
  id: 'rec-detail-001',
  finding_id: 'fnd-detail-001',
  recommendation_text:
    'Remove all hardcoded secrets from source code and migrate them to a dedicated secrets manager.',
  implementation_guide:
    '1. Identify all secrets using `git grep -i "AKIA\\|secret\\|password"`.\n' +
    '2. Rotate the exposed AWS keys immediately via the IAM console.\n' +
    '3. Store the new keys in AWS Secrets Manager.\n' +
    '4. Update the application to fetch secrets at runtime:\n' +
    '```typescript\nimport { SecretsManager } from "@aws-sdk/client-secrets-manager";\nconst secret = await client.getSecretValue({ SecretId: "payment/aws-keys" });\n```\n' +
    '5. Add a pre-commit hook to prevent future leaks:\n' +
    '```bash\nnpx detect-secrets scan > .secrets.baseline\ngit add .secrets.baseline\n```\n' +
    '6. Add `.env*` to `.gitignore` and audit the git history.',
  confidence_score: 0.92,
  business_impact:
    'Exposed AWS credentials could enable an attacker to access S3 buckets containing PII, ' +
    'incur significant cloud costs, and trigger regulatory penalties under GDPR and PCI-DSS.',
  source: 'ai_generated',
  created_at: '2026-08-10T08:05:00Z',
};

/** Medium-confidence recommendation (50-79%) — renders amber ring. */
export const MEDIUM_CONFIDENCE_DETAIL_RECOMMENDATION: FindingRecommendation = {
  id: 'rec-detail-002',
  finding_id: 'fnd-detail-002',
  recommendation_text:
    'Increase test coverage to at least 80% by adding unit tests for the payment and authentication modules.',
  implementation_guide:
    '1. Run `npm run coverage` to identify files with the lowest coverage.\n' +
    '2. Add unit tests for the payment calculation functions:\n' +
    '```typescript\ndescribe("calculateFee", () => {\n  it("returns 2.9% for Visa cards", () => {\n    expect(calculateFee("visa", 100)).toBe(2.90);\n  });\n});\n```\n' +
    '3. Add integration tests for the API endpoints.\n' +
    '4. Configure CI to fail below 80%:\n' +
    '```yaml\ncoverage:\n  threshold:\n    global:\n      statements: 80\n```',
  confidence_score: 0.65,
  business_impact:
    'Low test coverage increases the risk of regressions reaching production. ' +
    'Payment processing failures can result in lost revenue and customer trust damage.',
  source: 'ai_generated',
  created_at: '2026-08-10T09:05:00Z',
};

/** Low-confidence recommendation (<50%) — renders red ring + warning banner. */
export const LOW_CONFIDENCE_DETAIL_RECOMMENDATION: FindingRecommendation = {
  id: 'rec-detail-003',
  finding_id: 'fnd-detail-003',
  recommendation_text:
    'Consider upgrading lodash to address the prototype pollution vulnerability. ' +
    'Verify that lodash is actually used directly in production code before upgrading.',
  implementation_guide:
    '1. Check if lodash is a direct or transitive dependency:\n' +
    '```bash\nnpm ls lodash\n```\n' +
    '2. Upgrade if it is a direct dependency:\n' +
    '```bash\nnpm install lodash@latest\n```\n' +
    '3. Run the test suite to verify compatibility.',
  confidence_score: 0.35,
  business_impact:
    'Prototype pollution may be exploitable depending on how lodash functions are called ' +
    'with user-controlled input.',
  source: 'template_fallback',
  created_at: '2026-08-09T10:05:00Z',
};

/** Zero-confidence recommendation — edge case, strong warning. */
export const ZERO_CONFIDENCE_DETAIL_RECOMMENDATION: FindingRecommendation = {
  id: 'rec-detail-004',
  finding_id: 'fnd-detail-004',
  recommendation_text:
    'Add OpenAPI documentation for all undocumented endpoints.',
  implementation_guide:
    '1. Identify undocumented endpoints.\n2. Add OpenAPI annotations.',
  confidence_score: 0,
  business_impact: null,
  source: 'template_fallback',
  created_at: '2026-08-08T11:05:00Z',
};

/** Recommendation with 10+ steps — tests table-of-contents rendering. */
export const MANY_STEPS_RECOMMENDATION: FindingRecommendation = {
  id: 'rec-detail-005',
  finding_id: 'fnd-detail-001',
  recommendation_text: 'Comprehensive security hardening with many steps.',
  implementation_guide:
    '1. Rotate all exposed credentials.\n' +
    '2. Audit the git history for secrets.\n' +
    '3. Set up a secrets manager.\n' +
    '4. Update the application configuration.\n' +
    '5. Add a pre-commit hook.\n' +
    '6. Update the CI pipeline.\n' +
    '7. Notify the security team.\n' +
    '8. Document the incident.\n' +
    '9. Schedule a post-mortem.\n' +
    '10. Update runbooks.\n' +
    '11. Review similar codebases for the same issue.',
  confidence_score: 0.78,
  business_impact: 'Significant security risk requiring immediate remediation.',
  source: 'ai_generated',
  created_at: '2026-08-10T08:05:00Z',
};

// ---------------------------------------------------------------------------
// Re-evaluation result fixtures
// ---------------------------------------------------------------------------

/** Score improved after remediation. */
export const IMPROVED_REEVALUATION: ReEvaluationResult = {
  finding_id: 'fnd-detail-001',
  before_health_score: 62,
  after_health_score: 78,
  score_delta: 16,
  before_finding_status: FindingStatus.Open,
  after_finding_status: FindingStatus.Resolved,
  rule_results: [
    {
      rule_id: 'rule-sec-001',
      rule_name: 'No hardcoded secrets',
      passed: true,
      actual_value: '0 secrets found',
      threshold: '0',
    },
  ],
  updated_guidance: null,
  re_evaluated_at: '2026-08-12T15:00:00Z',
};

/** Score worsened after remediation attempt. */
export const WORSENED_REEVALUATION: ReEvaluationResult = {
  finding_id: 'fnd-detail-002',
  before_health_score: 72,
  after_health_score: 68,
  score_delta: -4,
  before_finding_status: FindingStatus.Open,
  after_finding_status: FindingStatus.Open,
  rule_results: [
    {
      rule_id: 'rule-cov-001',
      rule_name: 'Test coverage ≥ 80%',
      passed: false,
      actual_value: '64%',
      threshold: '80%',
    },
  ],
  updated_guidance: 'Coverage has decreased further. Review recent commits.',
  re_evaluated_at: '2026-08-12T16:00:00Z',
};

/** Score unchanged after remediation attempt. */
export const UNCHANGED_REEVALUATION: ReEvaluationResult = {
  finding_id: 'fnd-detail-003',
  before_health_score: 75,
  after_health_score: 75,
  score_delta: 0,
  before_finding_status: FindingStatus.InProgress,
  after_finding_status: FindingStatus.InProgress,
  rule_results: [
    {
      rule_id: 'rule-dep-001',
      rule_name: 'No known CVEs in dependencies',
      passed: false,
      actual_value: '1 CVE found',
      threshold: '0',
    },
  ],
  updated_guidance: null,
  re_evaluated_at: '2026-08-12T17:00:00Z',
};
