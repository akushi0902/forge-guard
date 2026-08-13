/**
 * PermissionDeniedAlert — inline accessible alert for 403 Permission Denied errors.
 *
 * Renders a Mantine Alert (color='red', variant='light') with an aria-live
 * region so screen readers announce the denial immediately. Suitable for both
 * inline page placement and programmatic display via the notification system.
 *
 * The alert identifies:
 *   - Which permission was required
 *   - Which role(s) hold that permission
 *   - Guidance on how to gain access (contact Platform Admin)
 */

import { Alert, Stack, Text } from '@mantine/core';
import { type JSX } from 'react';

import { usePermissionError } from '@/hooks/usePermissionError';
import type { PermissionDeniedResponse } from '@/types/api-errors';

// ---------------------------------------------------------------------------
// Inline SVG lock icon (no external icon library required)
// ---------------------------------------------------------------------------

function LockIcon(): JSX.Element {
  return (
    <svg
      width="16"
      height="16"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <rect x="3" y="11" width="18" height="11" rx="2" ry="2" />
      <path d="M7 11V7a5 5 0 0 1 10 0v4" />
    </svg>
  );
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export interface PermissionDeniedAlertProps {
  /** Structured 403 error from the backend. */
  error: PermissionDeniedResponse;
  /** Optional handler called when the user dismisses the alert. */
  onClose?: () => void;
}

/**
 * Accessible, dismissible alert for backend 403 Forbidden errors.
 *
 * Uses role='alert' and aria-live='assertive' so screen readers announce
 * the denial immediately when the component is mounted.
 *
 * @example
 * <PermissionDeniedAlert error={permissionError} onClose={() => setError(null)} />
 */
export function PermissionDeniedAlert({
  error,
  onClose,
}: PermissionDeniedAlertProps): JSX.Element {
  const { permissionLabel, permissionDescription, roleList, actionGuidance } =
    usePermissionError(error);

  return (
    <Alert
      color="red"
      variant="light"
      icon={<LockIcon />}
      title="Permission Denied"
      withCloseButton={onClose !== undefined}
      onClose={onClose}
      role="alert"
      aria-live="assertive"
      data-testid="permission-denied-alert"
    >
      <Stack gap="xs">
        <Text size="sm">
          This action requires the <strong>{permissionLabel}</strong> permission.{' '}
          {permissionDescription}
        </Text>
        {roleList && (
          <Text size="sm">
            <strong>Role(s) with this permission:</strong> {roleList}
          </Text>
        )}
        <Text size="sm" c="dimmed">
          {actionGuidance}
        </Text>
      </Stack>
    </Alert>
  );
}
