/**
 * Release assessment test fixtures for component and integration tests (WO-075).
 *
 * Provides:
 *   - Pending assessment (completed, awaiting decision)
 *   - Completed assessment with APPROVE decision
 *   - Completed assessment with BLOCK decision
 *   - Escalated assessment (requires Security Reviewer)
 */

import { type CombinedDecisionView, type ReleaseAssessmentFinding } from '@/types/api';

// ---------------------------------------------------------------------------
// Shared finding fixtures
// ---------------------------------------------------------------------------

export const CRITICAL_RELEASE_FINDING: ReleaseAssessmentFinding = {
  id: 'fnd-crit-r-001',
  title: 'Hardcoded API credentials detected',
  severity: 'critical',
  dimension: 'security',
  explanation: 'An AWS secret access key was found embedded in the application source code at src/config/aws.ts line 42.',
  business_impact: 'Full compromise of AWS resources if the repository is public or the key is leaked.',
  remediation_steps: [
    'Remove the hardcoded key from source code immediately.',
    'Rotate the AWS key via IAM console.',
    'Store secrets in environment variables or a secrets manager.',
  ],
  confidence_score: 0.99,
  source: 'security_scanner',
};

export const HIGH_RELEASE_FINDING: ReleaseAssessmentFinding = {
  id: 'fnd-high-r-001',
  title: 'Test coverage below 80% threshold',
  severity: 'high',
  dimension: 'test_coverage',
  explanation: 'Current test coverage is 62%. The policy requires a minimum of 80% coverage.',
  business_impact: 'Undetected regressions are more likely, increasing production incident risk.',
  remediation_steps: [
    'Add unit tests for the payment processing module.',
    'Configure CI to fail builds below the 80% threshold.',
  ],
  confidence_score: 0.92,
  source: 'policy_guardian',
};

export const MEDIUM_RELEASE_FINDING: ReleaseAssessmentFinding = {
  id: 'fnd-med-r-001',
  title: 'Outdated dependency: lodash@4.17.20',
  severity: 'medium',
  dimension: 'security',
  explanation: 'lodash@4.17.20 has a known prototype pollution vulnerability (CVE-2021-23337).',
  business_impact: 'Potential denial-of-service or property injection attacks.',
  remediation_steps: ['Upgrade lodash to >=4.17.21'],
  confidence_score: 0.88,
  source: 'dependency_scanner',
};

export const LOW_RELEASE_FINDING: ReleaseAssessmentFinding = {
  id: 'fnd-low-r-001',
  title: 'Missing OpenAPI documentation for 3 endpoints',
  severity: 'low',
  dimension: 'documentation',
  explanation: 'POST /refunds, DELETE /cards, and GET /limits are missing from the OpenAPI spec.',
  business_impact: 'Developers integrating with the API may make incorrect assumptions.',
  remediation_steps: ['Add OpenAPI annotations for all missing endpoints.'],
  confidence_score: 0.85,
  source: 'policy_guardian',
};

// ---------------------------------------------------------------------------
// Combined decision view fixtures
// ---------------------------------------------------------------------------

/** Assessment completed, no decision submitted yet. */
export const PENDING_DECISION_VIEW: CombinedDecisionView = {
  assessment: {
    id: 'rel-001',
    service_id: 'svc-001',
    commit_sha: 'abc123def456abc123def456abc123def456abc1',
    pr_reference: 'https://github.com/acme/payment-api/pull/42',
    status: 'completed',
    created_at: '2026-08-11T10:00:00Z',
    completed_at: '2026-08-11T10:05:00Z',
  },
  system_recommendation: { decision: 'CONDITIONAL_APPROVE' },
  health_score: { overall: 78, dimensions: [] },
  risk_score: { overall: 42, contributing_factors: [] },
  findings_summary: {
    total: 3,
    by_severity: {
      high:   { count: 1, items: [HIGH_RELEASE_FINDING] },
      medium: { count: 1, items: [MEDIUM_RELEASE_FINDING] },
      low:    { count: 1, items: [LOW_RELEASE_FINDING] },
    },
  },
  escalation: { is_escalated: false, reasons: null },
  decision_record: null,
  scoring_incomplete: false,
  scoring_incomplete_reason: null,
};

/** Assessment completed with an APPROVE decision. */
export const APPROVED_DECISION_VIEW: CombinedDecisionView = {
  ...PENDING_DECISION_VIEW,
  decision_record: {
    id: 'dec-001',
    decided_by: 'usr-tech-lead-001',
    decided_by_role: 'tech_lead',
    decision: 'APPROVE',
    rationale: 'All blocking issues have been resolved. Low-risk refactor. Approving for release.',
    comment: 'Monitoring for the next 24 hours.',
    was_escalated: false,
    created_at: '2026-08-11T11:00:00Z',
  },
};

/** Assessment completed with a BLOCK decision. */
export const BLOCKED_DECISION_VIEW: CombinedDecisionView = {
  ...PENDING_DECISION_VIEW,
  decision_record: {
    id: 'dec-002',
    decided_by: 'usr-tech-lead-001',
    decided_by_role: 'tech_lead',
    decision: 'BLOCK',
    rationale: 'High test coverage gap poses unacceptable risk. Must resolve before releasing.',
    comment: null,
    was_escalated: false,
    created_at: '2026-08-11T11:00:00Z',
  },
};

/** Escalated assessment (critical security finding, requires Security Reviewer). */
export const ESCALATED_DECISION_VIEW: CombinedDecisionView = {
  assessment: {
    id: 'rel-escalated',
    service_id: 'svc-001',
    commit_sha: 'dead0000cafe0000dead0000cafe0000dead0001',
    pr_reference: null,
    status: 'completed',
    created_at: '2026-08-12T09:00:00Z',
    completed_at: '2026-08-12T09:08:00Z',
  },
  system_recommendation: { decision: 'BLOCK' },
  health_score: { overall: 55, dimensions: [] },
  risk_score: { overall: 88, contributing_factors: [] },
  findings_summary: {
    total: 1,
    by_severity: {
      critical: { count: 1, items: [CRITICAL_RELEASE_FINDING] },
    },
  },
  escalation: {
    is_escalated: true,
    reasons: [{ finding_id: CRITICAL_RELEASE_FINDING.id, title: CRITICAL_RELEASE_FINDING.title }],
  },
  decision_record: null,
  scoring_incomplete: false,
  scoring_incomplete_reason: null,
};

/** Assessment still processing (pending status). */
export const PROCESSING_DECISION_VIEW: CombinedDecisionView = {
  assessment: {
    id: 'rel-pending',
    service_id: 'svc-001',
    commit_sha: 'a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2',
    pr_reference: null,
    status: 'pending',
    created_at: '2026-08-12T08:00:00Z',
    completed_at: null,
  },
  system_recommendation: { decision: 'PENDING' },
  health_score: null,
  risk_score: null,
  findings_summary: { total: 0, by_severity: {} },
  escalation: { is_escalated: false, reasons: null },
  decision_record: null,
  scoring_incomplete: true,
  scoring_incomplete_reason: 'Assessment pipeline has not completed yet.',
};
