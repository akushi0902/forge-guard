/**
 * MockDataBadge — inline indicator for simulated / demo data items.
 *
 * Renders an orange Badge that is visually distinctive and does not
 * use red (error/critical) or green (success/pass). Screen readers
 * announce "Simulated data" via aria-label.
 */

import { type JSX } from 'react';
import { Badge } from '@mantine/core';

export interface MockDataBadgeProps {
  /**
   * Badge label text.
   * @default 'Simulated'
   */
  label?: string;
}

/**
 * Inline demo-data badge for card components.
 *
 * @example
 * <MockDataBadge />
 * <MockDataBadge label="Demo Mode" />
 */
export function MockDataBadge({ label = 'Simulated' }: MockDataBadgeProps): JSX.Element {
  return (
    <Badge
      color="orange"
      variant="light"
      size="sm"
      aria-label="Simulated data"
      leftSection={
        <span aria-hidden="true" style={{ fontSize: 10 }}>
          🧪
        </span>
      }
      data-testid="mock-data-badge"
    >
      {label}
    </Badge>
  );
}
