/**
 * Auth refresh interceptor.
 *
 * Handles the 401 → refresh → retry flow transparently.  A module-level
 * `refreshPromise` deduplicates concurrent 401s so only one refresh request
 * is ever in flight at a time — all queued retries await the same promise.
 *
 * Refresh failure counter: after `MAX_REFRESH_FAILURES` consecutive refresh
 * errors the interceptor forces a full logout to break infinite retry loops.
 *
 * Usage:
 *   const data = await withAuthRetry(() => apiClient<MyType>('/api/v1/...'));
 */

import { useAuthStore } from '@/stores/auth-store';
import { ApiError } from '@/types/errors';

/** Maximum consecutive refresh failures before forcing logout. */
const MAX_REFRESH_FAILURES = 3;

/** In-flight refresh promise — shared across all concurrent 401 handlers. */
let refreshPromise: Promise<void> | null = null;

/** Consecutive refresh failure counter. */
let refreshFailureCount = 0;

/**
 * Execute `request()` and, on a 401 response, transparently refresh the auth
 * token and retry the original request once.
 *
 * If the refresh itself fails (returns 401 or throws), clears auth state and
 * re-throws so the caller can redirect to the login page.
 *
 * Race condition safety: if multiple callers receive 401 concurrently, all
 * await the same `refreshPromise` — only one actual HTTP refresh call is made.
 */
export async function withAuthRetry<T>(request: () => Promise<T>): Promise<T> {
  try {
    return await request();
  } catch (error) {
    if (!(error instanceof ApiError) || error.status !== 401) {
      throw error;
    }

    // 401 received — attempt a token refresh.
    if (!refreshPromise) {
      refreshPromise = useAuthStore
        .getState()
        .refreshToken()
        .then(() => {
          refreshFailureCount = 0;
        })
        .catch((refreshError: unknown) => {
          refreshFailureCount += 1;
          if (refreshFailureCount >= MAX_REFRESH_FAILURES) {
            refreshFailureCount = 0;
            void useAuthStore.getState().logout();
          }
          throw refreshError;
        })
        .finally(() => {
          refreshPromise = null;
        });
    }

    // All concurrent 401 callers await the same refresh.
    await refreshPromise;

    // Retry the original request with the new token (now in cookie).
    return await request();
  }
}

/**
 * Reset the refresh failure counter and any in-flight promise.
 * Useful in tests or after a successful manual re-login.
 */
export function resetRefreshState(): void {
  refreshPromise = null;
  refreshFailureCount = 0;
}
