import { http, HttpResponse } from 'msw';

import { type PaginatedResponse, type Service } from '@/types/api';

export const SERVICE_FIXTURE: Service = {
  id: 'svc-001',
  name: 'payment-service',
  description: 'Handles payment processing',
  repository_url: 'https://github.com/org/payment-service',
  health_score: 82,
  last_evaluated_at: '2026-08-11T10:00:00Z',
};

export const SERVICE_LIST_FIXTURE: PaginatedResponse<Service> = {
  items: [
    SERVICE_FIXTURE,
    {
      id: 'svc-002',
      name: 'auth-service',
      description: 'User authentication and authorisation',
      repository_url: 'https://github.com/org/auth-service',
      health_score: 91,
      last_evaluated_at: '2026-08-11T09:30:00Z',
    },
  ],
  cursor: null,
  total_count: 2,
};

export const serviceHandlers = [
  http.get('/api/v1/services', () => HttpResponse.json(SERVICE_LIST_FIXTURE)),
  http.get('/api/v1/services/:id', ({ params }) => {
    if (params['id'] === SERVICE_FIXTURE.id) {
      return HttpResponse.json(SERVICE_FIXTURE);
    }
    return HttpResponse.json(
      { detail: 'Service not found', status_code: 404, error_code: 'NOT_FOUND' },
      { status: 404 },
    );
  }),
];
