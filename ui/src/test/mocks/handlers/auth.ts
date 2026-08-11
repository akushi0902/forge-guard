import { http, HttpResponse } from 'msw';

import type { User } from '@/stores/auth-store';
import { Role } from '@/types';

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

export const TEST_CSRF_TOKEN = 'test-csrf-token-abc123';
export const REFRESHED_CSRF_TOKEN = 'refreshed-csrf-token-xyz789';

export const developerUser: User = {
  id: 'user-dev-001',
  email: 'dev@forgeguard.io',
  name: 'Alice Developer',
  role: Role.Developer,
  permissions: ['service:read', 'finding:read', 'score:read'],
};

// Valid test credentials
export const VALID_EMAIL = 'dev@forgeguard.io';
export const VALID_PASSWORD = 'valid-password-123';
export const LOCKED_EMAIL = 'locked@forgeguard.io';

// ---------------------------------------------------------------------------
// Default handlers — used by the shared MSW server
// ---------------------------------------------------------------------------

/** Login: success / 401 invalid credentials / 429 account lockout */
const loginHandler = http.post('/api/v1/auth/login', async ({ request }) => {
  const body = (await request.json()) as { email?: string; password?: string };

  if (body.email === LOCKED_EMAIL) {
    return HttpResponse.json(
      {
        detail: 'Account locked — try again in 15 minutes',
        status_code: 429,
        error_code: 'ACCOUNT_LOCKED',
      },
      { status: 429 },
    );
  }

  if (body.email !== VALID_EMAIL || body.password !== VALID_PASSWORD) {
    return HttpResponse.json(
      {
        detail: 'Invalid email or password',
        status_code: 401,
        error_code: 'INVALID_CREDENTIALS',
      },
      { status: 401 },
    );
  }

  return HttpResponse.json(
    { user: developerUser },
    { headers: { 'X-CSRF-Token': TEST_CSRF_TOKEN } },
  );
});

/** Refresh: success with new CSRF token */
const refreshHandler = http.post('/api/v1/auth/refresh', () =>
  HttpResponse.json(
    { user: developerUser },
    { headers: { 'X-CSRF-Token': REFRESHED_CSRF_TOKEN } },
  ),
);

/** Logout: 204 No Content */
const logoutHandler = http.post('/api/v1/auth/logout', () => new HttpResponse(null, { status: 204 }));

export const authHandlers = [loginHandler, refreshHandler, logoutHandler];

// ---------------------------------------------------------------------------
// Override handlers — use with server.use(...) in individual tests
// ---------------------------------------------------------------------------

/** Refresh returns 401 — session fully expired */
export const expiredRefreshHandler = http.post('/api/v1/auth/refresh', () =>
  HttpResponse.json(
    {
      detail: 'Refresh token expired',
      status_code: 401,
      error_code: 'TOKEN_EXPIRED',
    },
    { status: 401 },
  ),
);

/** Login returns 500 service error */
export const serverErrorLoginHandler = http.post('/api/v1/auth/login', () =>
  HttpResponse.json(
    {
      detail: 'Authentication service unavailable',
      status_code: 500,
      error_code: 'SERVER_ERROR',
    },
    { status: 500 },
  ),
);
