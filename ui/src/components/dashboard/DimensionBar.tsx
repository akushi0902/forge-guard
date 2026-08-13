import { Group, Progress, Text } from '@mantine/core';

const DIMENSION_LABELS: Record<string, string> = {
  code_quality:         'Code Quality',
  test_coverage:        'Test Coverage',
  security:             'Security',
  documentation:        'Documentation',
  operations_readiness: 'Operations Readiness',
};

function scoreColor(score: number): string {
  if (score >= 70) return 'green';
  if (score >= 50) return 'yellow';
  return 'red';
}

export interface DimensionBarProps {
  /** Raw dimension key from the API (e.g. 'code_quality'). */
  name: string;
  /** Score in the range [0, 100]. Clamped if out of range. */
  score: number;
  /** Relative weight of this dimension (0–1). Displayed for context only. */
  weight?: number;
}

/**
 * Horizontal labelled progress bar for a single health-score dimension.
 *
 * @example
 * <DimensionBar name="security" score={87} weight={0.3} />
 */
export function DimensionBar({ name, score, weight: _weight }: DimensionBarProps) {
  const label = DIMENSION_LABELS[name] ?? name.replace(/_/g, ' ');
  const clampedScore = Math.max(0, Math.min(100, isNaN(score) ? 0 : score));
  const color = scoreColor(clampedScore);

  return (
    <div aria-label={`${label}: ${Math.round(clampedScore)} out of 100`}>
      <Group justify="space-between" mb={4}>
        <Text size="sm" fw={500}>
          {label}
        </Text>
        <Text size="sm" fw={600} c={color}>
          {Math.round(clampedScore)}%
        </Text>
      </Group>
      <Progress
        value={clampedScore}
        color={color}
        size="sm"
        radius="sm"
        aria-label={`${label} progress bar`}
      />
    </div>
  );
}
