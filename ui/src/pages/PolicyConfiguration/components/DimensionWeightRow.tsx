import { type JSX } from 'react';
import { Group, NumberInput, Slider, Text } from '@mantine/core';

import { PolicyDimension } from '@/types/api';

const DIMENSION_LABELS: Record<PolicyDimension, string> = {
  [PolicyDimension.CodeQuality]: 'Code Quality',
  [PolicyDimension.TestCoverage]: 'Test Coverage',
  [PolicyDimension.Security]: 'Security',
  [PolicyDimension.Documentation]: 'Documentation',
  [PolicyDimension.OperationsReadiness]: 'Operations Readiness',
};

export interface DimensionWeightRowProps {
  dimension: PolicyDimension;
  weight: number;
  onChange: (dimension: PolicyDimension, weight: number) => void;
}

export function DimensionWeightRow({
  dimension,
  weight,
  onChange,
}: DimensionWeightRowProps): JSX.Element {
  const label = DIMENSION_LABELS[dimension] ?? dimension;

  return (
    <Group gap="md" align="center" data-testid={`dimension-row-${dimension}`}>
      <Text size="sm" fw={500} style={{ width: 180, flexShrink: 0 }}>
        {label}
      </Text>
      <Slider
        value={weight}
        onChange={(v) => onChange(dimension, v)}
        min={0}
        max={100}
        step={1}
        style={{ flex: 1 }}
        aria-label={`${label} weight`}
        data-testid={`slider-${dimension}`}
      />
      <NumberInput
        value={weight}
        onChange={(v) => onChange(dimension, Number(v) || 0)}
        min={0}
        max={100}
        step={1}
        suffix="%"
        style={{ width: 90 }}
        aria-label={`${label} weight input`}
        data-testid={`input-${dimension}`}
      />
    </Group>
  );
}
