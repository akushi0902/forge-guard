/**
 * CSRF token utilities.
 *
 * The backend sends a fresh CSRF token in the X-CSRF-Token response header
 * on every login and token refresh.  Mutation requests (POST/PUT/PATCH/DELETE)
 * must echo this token back in the same header so the server can validate it
 * against the HMAC derived from the access token's JTI claim.
 *
 * The token is stored in-memory via the auth store — never in localStorage or
 * sessionStorage — to prevent XSS extraction.
 */

import { getCsrfToken } from '@/stores/auth-store';

/** HTTP methods that require a CSRF token. */
export const MUTATION_METHODS = new Set(['POST', 'PUT', 'PATCH', 'DELETE']);

/**
 * Extract the CSRF token from a fetch Response's X-CSRF-Token header.
 * Returns null if the header is absent.
 */
export function extractCsrfToken(response: Response): string | null {
  return response.headers.get('X-CSRF-Token');
}

/**
 * Inject the CSRF token header into a Headers instance for mutation requests.
 *
 * No-ops for safe methods (GET/HEAD/OPTIONS) or when no token is available.
 */
export function injectCsrfToken(headers: Headers, method: string): void {
  if (!MUTATION_METHODS.has(method.toUpperCase())) return;
  const token = getCsrfToken();
  if (token) {
    headers.set('X-CSRF-Token', token);
  }
}
