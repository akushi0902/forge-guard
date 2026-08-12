import { type JSX } from 'react';
import { SimpleGrid } from '@mantine/core';

import { type ThresholdStatus } from '@/constants/healthThresholds';
import { StatusCard } from './StatusCard';

export interface StatusMetric {
  title: string;
  value: string;
  unit?: string;
  status: ThresholdStatus;
  description?: string;
}

export interface StatusGridProps {
  metrics: StatusMetric[];
}

export function StatusGrid({ metrics }: StatusGridProps): JSX.Element {
  return (
    <SimpleGrid cols={{ base: 1, sm: 2, lg: 4 }} spacing="md" data-testid="status-grid">
      {metrics.map((metric) => (
        <StatusCard key={metric.title} {...metric} />
      ))}
    </SimpleGrid>
  );
}
