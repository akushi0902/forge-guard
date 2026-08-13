/**
 * Service Health page — shows per-service health evaluation results.
 * Renders ServiceHealthEmptyState when no evaluations exist (WO-085 AC-1).
 */
import { type JSX } from 'react';
import { Stack, Title } from '@mantine/core';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { useServiceScores } from '@/hooks/api/useScores';
import { ServiceHealthEmptyState } from '@/components/empty-states/ServiceHealthEmptyState';

export function HealthPage(): JSX.Element {
  const [searchParams] = useSearchParams();
  const serviceId = searchParams.get('serviceId') ?? '';
  const navigate = useNavigate();

  const scoreQuery = useServiceScores(serviceId);
  const hasNoData = Boolean(serviceId) && !scoreQuery.isLoading && !scoreQuery.isError && !scoreQuery.data;

  return (
    <Stack gap="md">
      <Title order={2}>Service Health</Title>

      {hasNoData && (
        <ServiceHealthEmptyState
          onRunEvaluation={() => void navigate('/releases/new')}
        />
      )}
    </Stack>
  );
}
