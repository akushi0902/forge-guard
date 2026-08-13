/**
 * Permission denied interceptor for the ForgeGuard API client.
 *
 * Parses structured 403 Forbidden response bodies and shows a Mantine
 * notification with human-readable permission denial details.
 *
 * Deduplication: uses the permission slug as the notification ID so rapid
 * consecutive 403s for the same permission update a single notification
 * rather than flooding the user with duplicates.
 *
 * Usage: called internally by apiClient — consumers do not need to call
 * this directly; 403 handling is automatic.
 */

import { notifications } from '@mantine/notifications';

import {
  isPermissionDeniedResponse,
  type PermissionDeniedResponse,
} from '@/types/api-errors';
import {
  formatPermissionError,
  FALLBACK_PERMISSION_MESSAGE,
} from '@/utils/permissionMap';

/** Auto-dismiss delay for permission denied notifications (ms). */
export const PERMISSION_NOTIFICATION_DURATION_MS = 10_000;

/**
 * Show a Mantine notification for a 403 Permission Denied response.
 *
 * If `rawBody` conforms to PermissionDeniedResponse, the notification shows
 * the specific permission, the roles that hold it, and contact guidance.
 * Otherwise it shows a safe generic fallback message.
 *
 * @param rawBody - The parsed JSON body from a 403 response (may be unknown).
 */
export function showPermissionDeniedNotification(rawBody: unknown): void {
  if (isPermissionDeniedResponse(rawBody)) {
    showStructuredNotification(rawBody);
  } else {
    showFallbackNotification();
  }
}

// ---------------------------------------------------------------------------
// Internal helpers
// ---------------------------------------------------------------------------

function showStructuredNotification(error: PermissionDeniedResponse): void {
  const { permissionLabel, roleList, actionGuidance } = formatPermissionError(error);

  const roleText = roleList
    ? `Required by: ${roleList}.`
    : '';

  const message = [
    `This action requires the "${permissionLabel}" permission.`,
    roleText,
    actionGuidance,
  ]
    .filter(Boolean)
    .join(' ');

  notifications.show({
    // Deduplicate: identical permission slug → update existing notification
    id: `permission-denied:${error.permission}`,
    title: 'Permission Denied',
    message,
    color: 'red',
    autoClose: PERMISSION_NOTIFICATION_DURATION_MS,
    withCloseButton: true,
  });
}

function showFallbackNotification(): void {
  notifications.show({
    id: 'permission-denied:unknown',
    title: 'Permission Denied',
    message: FALLBACK_PERMISSION_MESSAGE,
    color: 'red',
    autoClose: PERMISSION_NOTIFICATION_DURATION_MS,
    withCloseButton: true,
  });
}
