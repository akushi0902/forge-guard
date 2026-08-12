import { http, HttpResponse } from 'msw';

import {
  PolicyDimension,
  PolicySeverity,
  type PolicyRule,
} from '@/types/api';
import {
  DIMENSION_WEIGHTS_FIXTURE,
  POLICY_RULE_FIXTURES,
  POLICY_RULES_RESPONSE_FIXTURE,
  SCORE_THRESHOLDS_FIXTURE,
} from '@/test/fixtures/policyData';

// Mutable in-memory store for CRUD simulation
let rules: PolicyRule[] = [...POLICY_RULE_FIXTURES];
let ruleIdCounter = 100;

function resetRules() {
  rules = [...POLICY_RULE_FIXTURES];
  ruleIdCounter = 100;
}

export { resetRules };

export const policyHandlers = [
  // GET /api/v1/policies — list with optional filters
  http.get('/api/v1/policies', ({ request }) => {
    const url = new URL(request.url);
    const search = url.searchParams.get('search')?.toLowerCase() ?? '';
    const dimension = url.searchParams.get('dimension') ?? '';
    const severity = url.searchParams.get('severity') ?? '';

    let filtered = rules;
    if (search) filtered = filtered.filter((r) => r.name.toLowerCase().includes(search));
    if (dimension) filtered = filtered.filter((r) => r.dimension === dimension);
    if (severity) filtered = filtered.filter((r) => r.severity === severity);

    return HttpResponse.json({
      items: filtered,
      cursor: null,
      total: filtered.length,
    });
  }),

  // POST /api/v1/policies — create rule
  http.post('/api/v1/policies', async ({ request }) => {
    const body = (await request.json()) as {
      name: string;
      dimension: PolicyDimension;
      severity: PolicySeverity;
      threshold: number;
      description?: string;
    };

    // 409 conflict: duplicate name
    if (rules.some((r) => r.name === body.name)) {
      return HttpResponse.json(
        { detail: 'A policy rule with this name already exists.', error_code: 'DUPLICATE_NAME' },
        { status: 409 },
      );
    }

    const newRule: PolicyRule = {
      id: `pol-${String(++ruleIdCounter).padStart(3, '0')}`,
      name: body.name,
      dimension: body.dimension,
      severity: body.severity,
      threshold: body.threshold,
      description: body.description ?? null,
      enabled: true,
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    };
    rules = [newRule, ...rules];
    return HttpResponse.json(newRule, { status: 201 });
  }),

  // PUT /api/v1/policies/:id — update rule
  http.put('/api/v1/policies/:id', async ({ params, request }) => {
    const { id } = params as { id: string };
    const body = (await request.json()) as Partial<PolicyRule>;
    const idx = rules.findIndex((r) => r.id === id);
    if (idx === -1) {
      return HttpResponse.json({ detail: 'Policy rule not found.' }, { status: 404 });
    }
    const updated: PolicyRule = { ...rules[idx], ...body, updated_at: new Date().toISOString() };
    rules = rules.map((r) => (r.id === id ? updated : r));
    return HttpResponse.json(updated);
  }),

  // DELETE /api/v1/policies/:id — delete rule
  http.delete('/api/v1/policies/:id', ({ params }) => {
    const { id } = params as { id: string };
    const idx = rules.findIndex((r) => r.id === id);
    if (idx === -1) {
      return HttpResponse.json({ detail: 'Policy rule not found.' }, { status: 404 });
    }
    rules = rules.filter((r) => r.id !== id);
    return new HttpResponse(null, { status: 204 });
  }),

  // GET /api/v1/policies/dimensions
  http.get('/api/v1/policies/dimensions', () =>
    HttpResponse.json(DIMENSION_WEIGHTS_FIXTURE),
  ),

  // PUT /api/v1/policies/dimensions
  http.put('/api/v1/policies/dimensions', async ({ request }) => {
    const body = (await request.json()) as typeof DIMENSION_WEIGHTS_FIXTURE;
    return HttpResponse.json(body);
  }),

  // GET /api/v1/policies/thresholds
  http.get('/api/v1/policies/thresholds', () =>
    HttpResponse.json(SCORE_THRESHOLDS_FIXTURE),
  ),

  // PUT /api/v1/policies/thresholds
  http.put('/api/v1/policies/thresholds', async ({ request }) => {
    const body = (await request.json()) as typeof SCORE_THRESHOLDS_FIXTURE;
    return HttpResponse.json(body);
  }),
];
