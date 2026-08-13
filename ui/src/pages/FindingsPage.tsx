/**
 * Findings page — lists policy violation findings for a service.
 * Renders FindingsEmptyState when no findings exist (WO-085 AC-2).
 */
import { type JSX } from 'react';
import { Stack, Title } from '@mantine/core';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { useServiceFindings } from '@/hooks/api/useFindings';
import { FindingsEmptyState } from '@/components/empty-states/FindingsEmptyState';

export function FindingsPage(): JSX.Element {
  const [searchParams] = useSearchParams();
  const serviceId = searchParams.get('serviceId') ?? '';
  const navigate = useNavigate();

  const findingsQuery = useServiceFindings(serviceId);
  const hasNoData =
    Boolean(serviceId) &&
    !findingsQuery.isLoading &&
    !findingsQuery.isError &&
    (findingsQuery.data?.items.length ?? 0) === 0;

  return (
    <Stack gap="md">
      <Title order={2}>Findings</Title>

      {hasNoData && (
        <FindingsEmptyState
          onTriggerEvaluation={() => void navigate('/releases/new')}
        />
      )}
    </Stack>
  );
}
