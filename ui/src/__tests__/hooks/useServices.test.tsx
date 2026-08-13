import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { renderHook, waitFor } from '@testing-library/react';
import { type ReactNode } from 'react';
import { afterAll, afterEach, beforeAll, describe, expect, it } from 'vitest';

import { useService, useServices } from '@/hooks/api/useServices';
import { SERVICE_FIXTURE, SERVICE_LIST_FIXTURE } from '@/test/mocks/handlers/services';
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

describe('useServices', () => {
  it('returns paginated service list', async () => {
    const { result } = renderHook(() => useServices(), { wrapper });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data).toEqual(SERVICE_LIST_FIXTURE);
    expect(result.current.data?.items).toHaveLength(2);
  });
});

describe('useService', () => {
  it('returns a single service by id', async () => {
    const { result } = renderHook(() => useService('svc-001'), { wrapper });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data).toEqual(SERVICE_FIXTURE);
  });

  it('returns error for unknown id', async () => {
    const { result } = renderHook(() => useService('svc-999'), { wrapper });
    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(result.current.error).toBeDefined();
  });

  it('does not fire query when id is empty', () => {
    const { result } = renderHook(() => useService(''), { wrapper });
    expect(result.current.fetchStatus).toBe('idle');
  });
});
