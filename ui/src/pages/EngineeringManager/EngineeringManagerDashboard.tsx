import { type JSX } from 'react';
import { useSearchParams } from 'react-router-dom';
import {
  Alert,
  Badge,
  Button,
  Container,
  Group,
  SimpleGrid,
  Skeleton,
  Stack,
  Text,
  Title,
} from '@mantine/core';

import { useServicesWithScores } from '@/hooks/api/useServicesWithScores';
import { useAssessmentTrends } from '@/hooks/api/useAssessmentTrends';
import { KPIGrid } from './components/KPIGrid';
import { HealthDistributionCard } from './components/HealthDistributionCard';
import { TrendChartCard } from './components/TrendChartCard';
import { ResolutionRateCard } from './components/ResolutionRateCard';
import { ServicesTableCard } from './components/ServicesTableCard';

// ---------------------------------------------------------------------------
// Skeleton loading layout
// ---------------------------------------------------------------------------

function DashboardSkeleton(): JSX.Element {
  return (
    <Stack gap="lg" data-testid="manager-dashboard-skeleton">
      <SimpleGrid cols={{ base: 1, xs: 2, md: 4 }} spacing="md">
        {Array.from({ length: 4 }).map((_, i) => (
          <Skeleton key={i} height={100} radius="md" />
        ))}
      </SimpleGrid>
      <Skeleton height={60} radius="md" />
      <SimpleGrid cols={{ base: 1, lg: 2 }} spacing="md">
        <Skeleton height={260} radius="md" />
        <Skeleton height={260} radius="md" />
      </SimpleGrid>
      <Skeleton height={300} radius="md" />
    </Stack>
  );
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------

export function EngineeringManagerDashboard(): JSX.Element {
  const [searchParams, setSearchParams] = useSearchParams();
  const selectedTeam = searchParams.get('team') ?? '';

  const servicesQuery = useServicesWithScores(selectedTeam || undefined);
  const trendsQuery = useAssessmentTrends(6);

  function handleTeamChange(team: string) {
    if (team) {
      setSearchParams({ team });
    } else {
      setSearchParams({});
    }
  }

  const isLoading = servicesQuery.isLoading || trendsQuery.isLoading;
  const hasError = servicesQuery.isError;

  const services = servicesQuery.data?.items ?? [];
  const lastUpdated = servicesQuery.dataUpdatedAt
    ? new Date(servicesQuery.dataUpdatedAt).toLocaleTimeString()
    : null;

  return (
    <Container size="xl">
      <Stack gap="lg">
        {/* Page header */}
        <Group justify="space-between" align="flex-start" wrap="wrap">
          <div>
            <Title order={2} data-testid="manager-dashboard-title">
              Engineering Manager Dashboard
            </Title>
            <Text c="dimmed" size="sm">
              Portfolio compliance overview — auto-refreshes every 60 seconds
            </Text>
          </div>
          {lastUpdated && (
            <Badge
              color="gray"
              variant="outline"
              size="md"
              data-testid="last-updated-badge"
            >
              Updated: {lastUpdated}
            </Badge>
          )}
        </Group>

        {/* Loading state */}
        {isLoading && <DashboardSkeleton />}

        {/* Error state */}
        {!isLoading && hasError && (
          <Alert
            color="red"
            title="Unable to load dashboard"
            data-testid="manager-dashboard-error"
          >
            <Stack gap="xs">
              <Text size="sm">
                Failed to load service data. Check your connection and try again.
              </Text>
              <Button
                variant="outline"
                color="red"
                size="xs"
                onClick={() => void servicesQuery.refetch()}
                data-testid="manager-retry-btn"
                style={{ alignSelf: 'flex-start' }}
              >
                Retry
              </Button>
            </Stack>
          </Alert>
        )}

        {/* Dashboard content */}
        {!isLoading && !hasError && (
          <>
            {/* KPI summary cards */}
            <KPIGrid services={services} />

            {/* Health score distribution */}
            <HealthDistributionCard services={services} />

            {/* Trend charts */}
            <SimpleGrid cols={{ base: 1, lg: 2 }} spacing="md">
              <TrendChartCard
                data={trendsQuery.data?.trends}
                isLoading={trendsQuery.isLoading}
              />
              <ResolutionRateCard
                data={trendsQuery.data?.resolution_rates}
                isLoading={trendsQuery.isLoading}
              />
            </SimpleGrid>

            {/* Services sortable table */}
            <ServicesTableCard
              services={services}
              isLoading={servicesQuery.isLoading}
              selectedTeam={selectedTeam}
              onTeamChange={handleTeamChange}
            />
          </>
        )}
      </Stack>
    </Container>
  );
}
