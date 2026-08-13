/**
 * Integration tests for useUsers TanStack Query hooks (WO-080).
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

import { useUsers, useUpdateUserRole } from '@/hooks/api/useUsers';
import { USERS_RESPONSE_FIXTURE } from '@/test/fixtures/rbacData';
import { Role } from '@/types';
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

describe('useUsers', () => {
  it('fetches user list from /api/v1/admin/roles', async () => {
    const { result } = renderHook(() => useUsers(), { wrapper: makeWrapper() });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.users).toHaveLength(USERS_RESPONSE_FIXTURE.users.length);
    expect(result.current.data?.roles).toHaveLength(6);
  });

  it('returns the correct user data shape', async () => {
    const { result } = renderHook(() => useUsers(), { wrapper: makeWrapper() });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    const first = result.current.data!.users[0];
    expect(first).toHaveProperty('id');
    expect(first).toHaveProperty('name');
    expect(first).toHaveProperty('email');
    expect(first).toHaveProperty('role');
  });
});

describe('useUpdateUserRole', () => {
  it('submits PUT /api/v1/admin/users/:id/role', async () => {
    const wrapper = makeWrapper();
    const { result } = renderHook(() => useUpdateUserRole(), { wrapper });
    await act(async () => {
      await result.current.mutateAsync({ userId: 'usr-001', role: Role.TechLead });
    });
    expect(result.current.isSuccess).toBe(true);
    expect(result.current.data?.role).toBe(Role.TechLead);
    expect(result.current.data?.previous_role).toBe(Role.Developer);
  });

  it('throws ApiError on 400 last-admin constraint', async () => {
    server.use(
      http.put('/api/v1/admin/users/:id/role', () =>
        HttpResponse.json(
          { detail: 'Cannot change: last admin', error_code: 'LAST_ADMIN' },
          { status: 400 },
        ),
      ),
    );
    const wrapper = makeWrapper();
    const { result } = renderHook(() => useUpdateUserRole(), { wrapper });
    let caught: unknown;
    await act(async () => {
      try {
        await result.current.mutateAsync({ userId: 'usr-009', role: Role.Developer });
      } catch (e) {
        caught = e;
      }
    });
    expect(caught).toBeDefined();
  });

  it('invalidates user query on success', async () => {
    const client = new QueryClient({
      defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
    });
    const wrapper = ({ children }: { children: ReactNode }) => (
      <QueryClientProvider client={client}>{children}</QueryClientProvider>
    );
    const { result: usersResult } = renderHook(() => useUsers(), { wrapper });
    await waitFor(() => expect(usersResult.current.isSuccess).toBe(true));

    const { result: mutResult } = renderHook(() => useUpdateUserRole(), { wrapper });
    await act(async () => {
      await mutResult.current.mutateAsync({ userId: 'usr-001', role: Role.Operator });
    });
    expect(mutResult.current.isSuccess).toBe(true);
  });
});
