/**
 * Integration tests for usePolicies TanStack Query hooks (WO-079).
 *
 * Validates CRUD operations against MSW mock handlers.
 */

import {
  afterAll,
  afterEach,
  beforeAll,
  describe,
  expect,
  it,
} from 'vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { renderHook, waitFor, act } from '@testing-library/react';
import { type ReactNode } from 'react';
import { http, HttpResponse } from 'msw';

import {
  usePolicies,
  useCreatePolicy,
  useUpdatePolicy,
  useDeletePolicy,
  useDimensionWeights,
  useScoreThresholds,
} from '@/hooks/api/usePolicies';
import {
  POLICY_RULES_RESPONSE_FIXTURE,
  DIMENSION_WEIGHTS_FIXTURE,
  SCORE_THRESHOLDS_FIXTURE,
} from '@/test/fixtures/policyData';
import { PolicyDimension, PolicySeverity } from '@/types/api';
import { server } from '@/test/mocks/server';

beforeAll(() => server.listen({ onUnhandledRequest: 'warn' }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

function makeWrapper() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  );
}

describe('usePolicies', () => {
  it('returns policy rules list', async () => {
    const { result } = renderHook(() => usePolicies(), { wrapper: makeWrapper() });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.items).toHaveLength(
      POLICY_RULES_RESPONSE_FIXTURE.items.length,
    );
  });

  it('passes filter params to the API', async () => {
    server.use(
      http.get('/api/v1/policies', ({ request }) => {
        const url = new URL(request.url);
        const dimension = url.searchParams.get('dimension');
        if (dimension === 'security') {
          return HttpResponse.json({
            items: POLICY_RULES_RESPONSE_FIXTURE.items.filter(
              (r) => r.dimension === PolicyDimension.Security,
            ),
            cursor: null,
            total: 2,
          });
        }
        return HttpResponse.json(POLICY_RULES_RESPONSE_FIXTURE);
      }),
    );
    const { result } = renderHook(
      () => usePolicies({ dimension: 'security' }),
      { wrapper: makeWrapper() },
    );
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.items.every((r) => r.dimension === PolicyDimension.Security)).toBe(true);
  });
});

describe('useCreatePolicy', () => {
  it('creates a new policy rule', async () => {
    const wrapper = makeWrapper();
    const { result } = renderHook(() => useCreatePolicy(), { wrapper });
    await act(async () => {
      await result.current.mutateAsync({
        name: 'New test rule',
        dimension: PolicyDimension.CodeQuality,
        severity: PolicySeverity.Medium,
        threshold: 75,
      });
    });
    expect(result.current.isSuccess).toBe(true);
    expect(result.current.data?.name).toBe('New test rule');
  });

  it('throws ApiError on 409 conflict', async () => {
    server.use(
      http.post('/api/v1/policies', () =>
        HttpResponse.json(
          { detail: 'Duplicate', error_code: 'DUPLICATE_NAME' },
          { status: 409 },
        ),
      ),
    );
    const wrapper = makeWrapper();
    const { result } = renderHook(() => useCreatePolicy(), { wrapper });
    let caught: unknown;
    await act(async () => {
      try {
        await result.current.mutateAsync({
          name: 'Existing rule',
          dimension: PolicyDimension.Security,
          severity: PolicySeverity.Critical,
          threshold: 0,
        });
      } catch (e) {
        caught = e;
      }
    });
    expect(caught).toBeDefined();
  });
});

describe('useUpdatePolicy', () => {
  it('updates an existing rule', async () => {
    const wrapper = makeWrapper();
    const { result } = renderHook(() => useUpdatePolicy('pol-001'), { wrapper });
    await act(async () => {
      await result.current.mutateAsync({ enabled: false });
    });
    expect(result.current.isSuccess).toBe(true);
  });
});

describe('useDeletePolicy', () => {
  it('deletes a policy rule (204 response)', async () => {
    const wrapper = makeWrapper();
    const { result } = renderHook(() => useDeletePolicy('pol-001'), { wrapper });
    await act(async () => {
      await result.current.mutateAsync();
    });
    expect(result.current.isSuccess).toBe(true);
  });
});

describe('useDimensionWeights', () => {
  it('returns dimension weights', async () => {
    const { result } = renderHook(() => useDimensionWeights(), { wrapper: makeWrapper() });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data).toEqual(DIMENSION_WEIGHTS_FIXTURE);
    const total = result.current.data!.reduce((sum, d) => sum + d.weight, 0);
    expect(total).toBe(100);
  });
});

describe('useScoreThresholds', () => {
  it('returns score thresholds', async () => {
    const { result } = renderHook(() => useScoreThresholds(), { wrapper: makeWrapper() });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data).toEqual(SCORE_THRESHOLDS_FIXTURE);
    expect(result.current.data!.approve.min_health).toBe(70);
    expect(result.current.data!.conditional.min_health).toBe(50);
    // Approve health threshold must be stricter than conditional
    expect(result.current.data!.approve.min_health).toBeGreaterThan(
      result.current.data!.conditional.min_health,
    );
  });
});
