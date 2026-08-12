import { http, HttpResponse } from 'msw';

import {
  SERVICES_WITH_METRICS_RESPONSE,
  ASSESSMENT_TRENDS_RESPONSE,
} from '@/test/fixtures/managerDashboardData';

export const managerHandlers = [
  http.get('/api/v1/services/with-metrics', () =>
    HttpResponse.json(SERVICES_WITH_METRICS_RESPONSE),
  ),
  http.get('/api/v1/assessments/trends', () =>
    HttpResponse.json(ASSESSMENT_TRENDS_RESPONSE),
  ),
];
