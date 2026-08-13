import { Card, Group, Stack, Text } from '@mantine/core';
import { type ServiceScore } from '@/types/api';
import { ScoreRing } from '@/components/shared';
import { DimensionBar } from './DimensionBar';

export interface HealthScoreCardProps {
  score: ServiceScore;
}

/**
 * Map an overall health score to a semantic colour per AC-2:
 *   green  ≥ 70
 *   amber  50–69
 *   red    < 50
 *
 * Exported for unit-testing purposes.
 */
export function healthScoreColor(overallScore: number): string {
  if (overallScore >= 70) return 'var(--mantine-color-success-6, #16a34a)';
  if (overallScore >= 50) return 'var(--mantine-color-warning-6, #d97706)';
  return 'var(--mantine-color-danger-6, #dc2626)';
}

/**
 * Card displaying the overall ScoreRing and one DimensionBar per dimension.
 *
 * @example
 * <HealthScoreCard score={scoreData} />
 */
export function HealthScoreCard({ score }: HealthScoreCardProps) {
  return (
    <Card withBorder>
      <Text fw={600} size="lg" mb="md">
        Engineering Health Score
      </Text>
      <Group align="flex-start" gap="xl" wrap="nowrap">
        <Stack align="center" gap={4} style={{ flexShrink: 0 }}>
          <ScoreRing
            score={score.overall_score}
            size={120}
            strokeWidth={10}
            label="Overall health score"
            color={healthScoreColor(score.overall_score)}
          />
          <Text size="xs" c="dimmed">
            Overall
          </Text>
        </Stack>
        <Stack gap="sm" style={{ flex: 1, minWidth: 0 }}>
          {score.dimensions.map((dim) => (
            <DimensionBar
              key={dim.name}
              name={dim.name}
              score={dim.score}
              weight={dim.weight}
            />
          ))}
        </Stack>
      </Group>
    </Card>
  );
}
