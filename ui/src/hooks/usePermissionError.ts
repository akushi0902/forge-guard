/**
 * usePermissionError — React hook for formatting permission denied responses.
 *
 * Accepts a raw PermissionDeniedResponse from the backend and returns
 * display-ready strings for rendering in PermissionDeniedAlert or similar UI.
 */

import {
  formatPermissionError,
  type FormattedPermissionError,
} from '@/utils/permissionMap';
import type { PermissionDeniedResponse } from '@/types/api-errors';

export type { FormattedPermissionError };

/**
 * Format a backend 403 error payload into display-ready strings.
 *
 * This hook is a thin wrapper around formatPermissionError() that follows
 * React hook naming conventions for consistent usage in components.
 *
 * @param error - The structured 403 response from the backend.
 * @returns      - Formatted strings ready for display.
 *
 * @example
 * const { permissionLabel, roleList, actionGuidance } = usePermissionError(error);
 */
export function usePermissionError(
  error: PermissionDeniedResponse,
): FormattedPermissionError {
  return formatPermissionError(error);
}
