import { Card, Group, Stack, Text } from '@mantine/core';
import { type ServiceScore } from '@/types/api';
import { ScoreRing } from '@/components/shared';
import { DimensionBar } from './DimensionBar';

export interface HealthScoreCardProps {
  score: ServiceScore;
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
