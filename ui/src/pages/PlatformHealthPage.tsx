/**
 * Operator Platform Health monitoring dashboard (WO-081).
 *
 * Shows four StatusCards (threshold-based), five service health check rows,
 * a Recharts response-time bar chart, and a recent operational logs feed.
 * All data auto-refreshes every 10 seconds via TanStack Query refetchInterval.
 * A stale-data warning banner appears after 3 consecutive refresh failures.
 */

import { type JSX, useEffect, useRef, useState } from 'react';
import {
  Alert,
  Badge,
  Container,
  Group,
  SimpleGrid,
  Stack,
  Text,
  Title,
} from '@mantine/core';

import {
  usePlatformHealthSummary,
  useSystemHealth,
  useReadinessStatus,
  usePlatformMetrics,
  usePlatformLogs,
} from '@/hooks/api/usePlatformHealth';
import { StatusGrid, type StatusMetric } from '@/components/platform/StatusGrid';
import {
  ServiceHealthCard,
  type ServiceHealthRow,
  type ServiceStatus,
} from '@/components/platform/ServiceHealthCard';
import { ResponseTimeChartCard } from '@/components/platform/ResponseTimeChartCard';
import { RecentLogsCard } from '@/components/platform/RecentLogsCard';
import {
  evaluateThreshold,
  HEALTH_THRESHOLDS,
  worstStatus,
  type ThresholdStatus,
} from '@/constants/healthThresholds';

const MAX_FAILURES = 3;

function formatTime(iso: string | null | undefined): string {
  if (!iso) return 'N/A';
  return new Date(iso).toLocaleTimeString();
}

function llmCircuitBreakerToStatus(cbStatus: string): ServiceStatus {
  if (cbStatus === 'closed') return 'up';
  if (cbStatus === 'half-open') return 'degraded';
  if (cbStatus === 'open') return 'down';
  return 'unknown';
}

