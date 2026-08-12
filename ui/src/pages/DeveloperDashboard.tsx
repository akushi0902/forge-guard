/**
 * DeveloperDashboard — primary landing page for the Developer persona (WO-072).
 *
 * Displays:
 *   - Service selector (reads / writes `serviceId` URL query param)
 *   - 4 StatCards (Health Score, Open Findings, Critical/High, Last Evaluation)
 *   - HealthScoreCard with ScoreRing and 5 DimensionBars
 *   - FindingsCard with severity filter tabs and findings table
 *   - EmptyStateCard when the service has no evaluations yet
 *   - Skeleton loading state during data fetch
 *   - Error Alert with Retry on API failure
 */

import { type JSX } from 'react';
import {
  Alert,
  Group,
  Select,
  SimpleGrid,
  Skeleton,
  Stack,
  Text,
  Title,
  UnstyledButton,
} from '@mantine/core';
import { useSearchParams } from 'react-router-dom';

import { useService, useServices } from '@/hooks/api/useServices';
import { useServiceScores } from '@/hooks/api/useScores';
import { useServiceFindings } from '@/hooks/api/useFindings';

import { HealthScoreCard } from '@/components/dashboard/HealthScoreCard';
import { StatsGrid } from '@/components/dashboard/StatsGrid';
import { FindingsCard } from '@/components/dashboard/FindingsCard';
import { EmptyStateCard } from '@/components/dashboard/EmptyStateCard';

/**
 * Loading skeleton that matches the dashboard layout dimensions.
 * Rendered while data is fetching.
 */
function DashboardSkeleton(): JSX.Element {
  return (
    <Stack gap="md" data-testid="dashboard-skeleton">
      <SimpleGrid cols={{ base: 1, xs: 2 }} spacing="md">
        <Skeleton height={100} radius="md" />
        <Skeleton height={100} radius="md" />
        <Skeleton height={100} radius="md" />
        <Skeleton height={100} radius="md" />
      </SimpleGrid>
      <Skeleton height={260} radius="md" />
      <Skeleton height={380} radius="md" />
    </Stack>
  );
}

/**
 * Developer Dashboard page component.
 *
 * Service context is stored in the `serviceId` URL query parameter so that
 * the URL is shareable and the browser back-button navigates between services.
 */
export function DeveloperDashboard(): JSX.Element {
  const [searchParams, setSearchParams] = useSearchParams();
  const serviceId = searchParams.get('serviceId') ?? '';

  const servicesQuery = useServices();
  const services = servicesQuery.data?.items ?? [];

  const scoreQuery    = useServiceScores(serviceId);
  const allFindings   = useServiceFindings(serviceId);
  const critFindings  = useServiceFindings(serviceId, { severity: 'critical' });
  const highFindings  = useServiceFindings(serviceId, { severity: 'high' });
  const serviceQuery  = useService(serviceId);

  const handleServiceChange = (id: string | null) => {
    if (id) {
      setSearchParams({ serviceId: id });
    } else {
      setSearchParams({});
    }
  };

  const isLoading =
    Boolean(serviceId) &&
    (scoreQuery.isLoading || allFindings.isLoading);

  const hasError =
    Boolean(serviceId) && !isLoading && scoreQuery.isError;

  const hasNoEvaluations =
    Boolean(serviceId) &&
    !isLoading &&
    !hasError &&
    !scoreQuery.data;

  const hasData =
    Boolean(serviceId) && !isLoading && !hasError && Boolean(scoreQuery.data);

  const openFindingsCount  = allFindings.data?.total_count ?? 0;
  const criticalHighCount  =
    (critFindings.data?.total_count ?? 0) +
    (highFindings.data?.total_count ?? 0);
  const lastEvaluatedAt    = serviceQuery.data?.last_evaluated_at;
  const overallScore       = scoreQuery.data?.overall_score ?? 0;

  const serviceSelectData = services.map((s) => ({
    value: s.id,
    label: s.name,
  }));

  return (
    <Stack gap="lg">
      {/* Header row */}
      <Group justify="space-between" align="flex-end" wrap="wrap">
        <Title order={2}>Developer Dashboard</Title>
        <Select
          placeholder={services.length === 0 ? 'No services registered' : 'Select a service'}
          data={serviceSelectData}
          value={serviceId || null}
          onChange={handleServiceChange}
          searchable
          clearable
          aria-label="Select service"
          style={{ minWidth: 240 }}
          disabled={services.length === 0}
          data-testid="service-selector"
        />
      </Group>

      {/* No service selected */}
      {!serviceId && (
        <Text c="dimmed" data-testid="no-service-prompt">
          Select a service above to view its engineering health score and findings.
        </Text>
      )}

      {/* Loading state */}
      {isLoading && <DashboardSkeleton />}

      {/* Error state */}
      {hasError && (
        <Alert color="red" title="Unable to load dashboard" role="alert" data-testid="dashboard-error">
          Failed to load service data. Check your connection and try again.{' '}
          <UnstyledButton
            onClick={() => void scoreQuery.refetch()}
            style={{ color: 'inherit', textDecoration: 'underline', cursor: 'pointer' }}
            data-testid="retry-btn"
          >
            Retry
          </UnstyledButton>
        </Alert>
      )}

      {/* Empty state — no evaluations yet */}
      {hasNoEvaluations && <EmptyStateCard serviceId={serviceId} />}

      {/* Full dashboard */}
      {hasData && scoreQuery.data && (
        <Stack gap="md">
          <StatsGrid
            overallScore={overallScore}
            openFindingsCount={openFindingsCount}
            criticalHighCount={criticalHighCount}
            lastEvaluatedAt={lastEvaluatedAt}
          />
          <HealthScoreCard score={scoreQuery.data} />
          <FindingsCard serviceId={serviceId} />
        </Stack>
      )}
    </Stack>
  );
}
