/**
 * Unit tests for the auth Zustand store.
 *
 * Uses vi.stubGlobal to mock fetch — the store is tested in isolation from MSW
 * so we can precisely control response headers and bodies.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { useAuthStore } from '@/stores/auth-store';
import { Role } from '@/types';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const TEST_USER = {
  id: 'user-001',
  email: 'dev@forgeguard.io',
  name: 'Alice Dev',
  role: Role.Developer,
  permissions: ['service:read'],
};

const TEST_CSRF = 'csrf-token-abc';

function makeFetchResponse(
  body: unknown,
  opts: { status?: number; csrfToken?: string } = {},
): Response {
  const headers = new Headers({ 'Content-Type': 'application/json' });
  if (opts.csrfToken) headers.set('X-CSRF-Token', opts.csrfToken);
  return new Response(JSON.stringify(body), {
    status: opts.status ?? 200,
    headers,
  });
}

// ---------------------------------------------------------------------------
// Setup / teardown
// ---------------------------------------------------------------------------

beforeEach(() => {
  // Reset store to initial state before each test.
  useAuthStore.setState({
    user: null,
    isAuthenticated: false,
    isLoading: false,
    csrfToken: null,
  });
  sessionStorage.clear();
});

afterEach(() => {
  vi.restoreAllMocks();
});

// ---------------------------------------------------------------------------
// login()
// ---------------------------------------------------------------------------

describe('login()', () => {
  it('populates user, isAuthenticated, and csrfToken on success', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValueOnce(makeFetchResponse({ user: TEST_USER }, { csrfToken: TEST_CSRF })),
    );

    await useAuthStore.getState().login('dev@forgeguard.io', 'password');

    const state = useAuthStore.getState();
    expect(state.isAuthenticated).toBe(true);
    expect(state.user).toEqual(TEST_USER);
    expect(state.csrfToken).toBe(TEST_CSRF);
    expect(state.isLoading).toBe(false);
  });

  it('sends credentials: include to /api/v1/auth/login', async () => {
    const mockFetch = vi.fn().mockResolvedValueOnce(
      makeFetchResponse({ user: TEST_USER }, { csrfToken: TEST_CSRF }),
    );
    vi.stubGlobal('fetch', mockFetch);

    await useAuthStore.getState().login('dev@forgeguard.io', 'password');

    expect(mockFetch).toHaveBeenCalledWith('/api/v1/auth/login', expect.objectContaining({
      method: 'POST',
      credentials: 'include',
    }));
  });

  it('does not include the password in the stored user object', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValueOnce(makeFetchResponse({ user: TEST_USER }, { csrfToken: TEST_CSRF })),
    );

    await useAuthStore.getState().login('dev@forgeguard.io', 's3cr3t');

    const state = useAuthStore.getState();
    expect(JSON.stringify(state)).not.toContain('s3cr3t');
  });

  it('throws and clears isLoading on 401', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValueOnce(
        makeFetchResponse({ detail: 'Invalid credentials' }, { status: 401 }),
      ),
    );

    await expect(useAuthStore.getState().login('bad@example.com', 'wrong')).rejects.toMatchObject({
      status: 401,
    });

    const state = useAuthStore.getState();
    expect(state.isAuthenticated).toBe(false);
    expect(state.isLoading).toBe(false);
    expect(state.user).toBeNull();
  });

  it('throws and clears isLoading on 429 lockout', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValueOnce(
        makeFetchResponse({ detail: 'Account locked' }, { status: 429 }),
      ),
    );

    await expect(useAuthStore.getState().login('locked@example.com', 'pass')).rejects.toMatchObject({
      status: 429,
    });

    expect(useAuthStore.getState().isLoading).toBe(false);
  });
});

// ---------------------------------------------------------------------------
// logout()
// ---------------------------------------------------------------------------

describe('logout()', () => {
  it('clears all auth state', async () => {
    useAuthStore.setState({ user: TEST_USER, isAuthenticated: true, csrfToken: TEST_CSRF });
    vi.stubGlobal('fetch', vi.fn().mockResolvedValueOnce(new Response(null, { status: 204 })));

    await useAuthStore.getState().logout();

    const state = useAuthStore.getState();
    expect(state.user).toBeNull();
    expect(state.isAuthenticated).toBe(false);
    expect(state.csrfToken).toBeNull();
    expect(state.isLoading).toBe(false);
  });

  it('sends X-CSRF-Token header when token is present', async () => {
    useAuthStore.setState({ csrfToken: TEST_CSRF });
    const mockFetch = vi.fn().mockResolvedValueOnce(new Response(null, { status: 204 }));
    vi.stubGlobal('fetch', mockFetch);

    await useAuthStore.getState().logout();

    expect(mockFetch).toHaveBeenCalledWith('/api/v1/auth/logout', expect.objectContaining({
      headers: expect.objectContaining({ 'X-CSRF-Token': TEST_CSRF }),
    }));
  });

  it('clears state even when logout network call fails', async () => {
    useAuthStore.setState({ user: TEST_USER, isAuthenticated: true });
    vi.stubGlobal('fetch', vi.fn().mockRejectedValueOnce(new Error('network')));

    await useAuthStore.getState().logout();

    expect(useAuthStore.getState().isAuthenticated).toBe(false);
    expect(useAuthStore.getState().user).toBeNull();
  });

  it('clears sessionStorage', async () => {
    sessionStorage.setItem('forgeguard-auth', JSON.stringify({ user: TEST_USER }));
    vi.stubGlobal('fetch', vi.fn().mockResolvedValueOnce(new Response(null, { status: 204 })));

    await useAuthStore.getState().logout();

    expect(sessionStorage.getItem('forgeguard-auth')).toBeNull();
  });
});

// ---------------------------------------------------------------------------
// refreshToken()
// ---------------------------------------------------------------------------

describe('refreshToken()', () => {
  it('updates csrfToken and user on success', async () => {
    const newCsrf = 'new-csrf-xyz';
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValueOnce(makeFetchResponse({ user: TEST_USER }, { csrfToken: newCsrf })),
    );

    await useAuthStore.getState().refreshToken();

    const state = useAuthStore.getState();
    expect(state.csrfToken).toBe(newCsrf);
    expect(state.user).toEqual(TEST_USER);
    expect(state.isAuthenticated).toBe(true);
  });

  it('clears state and throws on 401 (expired refresh token)', async () => {
    useAuthStore.setState({ user: TEST_USER, isAuthenticated: true, csrfToken: TEST_CSRF });
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValueOnce(makeFetchResponse({ detail: 'Expired' }, { status: 401 })),
    );

    await expect(useAuthStore.getState().refreshToken()).rejects.toMatchObject({ status: 401 });

    const state = useAuthStore.getState();
    expect(state.isAuthenticated).toBe(false);
    expect(state.user).toBeNull();
    expect(state.csrfToken).toBeNull();
  });

  it('sends credentials: include', async () => {
    const mockFetch = vi.fn().mockResolvedValueOnce(
      makeFetchResponse({ user: TEST_USER }, { csrfToken: 'tok' }),
    );
    vi.stubGlobal('fetch', mockFetch);

    await useAuthStore.getState().refreshToken();

    expect(mockFetch).toHaveBeenCalledWith('/api/v1/auth/refresh', expect.objectContaining({
      credentials: 'include',
    }));
  });
});

// ---------------------------------------------------------------------------
// csrfToken is never persisted
// ---------------------------------------------------------------------------

describe('persistence', () => {
  it('does not persist csrfToken to sessionStorage', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValueOnce(makeFetchResponse({ user: TEST_USER }, { csrfToken: TEST_CSRF })),
    );

    await useAuthStore.getState().login('dev@forgeguard.io', 'password');

    const persisted = JSON.parse(sessionStorage.getItem('forgeguard-auth') ?? '{}') as Record<string, unknown>;
    expect(persisted).not.toHaveProperty('state.csrfToken');
  });

  it('persists isAuthenticated and user to sessionStorage', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValueOnce(makeFetchResponse({ user: TEST_USER }, { csrfToken: TEST_CSRF })),
    );

    await useAuthStore.getState().login('dev@forgeguard.io', 'password');

    const persisted = JSON.parse(sessionStorage.getItem('forgeguard-auth') ?? '{}') as { state?: Record<string, unknown> };
    expect(persisted.state?.['isAuthenticated']).toBe(true);
    expect(persisted.state?.['user']).toMatchObject({ id: TEST_USER.id });
  });
});
