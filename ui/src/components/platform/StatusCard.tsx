import { type JSX } from 'react';
import { Card, Text, Title } from '@mantine/core';

import { type ThresholdStatus, STATUS_COLOR } from '@/constants/healthThresholds';

export interface StatusCardProps {
  title: string;
  value: string;
  unit?: string;
  status: ThresholdStatus;
  description?: string;
}

const CARD_STYLES: Record<ThresholdStatus, { border: string; background: string }> = {
  green:  { border: '2px solid var(--mantine-color-green-6)',  background: 'var(--mantine-color-green-0)'  },
  yellow: { border: '2px solid var(--mantine-color-yellow-6)', background: 'var(--mantine-color-yellow-0)' },
  red:    { border: '2px solid var(--mantine-color-red-6)',    background: 'var(--mantine-color-red-0)'    },
};

export function StatusCard({ title, value, unit, status, description }: StatusCardProps): JSX.Element {
  const cardStyles = CARD_STYLES[status];
  const ariaLabel = `${title}: ${value}${unit ? ` ${unit}` : ''}`;
  const testId = `status-card-${title.toLowerCase().replace(/\s+/g, '-')}`;

  return (
    <Card
      padding="md"
      style={{ border: cardStyles.border, background: cardStyles.background }}
      data-testid={testId}
      aria-label={ariaLabel}
    >
      <Text size="xs" c="dimmed" fw={500} tt="uppercase" mb={4}>
        {title}
      </Text>
      <Title order={2} c={STATUS_COLOR[status]}>
        {value}
        {unit && (
          <Text component="span" size="sm" fw={400} c={STATUS_COLOR[status]}>
            {' '}{unit}
          </Text>
        )}
      </Title>
      {description && (
        <Text size="xs" c="dimmed" mt={4}>
          {description}
        </Text>
      )}
    </Card>
  );
}
