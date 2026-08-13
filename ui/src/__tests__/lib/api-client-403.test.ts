/**
 * Integration-style tests for the 403 interceptor in api-client (WO-086).
 *
 * Verifies that 403 responses trigger the permission notification, 401
 * responses do NOT trigger the permission notification, and malformed
 * 403 bodies fall back to the generic notification.
 */

import { afterAll, afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';
import { http, HttpResponse } from 'msw';

import { server } from '@/test/mocks/server';
import { apiClient } from '@/lib/api-client';
import { ApiError } from '@/types/errors';
import type { PermissionDeniedResponse } from '@/types/api-errors';

// Mock the notification system to capture calls
const mockNotificationsShow = vi.fn();
vi.mock('@mantine/notifications', () => ({
  notifications: { show: mockNotificationsShow },
}));

const VALID_403_BODY: PermissionDeniedResponse = {
  error: 'forbidden',
  permission: 'release.approve',
  required_role: ['Tech Lead', 'Platform Admin'],
  message: "Requires 'release.approve'.",
  action: 'Contact your Platform Admin.',
};

beforeAll(() => server.listen({ onUnhandledRequest: 'bypass' }));
afterEach(() => {
  server.resetHandlers();
  mockNotificationsShow.mockClear();
});
afterAll(() => server.close());

describe('apiClient — 403 permission interceptor', () => {
  it('calls showPermissionDeniedNotification for a structured 403', async () => {
    server.use(
      http.get('/api/v1/test-403', () =>
        HttpResponse.json(VALID_403_BODY, { status: 403 }),
      ),
    );

    await expect(apiClient('/api/v1/test-403')).rejects.toBeInstanceOf(ApiError);
    expect(mockNotificationsShow).toHaveBeenCalledOnce();
    const call = mockNotificationsShow.mock.calls[0][0] as { title: string };
    expect(call.title).toBe('Permission Denied');
  });

  it('still throws ApiError with status 403 after notification', async () => {
    server.use(
      http.get('/api/v1/test-403', () =>
        HttpResponse.json(VALID_403_BODY, { status: 403 }),
      ),
    );

    const error = await apiClient('/api/v1/test-403').catch((e) => e as ApiError);
    expect(error.status).toBe(403);
  });

  it('calls fallback notification for a 403 with non-standard body', async () => {
    server.use(
      http.get('/api/v1/test-403', () =>
        HttpResponse.json({ detail: 'Forbidden' }, { status: 403 }),
      ),
    );

    await expect(apiClient('/api/v1/test-403')).rejects.toBeInstanceOf(ApiError);
    expect(mockNotificationsShow).toHaveBeenCalledOnce();
    const call = mockNotificationsShow.mock.calls[0][0] as { id: string };
    expect(call.id).toBe('permission-denied:unknown');
  });

  it('does NOT call permission notification for 401 responses', async () => {
    server.use(
      http.get('/api/v1/test-401', () =>
        HttpResponse.json({ detail: 'Unauthorized' }, { status: 401 }),
      ),
    );

    await expect(apiClient('/api/v1/test-401')).rejects.toBeInstanceOf(ApiError);
    expect(mockNotificationsShow).not.toHaveBeenCalled();
  });

  it('does NOT call permission notification for 500 responses', async () => {
    server.use(
      http.get('/api/v1/test-500', () =>
        HttpResponse.json({ detail: 'Internal error' }, { status: 500 }),
      ),
    );

    await expect(apiClient('/api/v1/test-500')).rejects.toBeInstanceOf(ApiError);
    expect(mockNotificationsShow).not.toHaveBeenCalled();
  });

  it('does NOT call permission notification for 404 responses', async () => {
    server.use(
      http.get('/api/v1/test-404', () =>
        HttpResponse.json({ detail: 'Not found' }, { status: 404 }),
      ),
    );

    await expect(apiClient('/api/v1/test-404')).rejects.toBeInstanceOf(ApiError);
    expect(mockNotificationsShow).not.toHaveBeenCalled();
  });

  it('uses the permission slug as the notification ID for deduplication', async () => {
    server.use(
      http.get('/api/v1/test-403', () =>
        HttpResponse.json(VALID_403_BODY, { status: 403 }),
      ),
    );

    await apiClient('/api/v1/test-403').catch(() => undefined);
    const call = mockNotificationsShow.mock.calls[0][0] as { id: string };
    expect(call.id).toBe('permission-denied:release.approve');
  });
});
