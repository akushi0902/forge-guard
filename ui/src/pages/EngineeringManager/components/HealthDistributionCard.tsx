import { type JSX } from 'react';
import { Card, Group, Progress, Stack, Text, Title } from '@mantine/core';

import { type ServiceWithMetrics } from '@/types/api';

interface Bucket {
  label: string;
  color: string;
  count: number;
}

function bucketServices(services: ServiceWithMetrics[]): Bucket[] {
  const scored = services.filter((s) => s.health_score != null);
  const buckets: Bucket[] = [
    { label: '85–100 Healthy',  color: 'green',  count: 0 },
    { label: '70–84 Good',      color: 'teal',   count: 0 },
    { label: '50–69 Warning',   color: 'yellow', count: 0 },
    { label: '0–49 Critical',   color: 'red',    count: 0 },
  ];
  for (const s of scored) {
    const score = s.health_score ?? 0;
    if (score >= 85)      buckets[0]!.count++;
    else if (score >= 70) buckets[1]!.count++;
    else if (score >= 50) buckets[2]!.count++;
    else                  buckets[3]!.count++;
  }
  return buckets;
}

export interface HealthDistributionCardProps {
  services: ServiceWithMetrics[];
}

export function HealthDistributionCard({ services }: HealthDistributionCardProps): JSX.Element {
  const buckets = bucketServices(services);
  const total = buckets.reduce((s, b) => s + b.count, 0);

  return (
    <Card withBorder data-testid="health-distribution-card">
      <Stack gap="md">
        <Title order={4}>Health Score Distribution</Title>

        {total === 0 ? (
          <Text c="dimmed" size="sm">No evaluated services.</Text>
        ) : (
          <>
            <Progress.Root
              size={20}
              radius="sm"
              aria-label="Health score distribution across all services"
            >
              {buckets
                .filter((b) => b.count > 0)
                .map((b) => (
                  <Progress.Section
                    key={b.label}
                    value={(b.count / total) * 100}
                    color={b.color}
                    aria-label={`${b.label}: ${b.count} services`}
                  />
                ))}
            </Progress.Root>

            <Group gap="lg" wrap="wrap" data-testid="distribution-legend">
              {buckets.map((b) => (
                <Group key={b.label} gap={6}>
                  <div
                    style={{
                      width: 12,
                      height: 12,
                      borderRadius: 2,
                      backgroundColor: `var(--mantine-color-${b.color}-6)`,
                    }}
                    aria-hidden="true"
                  />
                  <Text size="sm">
                    {b.label}: <strong>{b.count}</strong>
                  </Text>
                </Group>
              ))}
            </Group>
          </>
        )}
      </Stack>
    </Card>
  );
}
