/**
 * Typed fetch wrapper for ForgeGuard API calls.
 *
 * Distinct from src/api/client.ts (Axios-based) — this module uses native
 * fetch and is consumed by TanStack Query hooks.
 */

import { getCsrfToken } from '@/stores/auth-store';
import { ApiError, NetworkError, ParseError } from '@/types/errors';
import { showPermissionDeniedNotification } from '@/lib/permission-interceptor';

const MUTATION_METHODS = new Set(['POST', 'PUT', 'PATCH', 'DELETE']);
const DEFAULT_TIMEOUT_MS = 30_000;

export interface ApiClientOptions extends RequestInit {
  timeout?: number;
}

/**
 * Build the full URL from the path and optional VITE_API_BASE_URL env var.
 * Supports both relative paths (same-origin) and absolute URLs (dev proxy).
 */
function buildUrl(path: string): string {
  const base = (import.meta.env.VITE_API_BASE_URL as string | undefined) ?? '';
  if (!base) return path;
  return `${base.replace(/\/$/, '')}/${path.replace(/^\//, '')}`;
}

/**
 * Core typed fetch wrapper.
 *
 * - Prepends VITE_API_BASE_URL to path
 * - Sets credentials: 'include' for cookie transmission
 * - Sets Content-Type: application/json
 * - Injects X-CSRF-Token on mutation methods (POST/PUT/PATCH/DELETE)
 * - Times out after `timeout` ms (default 30 s) via AbortController
 * - Parses JSON response body and returns it typed as T
 * - Throws ApiError for non-2xx responses
 * - Throws NetworkError for fetch failures (no response)
 * - Throws ParseError for invalid JSON
 * - Returns null for 204 No Content
 */
export async function apiClient<T>(
  path: string,
  options: ApiClientOptions = {},
): Promise<T> {
  const { timeout = DEFAULT_TIMEOUT_MS, ...fetchOptions } = options;
  const method = (fetchOptions.method ?? 'GET').toUpperCase();

  const controller = new AbortController();
  const timerId = setTimeout(() => controller.abort(), timeout);

  const headers = new Headers(fetchOptions.headers);
  headers.set('Content-Type', 'application/json');
  headers.set('Accept', 'application/json');

  if (MUTATION_METHODS.has(method)) {
    const token = getCsrfToken();
    if (token) {
      headers.set('X-CSRF-Token', token);
    }
  }

  const url = buildUrl(path);

  let response: Response;
  try {
    response = await fetch(url, {
      ...fetchOptions,
      method,
      headers,
      credentials: 'include',
      signal: fetchOptions.signal ?? controller.signal,
    });
  } catch (err) {
    clearTimeout(timerId);
    if (err instanceof DOMException && err.name === 'AbortError') {
      throw new NetworkError(`Request to ${url} timed out after ${timeout}ms`, err);
    }
    throw new NetworkError(
      'Unable to connect to the server — check your network connection',
      err,
    );
  } finally {
    clearTimeout(timerId);
  }

  if (response.status === 204) {
    return undefined as unknown as T;
  }

  if (!response.ok) {
    let rawBody: unknown = {};
    try {
      rawBody = await response.json();
    } catch {
      // Non-JSON error body — use defaults
    }

    // Intercept 403 Permission Denied: show a structured notification before
    // throwing so all callers benefit without per-component error handling.
    if (response.status === 403) {
      showPermissionDeniedNotification(rawBody);
    }

    const errorBody = rawBody as {
      detail?: string;
      status_code?: number;
      error_code?: string;
    };
    const detail = errorBody.detail ?? response.statusText;
    const errorCode = errorBody.error_code ?? String(response.status);

    if (import.meta.env.DEV) {
      console.error('[apiClient] error', { url, method, status: response.status, rawBody });
    }

    throw new ApiError(response.status, detail, errorCode);
  }

  const contentType = response.headers.get('Content-Type') ?? '';
  if (!contentType.includes('application/json')) {
    return undefined as unknown as T;
  }

  try {
    return (await response.json()) as T;
  } catch (err) {
    if (import.meta.env.DEV) {
      console.warn('[apiClient] JSON parse error', { url, err });
    }
    throw new ParseError(`Failed to parse response from ${url}`, err);
  }
}
