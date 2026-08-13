import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { apiClient } from '@/lib/api-client';
import { ApiError, NetworkError } from '@/types/errors';

// Mock the auth store so we can control the CSRF token
vi.mock('@/stores/auth', () => ({
  getAccessToken: vi.fn(() => null),
}));

import { getAccessToken } from '@/stores/auth';

const mockGetAccessToken = vi.mocked(getAccessToken);

describe('apiClient', () => {
  const originalFetch = global.fetch;

  afterEach(() => {
    global.fetch = originalFetch;
    vi.clearAllMocks();
  });

  function mockFetch(status: number, body: unknown, headers: Record<string, string> = {}) {
    global.fetch = vi.fn().mockResolvedValue({
      ok: status >= 200 && status < 300,
      status,
      statusText: 'OK',
      headers: new Headers({ 'Content-Type': 'application/json', ...headers }),
      json: () => Promise.resolve(body),
    } as unknown as Response);
  }

  // -------------------------------------------------------------------------
  // Success
  // -------------------------------------------------------------------------

  it('returns parsed JSON for a 200 response', async () => {
    mockFetch(200, { id: '1', name: 'test' });
    const result = await apiClient<{ id: string; name: string }>('/api/v1/test');
    expect(result).toEqual({ id: '1', name: 'test' });
  });

  it('returns undefined for a 204 No Content response', async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 204,
      statusText: 'No Content',
      headers: new Headers({}),
      json: () => Promise.reject(new Error('no body')),
    } as unknown as Response);
    const result = await apiClient('/api/v1/test');
    expect(result).toBeUndefined();
  });

  // -------------------------------------------------------------------------
  // Error status codes
  // -------------------------------------------------------------------------

  it('throws ApiError with status 400', async () => {
    mockFetch(400, { detail: 'Bad request', status_code: 400, error_code: 'BAD_REQUEST' });
    await expect(apiClient('/api/v1/test')).rejects.toThrow(ApiError);
    await expect(apiClient('/api/v1/test')).rejects.toMatchObject({
      status: 400,
      detail: 'Bad request',
      errorCode: 'BAD_REQUEST',
    });
  });

  it('throws ApiError with status 401', async () => {
    mockFetch(401, { detail: 'Unauthorised', status_code: 401, error_code: 'UNAUTHORIZED' });
    await expect(apiClient('/api/v1/test')).rejects.toMatchObject({ status: 401 });
  });

  it('throws ApiError with status 403', async () => {
    mockFetch(403, { detail: 'Forbidden', status_code: 403, error_code: 'FORBIDDEN' });
    await expect(apiClient('/api/v1/test')).rejects.toMatchObject({ status: 403 });
  });

  it('throws ApiError with status 404', async () => {
    mockFetch(404, { detail: 'Not found', status_code: 404, error_code: 'NOT_FOUND' });
    await expect(apiClient('/api/v1/test')).rejects.toMatchObject({ status: 404 });
  });

  it('throws ApiError with status 500', async () => {
    mockFetch(500, { detail: 'Server error', status_code: 500, error_code: 'INTERNAL_ERROR' });
    await expect(apiClient('/api/v1/test')).rejects.toMatchObject({ status: 500 });
  });

  // -------------------------------------------------------------------------
  // CSRF header injection
  // -------------------------------------------------------------------------

  it('injects X-CSRF-Token on POST when token is available', async () => {
    mockGetAccessToken.mockReturnValue('csrf-token-123');
    mockFetch(201, { id: 'new' });

    await apiClient('/api/v1/test', { method: 'POST', body: JSON.stringify({}) });

    const calledHeaders = (global.fetch as ReturnType<typeof vi.fn>).mock.calls[0][1].headers as Headers;
    expect(calledHeaders.get('X-CSRF-Token')).toBe('csrf-token-123');
  });

  it('does NOT inject X-CSRF-Token on GET', async () => {
    mockGetAccessToken.mockReturnValue('csrf-token-123');
    mockFetch(200, { id: '1' });

    await apiClient('/api/v1/test', { method: 'GET' });

    const calledHeaders = (global.fetch as ReturnType<typeof vi.fn>).mock.calls[0][1].headers as Headers;
    expect(calledHeaders.get('X-CSRF-Token')).toBeNull();
  });

  it('does NOT inject X-CSRF-Token on POST when no token', async () => {
    mockGetAccessToken.mockReturnValue(null);
    mockFetch(201, { id: 'new' });

    await apiClient('/api/v1/test', { method: 'POST', body: JSON.stringify({}) });

    const calledHeaders = (global.fetch as ReturnType<typeof vi.fn>).mock.calls[0][1].headers as Headers;
    expect(calledHeaders.get('X-CSRF-Token')).toBeNull();
  });

  // -------------------------------------------------------------------------
  // Network failures
  // -------------------------------------------------------------------------

  it('throws NetworkError when fetch itself fails', async () => {
    global.fetch = vi.fn().mockRejectedValue(new Error('Network down'));
    await expect(apiClient('/api/v1/test')).rejects.toThrow(NetworkError);
  });

  it('sets credentials: include on every request', async () => {
    mockFetch(200, {});
    await apiClient('/api/v1/test');
    const callOptions = (global.fetch as ReturnType<typeof vi.fn>).mock.calls[0][1];
    expect(callOptions.credentials).toBe('include');
  });
});
