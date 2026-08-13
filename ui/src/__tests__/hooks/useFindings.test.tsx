import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { renderHook, waitFor } from '@testing-library/react';
import { type ReactNode } from 'react';
import { afterAll, afterEach, beforeAll, describe, expect, it } from 'vitest';

import { useFindingRecommendation, useServiceFindings } from '@/hooks/api/useFindings';
import {
  FINDING_LIST_FIXTURE,
  RECOMMENDATION_FIXTURE,
} from '@/test/mocks/handlers/findings';
import { server } from '@/test/mocks/server';

beforeAll(() => server.listen({ onUnhandledRequest: 'warn' }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

describe('useServiceFindings', () => {
  it('returns finding list for a service', async () => {
    const { result } = renderHook(() => useServiceFindings('svc-001'), { wrapper });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data).toEqual(FINDING_LIST_FIXTURE);
    expect(result.current.data?.items).toHaveLength(1);
  });
});

describe('useFindingRecommendation', () => {
  it('returns recommendation for a finding', async () => {
    const { result } = renderHook(() => useFindingRecommendation('fnd-001'), { wrapper });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data).toEqual(RECOMMENDATION_FIXTURE);
  });
});