export function PlatformHealthPage(): JSX.Element {
  const {
    data: health,
    isError: healthError,
    error: healthErrorObj,
    dataUpdatedAt,
  } = usePlatformHealthSummary();
  const { data: system, isError: systemError } = useSystemHealth();
  const { data: ready,  isError: readyError  } = useReadinessStatus();
  const { data: metrics, isLoading: metricsLoading } = usePlatformMetrics();
  const { data: logs,   isLoading: logsLoading   } = usePlatformLogs();

  // Track consecutive failures across all three primary health queries.
  // Each new healthErrorObj reference indicates a new polling cycle failed.
  const consecutiveFailuresRef = useRef(0);
  const [showStaleBanner, setShowStaleBanner] = useState(false);

  useEffect(() => {
    if (healthError && systemError && readyError) {
      consecutiveFailuresRef.current += 1;
      if (consecutiveFailuresRef.current >= MAX_FAILURES) {
        setShowStaleBanner(true);
      }
    } else {
      consecutiveFailuresRef.current = 0;
      if (!healthError && !systemError && !readyError) {
        setShowStaleBanner(false);
      }
    }
    // healthErrorObj changes on each new poll failure even when isError stays true
  }, [healthError, systemError, readyError, healthErrorObj]);

  // -------------------------------------------------------------------------
  // Build StatusGrid metric cards
  // -------------------------------------------------------------------------

  const statusMetrics: StatusMetric[] = [
    {
      title: 'API Success Rate',
      value: health != null ? health.api_success_rate.toFixed(1) : '—',
      unit: '%',
      status: health != null
        ? evaluateThreshold(health.api_success_rate, HEALTH_THRESHOLDS.apiSuccessRate)
        : 'green',
      description: 'Success rate across all API requests',
    },
    {
      title: 'Assessment Completion',
      value: health != null ? health.assessment_completion_rate.toFixed(1) : '—',
      unit: '%',
      status: health != null
        ? evaluateThreshold(health.assessment_completion_rate, HEALTH_THRESHOLDS.assessmentCompletionRate)
        : 'green',
      description: 'Assessment queue completion rate',
    },
    {
      title: 'DB Pool Utilization',
      value: health != null ? (health.db_connection_pool_utilization * 100).toFixed(0) : '—',
      unit: '%',
      status: health != null
        ? evaluateThreshold(health.db_connection_pool_utilization * 100, HEALTH_THRESHOLDS.dbPoolUtilizationPct)
        : 'green',
      description: 'Database connection pool usage',
    },
    {
      title: 'Audit Log Success',
      value: health != null ? health.audit_log_write_success_rate.toFixed(1) : '—',
      unit: '%',
      status: health != null
        ? evaluateThreshold(health.audit_log_write_success_rate, HEALTH_THRESHOLDS.auditLogSuccessRate)
        : 'green',
      description: 'Audit log write success rate',
    },
  ];

  // -------------------------------------------------------------------------
  // Build service health check rows
  // -------------------------------------------------------------------------

  const backendStatus: ServiceStatus = systemError
    ? 'down'
    : system?.status === 'healthy'
      ? 'up'
      : system != null
        ? 'degraded'
        : 'unknown';

  const dbStatus: ServiceStatus = readyError
    ? 'down'
    : ready?.database.status === 'ok'
      ? 'up'
      : ready != null
        ? 'degraded'
        : 'unknown';

  const llmStatus: ServiceStatus = health != null
    ? llmCircuitBreakerToStatus(health.llm_circuit_breaker_status)
    : 'unknown';

  const pipelineStatus: ServiceStatus = health != null
    ? (health.assessment_completion_rate >= 95
        ? 'up'
        : health.assessment_completion_rate >= 80
          ? 'degraded'
          : 'down')
    : 'unknown';

  const serviceRows: ServiceHealthRow[] = [
    {
      name: 'Backend API',
      status: backendStatus,
      lastChecked: formatTime(system?.timestamp),
      detail: system?.version ? `v${system.version}` : undefined,
    },
    {
      name: 'Database',
      status: dbStatus,
      lastChecked: formatTime(health?.timestamp),
      detail: ready != null ? `${ready.database.latency_ms}ms latency` : undefined,
    },
    {
      name: 'Frontend',
      status: 'up',
      lastChecked: formatTime(new Date().toISOString()),
      detail: 'Self-reporting',
    },
    {
      name: 'LLM Provider',
      status: llmStatus,
      lastChecked: formatTime(health?.timestamp),
      detail: health?.llm_circuit_breaker_status,
    },
    {
      name: 'CI/CD Pipeline',
      status: pipelineStatus,
      lastChecked: formatTime(health?.timestamp),
      detail: health != null
        ? `${health.assessment_completion_rate.toFixed(0)}% completion`
        : undefined,
    },
  ];

  // -------------------------------------------------------------------------
  // Derive overall platform status (worst of all checks)
  // -------------------------------------------------------------------------

  const serviceThresholds: ThresholdStatus[] = serviceRows.map((r) =>
    r.status === 'down' ? 'red' : r.status === 'degraded' ? 'yellow' : 'green',
  );
  const overallStatus = worstStatus([
    ...serviceThresholds,
    ...statusMetrics.map((m) => m.status),
  ]);
  const overallColor =
    overallStatus === 'red' ? 'red' : overallStatus === 'yellow' ? 'yellow' : 'green';
  const overallLabel =
    overallStatus === 'red' ? 'Critical' : overallStatus === 'yellow' ? 'Degraded' : 'Healthy';

  const lastRefresh = dataUpdatedAt ? new Date(dataUpdatedAt).toLocaleTimeString() : null;

  return (
    <Container size="xl">
      <Stack gap="lg">
        {/* Page header */}
        <Group justify="space-between" align="flex-start">
          <div>
            <Title order={2}>Platform Health</Title>
            <Text c="dimmed" size="sm">Auto-refreshes every 10 seconds</Text>
          </div>
          <Group gap="sm" align="center">
            <Badge
              color={overallColor}
              size="lg"
              variant="filled"
              data-testid="overall-status-badge"
            >
              {overallLabel}
            </Badge>
            {lastRefresh != null && (
              <Text size="xs" c="dimmed" data-testid="last-refresh-time">
                Last updated: {lastRefresh}
              </Text>
            )}
          </Group>
        </Group>

        {/* Stale data warning */}
        {showStaleBanner && (
          <Alert
            color="orange"
            title="Stale data — unable to reach backend"
            data-testid="stale-data-banner"
          >
            Dashboard data may be outdated. The last {MAX_FAILURES} consecutive refresh
            attempts failed. Check your network connection or reload the page.
          </Alert>
        )}

        {/* Four metric status cards */}
        <StatusGrid metrics={statusMetrics} />

        {/* Service health checks + response time chart */}
        <SimpleGrid cols={{ base: 1, lg: 2 }} spacing="md">
          <ServiceHealthCard rows={serviceRows} lastUpdated={lastRefresh} />
          <ResponseTimeChartCard
            data={metrics?.response_times}
            isLoading={metricsLoading}
          />
        </SimpleGrid>

        {/* Recent operational logs */}
        <RecentLogsCard entries={logs?.entries} isLoading={logsLoading} />
      </Stack>
    </Container>
  );
}
