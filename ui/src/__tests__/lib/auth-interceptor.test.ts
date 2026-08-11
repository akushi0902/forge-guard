/**
 * Unit tests for the auth refresh interceptor.
 *
 * Covers:
 *  - Passthrough for successful requests
 *  - 401 → refresh → retry flow
 *  - Concurrent 401 race condition (only 1 refresh issued)
 *  - Refresh failure → clears state and re-throws
 *  - Max-failure force logout after 3 consecutive refresh failures
 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { resetRefreshState, withAuthRetry } from '@/lib/auth-interceptor';
import { useAuthStore } from '@/stores/auth-store';
import { ApiError } from '@/types/errors';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function makeRequest<T>(result: T): () => Promise<T> {
  return () => Promise.resolve(result);
}

function make401Request(): () => Promise<never> {
  return () => Promise.reject(new ApiError(401, 'Unauthorized', 'UNAUTHORIZED'));
}

// ---------------------------------------------------------------------------
// Setup
// ---------------------------------------------------------------------------

beforeEach(() => {
  resetRefreshState();
  useAuthStore.setState({ user: null, isAuthenticated: false, isLoading: false, csrfToken: null });
});

afterEach(() => {
  vi.restoreAllMocks();
  resetRefreshState();
});

// ---------------------------------------------------------------------------
// Happy path
// ---------------------------------------------------------------------------

describe('withAuthRetry - happy path', () => {
  it('returns the value from a successful request without calling refresh', async () => {
    const refreshSpy = vi.spyOn(useAuthStore.getState(), 'refreshToken');
    const result = await withAuthRetry(makeRequest('hello'));
    expect(result).toBe('hello');
    expect(refreshSpy).not.toHaveBeenCalled();
  });

  it('propagates non-401 errors without refreshing', async () => {
    const err = new ApiError(403, 'Forbidden', 'FORBIDDEN');
    const refreshSpy = vi.spyOn(useAuthStore.getState(), 'refreshToken');

    await expect(withAuthRetry(() => Promise.reject(err))).rejects.toBe(err);
    expect(refreshSpy).not.toHaveBeenCalled();
  });

  it('propagates non-ApiError exceptions without refreshing', async () => {
    const err = new Error('network');
    const refreshSpy = vi.spyOn(useAuthStore.getState(), 'refreshToken');

    await expect(withAuthRetry(() => Promise.reject(err))).rejects.toBe(err);
    expect(refreshSpy).not.toHaveBeenCalled();
  });
});

// ---------------------------------------------------------------------------
// Refresh and retry
// ---------------------------------------------------------------------------

describe('withAuthRetry - 401 → refresh → retry', () => {
  it('retries the request after a successful refresh', async () => {
    let callCount = 0;
    vi.spyOn(useAuthStore.getState(), 'refreshToken').mockResolvedValue(undefined);

    const request = (): Promise<string> => {
      callCount += 1;
      if (callCount === 1) return Promise.reject(new ApiError(401, 'Unauthorized', 'UNAUTH'));
      return Promise.resolve('retried-value');
    };

    const result = await withAuthRetry(request);
    expect(result).toBe('retried-value');
    expect(callCount).toBe(2);
  });

  it('throws after a failed refresh and does not retry', async () => {
    const refreshError = new Error('session expired');
    vi.spyOn(useAuthStore.getState(), 'refreshToken').mockRejectedValue(refreshError);

    let callCount = 0;
    const request = (): Promise<never> => {
      callCount += 1;
      return Promise.reject(new ApiError(401, 'Unauthorized', 'UNAUTH'));
    };

    await expect(withAuthRetry(request)).rejects.toBe(refreshError);
    expect(callCount).toBe(1);
  });
});

// ---------------------------------------------------------------------------
// Concurrent 401 race condition
// ---------------------------------------------------------------------------

describe('withAuthRetry - concurrent 401 deduplication', () => {
  it('issues only one refresh when multiple concurrent requests get 401', async () => {
    let refreshCallCount = 0;

    vi.spyOn(useAuthStore.getState(), 'refreshToken').mockImplementation(async () => {
      refreshCallCount += 1;
      await new Promise((resolve) => setTimeout(resolve, 10));
    });

    let attempt = 0;
    const request = (): Promise<string> => {
      if (attempt === 0) {
        attempt += 1;
        return Promise.reject(new ApiError(401, 'Unauthorized', 'UNAUTH'));
      }
      return Promise.resolve('ok');
    };

    // Fire 5 concurrent requests — all will hit 401 on first attempt.
    const results = await Promise.all(
      Array.from({ length: 5 }, () => {
        let firstCall = true;
        return withAuthRetry(() => {
          if (firstCall) {
            firstCall = false;
            return Promise.reject(new ApiError(401, 'Unauthorized', 'UNAUTH'));
          }
          return Promise.resolve('ok');
        });
      }),
    );

    expect(refreshCallCount).toBe(1);
    expect(results).toHaveLength(5);
    results.forEach((r) => expect(r).toBe('ok'));
  });
});

// ---------------------------------------------------------------------------
// Force logout after max failures
// ---------------------------------------------------------------------------

describe('withAuthRetry - max failure force logout', () => {
  it('calls logout after 3 consecutive refresh failures', async () => {
    const logoutSpy = vi.spyOn(useAuthStore.getState(), 'logout').mockResolvedValue(undefined);
    vi.spyOn(useAuthStore.getState(), 'refreshToken').mockRejectedValue(new Error('expired'));

    const failingRequest = (): Promise<never> =>
      Promise.reject(new ApiError(401, 'Unauthorized', 'UNAUTH'));

    // Each withAuthRetry call will attempt a refresh, fail, and increment the
    // failure counter. The refreshPromise is cleared by the .finally() handler
    // in the interceptor itself — we must NOT call resetRefreshState() here or
    // the counter would reset between calls.
    for (let i = 0; i < 3; i++) {
      await expect(withAuthRetry(failingRequest)).rejects.toBeInstanceOf(Error);
      // Allow .finally() microtask to clear refreshPromise before next iteration.
      await Promise.resolve();
    }

    // Give the async logout a microtask to run.
    await Promise.resolve();
    expect(logoutSpy).toHaveBeenCalledTimes(1);
  });
});
