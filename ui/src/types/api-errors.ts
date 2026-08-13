/**
 * TypeScript interfaces for structured API error responses.
 *
 * Defines the 403 Forbidden payload contract expected from the backend
 * RBAC middleware. Keep in sync with the backend ForbiddenErrorResponse model.
 */

/**
 * Structured 403 response body emitted by the backend when a user lacks
 * the permission required to perform an action.
 *
 * Example:
 * {
 *   "error": "forbidden",
 *   "permission": "release.approve",
 *   "required_role": "Tech Lead",
 *   "message": "This action requires the 'release.approve' permission.",
 *   "action": "Contact your Platform Admin for access."
 * }
 */
export interface PermissionDeniedResponse {
  /** Error type identifier, typically "forbidden". */
  error: string;
  /** RBAC permission slug that was denied (e.g. "release.approve"). */
  permission: string;
  /** Role(s) that hold the required permission. May be a string or string[]. */
  required_role: string | string[];
  /** Human-readable message describing the denial. */
  message: string;
  /** Guidance on how the user can gain access. */
  action: string;
}

/**
 * Runtime type guard for PermissionDeniedResponse.
 *
 * Validates all required fields are present and have the correct types.
 * Use this before casting an unknown 403 response body.
 */
export function isPermissionDeniedResponse(
  value: unknown,
): value is PermissionDeniedResponse {
  if (typeof value !== 'object' || value === null) return false;
  const obj = value as Record<string, unknown>;
  return (
    typeof obj.error === 'string' &&
    typeof obj.permission === 'string' &&
    (typeof obj.required_role === 'string' ||
      (Array.isArray(obj.required_role) &&
        obj.required_role.every((r) => typeof r === 'string'))) &&
    typeof obj.message === 'string' &&
    typeof obj.action === 'string'
  );
}
