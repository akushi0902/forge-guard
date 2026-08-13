import { http, HttpResponse } from 'msw';

import {
  FindingSeverity,
  FindingStatus,
  type Finding,
  type PaginatedResponse,
  type RemediationRecommendation,
} from '@/types/api';

export const FINDING_FIXTURE: Finding = {
  id: 'fnd-001',
  service_id: 'svc-001',
  title: 'SQL injection vulnerability in query builder',
  description: 'Unsanitised user input passed directly to SQL query.',
  severity: FindingSeverity.Critical,
  dimension: 'security',
  status: FindingStatus.Open,
  created_at: '2026-08-10T14:00:00Z',
};

export const FINDING_LIST_FIXTURE: PaginatedResponse<Finding> = {
  items: [FINDING_FIXTURE],
  cursor: null,
  total_count: 1,
};

export const RECOMMENDATION_FIXTURE: RemediationRecommendation = {
  id: 'rec-001',
  finding_id: 'fnd-001',
  recommendation_text: 'Use parameterised queries to prevent SQL injection.',
  implementation_guide:
    '1. Replace raw SQL with ORM queries.\n2. Use prepared statements.\n3. Add input validation.',
  confidence_score: 0.95,
};

export const findingHandlers = [
  http.get('/api/v1/services/:serviceId/findings', () =>
    HttpResponse.json(FINDING_LIST_FIXTURE),
  ),
  http.get('/api/v1/findings/:findingId/recommendation', () =>
    HttpResponse.json(RECOMMENDATION_FIXTURE),
  ),
  http.post('/api/v1/findings/:findingId/exception', () =>
    HttpResponse.json(
      {
        id: 'exc-001',
        finding_id: 'fnd-001',
        justification: 'Accepted risk pending fix in next sprint.',
        status: 'pending',
        expires_at: null,
      },
      { status: 201 },
    ),
  ),
];
