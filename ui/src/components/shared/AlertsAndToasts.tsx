/**
 * ForgeGuard Alerts and Toast notifications.
 *
 * Alert — inline alert component for in-page messages.
 * showToast — programmatic toast via @mantine/notifications.
 *
 * Auto-dismiss:
 *   success / info → 5 000 ms
 *   warning        → 8 000 ms
 *   error          → persistent (autoClose: false)
 */

import { Alert as MantineAlert, type AlertProps as MantineAlertProps } from '@mantine/core';
import { notifications } from '@mantine/notifications';
import { forwardRef } from 'react';

export type AlertType = 'info' | 'success' | 'warning' | 'error';

export interface AlertProps extends Omit<MantineAlertProps, 'color'> {
  type: AlertType;
}

const ALERT_CONFIG: Record<AlertType, { color: string; autoClose: number | false }> = {
  info: { color: 'info', autoClose: 5_000 },
  success: { color: 'success', autoClose: 5_000 },
  warning: { color: 'warning', autoClose: 8_000 },
  error: { color: 'danger', autoClose: false },
};

/**
 * Inline alert component.
 *
 * @example
 * <Alert type="success" title="Saved">Changes have been saved successfully.</Alert>
 * <Alert type="error" title="Failed">Could not connect to the backend.</Alert>
 */
export const Alert = forwardRef<HTMLDivElement, AlertProps>(
  ({ type, ...rest }, ref) => {
    const { color } = ALERT_CONFIG[type];
    return <MantineAlert ref={ref} color={color} {...rest} />;
  },
);

Alert.displayName = 'Alert';

// ---------------------------------------------------------------------------
// Toast helper
// ---------------------------------------------------------------------------

export interface ShowToastOptions {
  title?: string;
  message: string;
  type: AlertType;
  autoClose?: number | false;
}

/**
 * Programmatically show a toast notification.
 *
 * @example
 * showToast({ type: 'success', message: 'Assessment submitted.' });
 * showToast({ type: 'error', title: 'Connection failed', message: 'Check your network.' });
 */
export function showToast({ title, message, type, autoClose }: ShowToastOptions): void {
  const { color, autoClose: defaultAutoClose } = ALERT_CONFIG[type];
  notifications.show({
    title,
    message,
    color,
    autoClose: autoClose ?? defaultAutoClose,
  });
}
