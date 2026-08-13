import { http, HttpResponse } from 'msw';

import { DecisionType, type CombinedDecisionView, type ReleaseAssessment, type ReleaseDecision } from '@/types/api';

export const RELEASE_FIXTURE: ReleaseAssessment = {
  id: 'rel-001',
  service_id: 'svc-001',
  commit_sha: 'abc123def456',
  pr_reference: 'https://github.com/org/payment-service/pull/42',
  status: 'completed',
  risk_score: 25,
  change_analysis: 'Low-risk refactor with no new dependencies.',
  created_at: '2026-08-11T10:00:00Z',
  completed_at: '2026-08-11T10:05:00Z',
};

/** Pending fixture returned by POST /api/v1/releases/assess. */
export const PENDING_RELEASE_FIXTURE: ReleaseAssessment = {
  id: 'rel-pending',
  service_id: 'svc-001',
  commit_sha: 'a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2',
  pr_reference: null,
  status: 'pending',
  risk_score: null,
  change_analysis: null,
  created_at: '2026-08-12T08:00:00Z',
  completed_at: null,
};

export const DECISION_FIXTURE: ReleaseDecision = {
  id: 'dec-001',
  release_assessment_id: 'rel-001',
  health_score_at_decision: 82,
  risk_score_at_decision: 25,
  decision: DecisionType.Approve,
  decided_by_role: 'tech_lead',
  rationale: 'All critical checks pass.',
  comment: null,
  was_escalated: false,
};

/** Combined decision view for the completed (undecided) release fixture. */
export const DECISION_VIEW_PENDING: CombinedDecisionView = {
  assessment: {
    id: RELEASE_FIXTURE.id,
    service_id: RELEASE_FIXTURE.service_id,
    commit_sha: RELEASE_FIXTURE.commit_sha,
    pr_reference: RELEASE_FIXTURE.pr_reference,
    status: 'completed',
    created_at: RELEASE_FIXTURE.created_at,
    completed_at: RELEASE_FIXTURE.completed_at,
  },
  system_recommendation: { decision: 'APPROVE' },
  health_score: { overall: 82, dimensions: [] },
  risk_score: { overall: 25, contributing_factors: [] },
  findings_summary: {
    total: 2,
    by_severity: {
      high: {
        count: 1,
        items: [
          {
            id: 'fnd-h-001',
            title: 'Test coverage below threshold',
            severity: 'high',
            dimension: 'test_coverage',
            explanation: 'Current coverage is 67%, below the 80% minimum.',
            business_impact: 'Increases risk of undetected regressions.',
            remediation_steps: ['Add unit tests for payment module', 'Set coverage gate to 80%'],
            confidence_score: 0.92,
            source: 'policy_guardian',
          },
        ],
      },
      low: {
        count: 1,
        items: [
          {
            id: 'fnd-l-001',
            title: 'Missing API docs for 2 endpoints',
            severity: 'low',
            dimension: 'documentation',
            explanation: 'OpenAPI spec missing for POST /refunds.',
            business_impact: 'Developers may misuse the API.',
            remediation_steps: ['Add OpenAPI annotations'],
            confidence_score: 0.85,
            source: 'policy_guardian',
          },
        ],
      },
    },
  },
  escalation: { is_escalated: false, reasons: null },
  decision_record: null,
  scoring_incomplete: false,
  scoring_incomplete_reason: null,
};

/** Combined decision view for a decided (approved) release. */
export const DECISION_VIEW_APPROVED: CombinedDecisionView = {
  ...DECISION_VIEW_PENDING,
  decision_record: {
    id: DECISION_FIXTURE.id,
    decided_by: null,
    decided_by_role: DECISION_FIXTURE.decided_by_role,
    decision: 'APPROVE',
    rationale: DECISION_FIXTURE.rationale,
    comment: null,
    was_escalated: false,
    created_at: '2026-08-11T10:10:00Z',
  },
};

/** Combined decision view for a pending release (assessment still processing). */
export const DECISION_VIEW_PROCESSING: CombinedDecisionView = {
  ...DECISION_VIEW_PENDING,
  assessment: {
    ...DECISION_VIEW_PENDING.assessment,
    id: PENDING_RELEASE_FIXTURE.id,
    commit_sha: PENDING_RELEASE_FIXTURE.commit_sha,
    status: 'pending',
    completed_at: null,
  },
  risk_score: null,
  findings_summary: { total: 0, by_severity: {} },
};

/** Combined decision view for an escalated release. */
export const DECISION_VIEW_ESCALATED: CombinedDecisionView = {
  ...DECISION_VIEW_PENDING,
  assessment: {
    ...DECISION_VIEW_PENDING.assessment,
    id: 'rel-escalated',
  },
  findings_summary: {
    total: 1,
    by_severity: {
      critical: {
        count: 1,
        items: [
          {
            id: 'fnd-c-001',
            title: 'Hardcoded AWS credentials',
            severity: 'critical',
            dimension: 'security',
            explanation: 'AWS access key found in source code.',
            business_impact: 'Full compromise of AWS account if leaked.',
            remediation_steps: ['Remove credentials', 'Rotate keys immediately'],
            confidence_score: 0.99,
            source: 'security_scanner',
          },
        ],
      },
    },
  },
  escalation: {
    is_escalated: true,
    reasons: [{ finding_id: 'fnd-c-001', title: 'Hardcoded AWS credentials' }],
  },
};

export const releaseHandlers = [
  http.get('/api/v1/releases/:id', ({ params }) => {
    const id = params['id'];
    if (id === RELEASE_FIXTURE.id) {
      return HttpResponse.json(RELEASE_FIXTURE);
    }
    if (id === PENDING_RELEASE_FIXTURE.id) {
      return HttpResponse.json(PENDING_RELEASE_FIXTURE);
    }
    return HttpResponse.json(
      { detail: 'Release not found', status_code: 404, error_code: 'NOT_FOUND' },
      { status: 404 },
    );
  }),
  http.get('/api/v1/releases/:id/decision', ({ params }) => {
    const id = params['id'];
    if (id === RELEASE_FIXTURE.id) {
      return HttpResponse.json(DECISION_VIEW_PENDING);
    }
    if (id === PENDING_RELEASE_FIXTURE.id) {
      return HttpResponse.json(DECISION_VIEW_PROCESSING);
    }
    if (id === 'rel-escalated') {
      return HttpResponse.json(DECISION_VIEW_ESCALATED);
    }
    return HttpResponse.json(
      { detail: 'Release not found', status_code: 404, error_code: 'NOT_FOUND' },
      { status: 404 },
    );
  }),
  http.post('/api/v1/releases/assess', () =>
    HttpResponse.json(PENDING_RELEASE_FIXTURE, { status: 201 }),
  ),
  http.post('/api/v1/releases/:id/decide', () =>
    HttpResponse.json(DECISION_FIXTURE, { status: 201 }),
  ),
  http.post('/api/v1/services/:serviceId/assess', () =>
    HttpResponse.json(RELEASE_FIXTURE, { status: 201 }),
  ),
];
