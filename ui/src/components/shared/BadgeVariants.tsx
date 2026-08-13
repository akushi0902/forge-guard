/**
 * ForgeGuard severity badges.
 *
 * Maps FindingSeverity values to color-coded Mantine badges with a non-color
 * text label indicator for color-blind accessibility (WCAG 1.4.1).
 */

import { Badge, type BadgeProps } from '@mantine/core';
import { forwardRef } from 'react';
import { type FindingSeverity } from '@/types';

export interface SeverityBadgeProps extends Omit<BadgeProps, 'color' | 'children'> {
  severity: FindingSeverity;
}

const SEVERITY_CONFIG: Record<
  FindingSeverity,
  { color: string; label: string }
> = {
  critical: { color: 'danger', label: 'Critical' },
  high: { color: 'danger', label: 'High' },
  medium: { color: 'warning', label: 'Medium' },
  low: { color: 'info', label: 'Low' },
  info: { color: 'neutral', label: 'Info' },
};

/**
 * Color-coded severity badge with text label for accessibility.
 *
 * @example
 * <SeverityBadge severity="critical" />
 * <SeverityBadge severity="medium" size="lg" />
 */
export const SeverityBadge = forwardRef<HTMLDivElement, SeverityBadgeProps>(
  ({ severity, ...rest }, ref) => {
    const { color, label } = SEVERITY_CONFIG[severity];
    return (
      <Badge ref={ref} color={color} {...rest}>
        {label}
      </Badge>
    );
  },
);

SeverityBadge.displayName = 'SeverityBadge';

// ---------------------------------------------------------------------------
// Generic status badge (for non-severity contexts)
// ---------------------------------------------------------------------------

export type StatusVariant = 'success' | 'warning' | 'error' | 'info' | 'neutral';

export interface StatusBadgeProps extends Omit<BadgeProps, 'color'> {
  status: StatusVariant;
}

const STATUS_COLOR: Record<StatusVariant, string> = {
  success: 'success',
  warning: 'warning',
  error: 'danger',
  info: 'info',
  neutral: 'neutral',
};

export const StatusBadge = forwardRef<HTMLDivElement, StatusBadgeProps>(
  ({ status, ...rest }, ref) => (
    <Badge ref={ref} color={STATUS_COLOR[status]} {...rest} />
  ),
);

StatusBadge.displayName = 'StatusBadge';
