/**
 * CriticalEscalationAlert — prominent banner for unresolved critical security findings.
 *
 * Renders a high-visibility red Alert when criticalCount > 0.
 * Returns null when there are no critical findings so it takes no space.
 */

import { Alert } from '@mantine/core';
import { type JSX } from 'react';

export interface CriticalEscalationAlertProps {
  /** Number of unresolved critical security findings. */
  criticalCount: number;
}

/**
 * @example
 * <CriticalEscalationAlert criticalCount={3} />
 */
export function CriticalEscalationAlert({
  criticalCount,
}: CriticalEscalationAlertProps): JSX.Element | null {
  if (criticalCount === 0) return null;

  return (
    <Alert
      color="red"
      variant="filled"
      title={`⚠ Critical Security Escalation — ${criticalCount} unresolved critical finding${criticalCount > 1 ? 's' : ''}`}
      data-testid="critical-escalation-alert"
      role="alert"
      aria-live="polite"
    >
      {criticalCount === 1
        ? 'A critical security finding requires immediate review. Block or override the affected release before deployment.'
        : `${criticalCount} critical security findings require immediate review. Block or override the affected releases before deployment.`}
    </Alert>
  );
}
