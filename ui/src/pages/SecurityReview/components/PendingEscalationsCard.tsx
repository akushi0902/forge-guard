/**
 * PendingEscalationsCard — section displaying all escalated release assessments.
 *
 * Renders a grid of EscalationCard components. Shows a helpful empty state when
 * no escalations are pending, and a skeleton while data loads.
 */

import { Card, SimpleGrid, Skeleton, Stack, Text, Title } from '@mantine/core';
import { type JSX } from 'react';

import { EscalationCard } from './EscalationCard';
import { type EscalatedRelease } from '@/hooks/api/useSecurityFindings';

export interface PendingEscalationsCardProps {
  escalations: EscalatedRelease[];
  isLoading: boolean;
}

export function PendingEscalationsCard({
  escalations,
  isLoading,
}: PendingEscalationsCardProps): JSX.Element {
  return (
    <Stack gap="sm">
      <Title order={4} data-testid="pending-escalations-title">
        Pending Escalations
      </Title>

      {/* Loading skeletons */}
      {isLoading && (
        <SimpleGrid cols={{ base: 1, md: 2 }} spacing="md" data-testid="escalations-skeleton">
          {Array.from({ length: 2 }).map((_, i) => (
            <Skeleton key={i} height={160} radius="md" />
          ))}
        </SimpleGrid>
      )}

      {/* Empty state */}
      {!isLoading && escalations.length === 0 && (
        <Card withBorder radius="md" p="lg" data-testid="escalations-empty">
          <Stack gap="xs" align="center">
            <Text size="lg">✅</Text>
            <Text fw={500} size="sm">
              No pending escalations
            </Text>
            <Text size="sm" c="dimmed" ta="center">
              All release assessments are within acceptable security thresholds.
            </Text>
          </Stack>
        </Card>
      )}

      {/* Escalation cards */}
      {!isLoading && escalations.length > 0 && (
        <SimpleGrid cols={{ base: 1, md: 2 }} spacing="md">
          {escalations.map((escalation) => (
            <EscalationCard key={escalation.id} escalation={escalation} />
          ))}
        </SimpleGrid>
      )}
    </Stack>
  );
}
