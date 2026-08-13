import { http, HttpResponse } from 'msw';

import { DecisionType, type ReleaseAssessment, type ReleaseDecision } from '@/types/api';

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
