import { http, HttpResponse } from 'msw';

import { type ServiceScore } from '@/types/api';

export const SCORE_FIXTURE: ServiceScore = {
  overall_score: 82,
  dimensions: [
    { name: 'code_quality', score: 85, weight: 0.25, rule_count: 10, pass_count: 9 },
    { name: 'test_coverage', score: 78, weight: 0.25, rule_count: 8, pass_count: 6 },
    { name: 'security', score: 90, weight: 0.30, rule_count: 12, pass_count: 11 },
    { name: 'documentation', score: 75, weight: 0.10, rule_count: 6, pass_count: 5 },
    { name: 'operations_readiness', score: 80, weight: 0.10, rule_count: 5, pass_count: 4 },
  ],
};

export const scoreHandlers = [
  http.get('/api/v1/services/:serviceId/scores', () =>
    HttpResponse.json(SCORE_FIXTURE),
  ),
];
