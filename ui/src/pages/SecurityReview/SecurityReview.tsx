/**
 * SecurityReview page — Security Reviewer persona dashboard (WO-077).
 *
 * Displays:
 *   1. CriticalEscalationAlert — prominent banner when unresolved critical findings exist
 *   2. KPIGrid                 — four summary cards (critical, high, blocked, exceptions)
 *   3. PendingEscalationsCard  — escalated release assessments with Block/Override actions
 *   4. SecurityFindingsTable   — sortable/filterable security findings table
 *
 * RBAC: Page is route-guarded by the release.block permission. All mutation
 * actions are additionally gated client-side and enforced server-side.
 */

import { type JSX, useState } from 'react';
import {
  Alert,
  Button,
  Container,
  Group,
  Select,
  Skeleton,
  Stack,
  Text,
  Title,
} from '@mantine/core';

import { useSecurityFindings, usePendingEscalations, usePendingExceptions } from '@/hooks/api/useSecurityFindings';
import { CriticalEscalationAlert } from './components/CriticalEscalationAlert';
import { KPIGrid } from './components/KPIGrid';
import { PendingEscalationsCard } from './components/PendingEscalationsCard';
import { SecurityFindingsTable } from './components/SecurityFindingsTable';

// ---------------------------------------------------------------------------
// Loading skeleton
// ---------------------------------------------------------------------------

function SecurityReviewSkeleton(): JSX.Element {
  return (
    <Stack gap="lg" data-testid="security-review-skeleton">
      <Skeleton height={60} radius="md" />
      <Group>
        {Array.from({ length: 4 }).map((_, i) => (
          <Skeleton key={i} height={100} style={{ flex: 1 }} radius="md" />
        ))}
      </Group>
      <Skeleton height={200} radius="md" />
      <Skeleton height={300} radius="md" />
    </Stack>
  );
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------

export function SecurityReview(): JSX.Element {
  const [severityFilter, setSeverityFilter] = useState<string>('critical,high');
  const [statusFilter, setStatusFilter] = useState<string>('');

  const findingsQuery = useSecurityFindings({
    severity: severityFilter,
    status: statusFilter || undefined,
  });
  const escalationsQuery = usePendingEscalations();
  const exceptionsQuery = usePendingExceptions();

  const isLoading =
    findingsQuery.isLoading || escalationsQuery.isLoading || exceptionsQuery.isLoading;
  const hasError =
    findingsQuery.isError || escalationsQuery.isError || exceptionsQuery.isError;

  const findings = findingsQuery.data?.items ?? [];
  const escalations = escalationsQuery.data?.items ?? [];
  const exceptions = exceptionsQuery.data?.items ?? [];

  const criticalFindings = findings.filter(
    (f) => f.severity === 'critical' && f.status !== 'resolved' && f.status !== 'excepted',
  );

  return (
    <Container size="xl">
      <Stack gap="lg">
        {/* Page header */}
        <Group justify="space-between" align="flex-start" wrap="wrap">
          <div>
            <Title order={2} data-testid="security-review-title">
              Security Review
            </Title>
            <Text c="dimmed" size="sm">
              Manage critical security escalations and exercise block authority on
              releases with security violations.
            </Text>
          </div>
        </Group>

        {/* Loading state */}
        {isLoading && <SecurityReviewSkeleton />}

        {/* Error state */}
        {!isLoading && hasError && (
          <Alert
            color="red"
            title="Unable to load security data"
            data-testid="security-review-error"
          >
            <Stack gap="xs">
              <Text size="sm">
                Failed to fetch security findings. Check your connection and try again.
              </Text>
              <Button
                variant="outline"
                color="red"
                size="xs"
                onClick={() => {
                  void findingsQuery.refetch();
                  void escalationsQuery.refetch();
                  void exceptionsQuery.refetch();
                }}
                data-testid="security-retry-btn"
                style={{ alignSelf: 'flex-start' }}
              >
                Retry
              </Button>
            </Stack>
          </Alert>
        )}

        {!isLoading && !hasError && (
          <>
            {/* Critical escalation alert banner */}
            <CriticalEscalationAlert criticalCount={criticalFindings.length} />

            {/* KPI summary cards */}
            <KPIGrid
              findings={findings}
              escalations={escalations}
              exceptions={exceptions}
              isLoading={false}
            />

            {/* Pending escalations */}
            <PendingEscalationsCard
              escalations={escalations}
              isLoading={escalationsQuery.isLoading}
            />

            {/* Findings table filters */}
            <Stack gap="sm">
              <Title order={4} data-testid="findings-section-title">
                Security Findings
              </Title>
              <Group gap="sm" wrap="wrap">
                <Select
                  label="Severity"
                  value={severityFilter}
                  onChange={(v) => setSeverityFilter(v ?? 'critical,high')}
                  data={[
                    { value: 'critical,high', label: 'Critical + High' },
                    { value: 'critical', label: 'Critical only' },
                    { value: 'high', label: 'High only' },
                    { value: 'critical,high,medium,low', label: 'All severities' },
                  ]}
                  size="sm"
                  style={{ width: 200 }}
                  data-testid="severity-filter"
                  aria-label="Filter by severity"
                />
                <Select
                  label="Status"
                  value={statusFilter}
                  onChange={(v) => setStatusFilter(v ?? '')}
                  data={[
                    { value: '', label: 'All statuses' },
                    { value: 'open', label: 'Open' },
                    { value: 'in_progress', label: 'In progress' },
                    { value: 'resolved', label: 'Resolved' },
                    { value: 'excepted', label: 'Excepted' },
                  ]}
                  size="sm"
                  style={{ width: 180 }}
                  data-testid="status-filter"
                  aria-label="Filter by status"
                />
              </Group>

              {/* Empty state when no findings at all */}
              {findings.length === 0 && !findingsQuery.isLoading && (
                <Stack align="center" gap="xs" py="xl" data-testid="security-empty-state">
                  <Text size="xl">🔒</Text>
                  <Text fw={600} size="md">
                    No security findings detected
                  </Text>
                  <Text size="sm" c="dimmed" ta="center" maw={480}>
                    No security findings matching your filters have been detected across your
                    services. Findings auto-populate when policy evaluations identify security
                    violations. Keep your services healthy by reviewing engineering standards
                    regularly.
                  </Text>
                </Stack>
              )}

              {/* Security findings table */}
              <SecurityFindingsTable
                findings={findings}
                isLoading={findingsQuery.isLoading}
              />
            </Stack>
          </>
        )}
      </Stack>
    </Container>
  );
}
