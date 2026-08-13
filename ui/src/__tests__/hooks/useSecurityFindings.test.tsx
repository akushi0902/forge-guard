/**
 * Integration tests for useSecurityFindings hooks (WO-077, AC-8).
 *
 * Verifies that TanStack Query hooks correctly fetch from:
 *   GET /api/v1/findings?dimension=security
 *   GET /api/v1/releases?status=escalated
 *   GET /api/v1/exceptions?status=pending
 */

import {
  afterAll,
  afterEach,
  beforeAll,
  describe,
  expect,
  it,
} from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { http, HttpResponse } from 'msw';
import { type ReactNode } from 'react';

import { server } from '@/test/mocks/server';
import {
  useSecurityFindings,
  usePendingEscalations,
  usePendingExceptions,
} from '@/hooks/api/useSecurityFindings';
import {
  SECURITY_FINDINGS_PAGINATED,
  ESCALATIONS_PAGINATED,
  PENDING_EXCEPTIONS_PAGINATED,
} from '@/test/fixtures/securityFindings';

// ---------------------------------------------------------------------------
// Test wrapper
// ---------------------------------------------------------------------------

function makeWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: 0 }, mutations: { retry: false } },
  });
  return ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );
}

// ---------------------------------------------------------------------------
// MSW setup
// ---------------------------------------------------------------------------

beforeAll(() => server.listen({ onUnhandledRequest: 'warn' }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

// ---------------------------------------------------------------------------
// useSecurityFindings
// ---------------------------------------------------------------------------

describe('useSecurityFindings — hook', () => {
  it('fetches security findings with dimension=security parameter', async () => {
    let capturedUrl = '';
    server.use(
      http.get('/api/v1/findings', ({ request }) => {
        capturedUrl = request.url;
        return HttpResponse.json(SECURITY_FINDINGS_PAGINATED);
      }),
    );

    const { result } = renderHook(() => useSecurityFindings(), { wrapper: makeWrapper() });

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });

    expect(capturedUrl).toContain('dimension=security');
    expect(result.current.data?.items).toHaveLength(4);
    expect(result.current.data?.total_count).toBe(4);
  });

  it('includes severity=critical,high by default', async () => {
    let capturedUrl = '';
    server.use(
      http.get('/api/v1/findings', ({ request }) => {
        capturedUrl = request.url;
        return HttpResponse.json(SECURITY_FINDINGS_PAGINATED);
      }),
    );

    const { result } = renderHook(() => useSecurityFindings(), { wrapper: makeWrapper() });

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });

    expect(capturedUrl).toContain('severity=critical%2Chigh');
  });

  it('returns error state on 500 response', async () => {
    server.use(
      http.get('/api/v1/findings', () =>
        HttpResponse.json({ detail: 'Server error' }, { status: 500 }),
      ),
    );

    const { result } = renderHook(() => useSecurityFindings(), { wrapper: makeWrapper() });

    await waitFor(() => {
      expect(result.current.isError).toBe(true);
    });
  });

  it('returns empty items array when no findings', async () => {
    server.use(
      http.get('/api/v1/findings', () =>
        HttpResponse.json({ items: [], cursor: null, total_count: 0 }),
      ),
    );

    const { result } = renderHook(() => useSecurityFindings(), { wrapper: makeWrapper() });

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });

    expect(result.current.data?.items).toHaveLength(0);
  });
});

// ---------------------------------------------------------------------------
// usePendingEscalations
// ---------------------------------------------------------------------------

describe('usePendingEscalations — hook', () => {
  it('fetches escalated releases with status=escalated parameter', async () => {
    let capturedUrl = '';
    server.use(
      http.get('/api/v1/releases', ({ request }) => {
        capturedUrl = request.url;
        return HttpResponse.json(ESCALATIONS_PAGINATED);
      }),
    );

    const { result } = renderHook(() => usePendingEscalations(), { wrapper: makeWrapper() });

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });

    expect(capturedUrl).toContain('status=escalated');
    expect(result.current.data?.items).toHaveLength(2);
  });
});

// ---------------------------------------------------------------------------
// usePendingExceptions
// ---------------------------------------------------------------------------

describe('usePendingExceptions — hook', () => {
  it('fetches pending exceptions with status=pending parameter', async () => {
    let capturedUrl = '';
    server.use(
      http.get('/api/v1/exceptions', ({ request }) => {
        capturedUrl = request.url;
        return HttpResponse.json(PENDING_EXCEPTIONS_PAGINATED);
      }),
    );

    const { result } = renderHook(() => usePendingExceptions(), { wrapper: makeWrapper() });

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });

    expect(capturedUrl).toContain('status=pending');
    expect(result.current.data?.items).toHaveLength(2);
  });
});
