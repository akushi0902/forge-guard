/**
 * KPIGrid — four summary cards for the Security Review dashboard.
 *
 * Cards:
 *   1. Critical Findings count
 *   2. High Findings count
 *   3. Blocked Releases count (escalations with an existing block decision)
 *   4. Pending Exceptions count
 */

import { type JSX } from 'react';
import { SimpleGrid } from '@mantine/core';

import { KPICard } from '@/components/shared/StatCard';
import { type SecurityFinding, type EscalatedRelease, type PendingException } from '@/hooks/api/useSecurityFindings';

export interface KPIGridProps {
  findings: SecurityFinding[];
  escalations: EscalatedRelease[];
  exceptions: PendingException[];
  isLoading?: boolean;
}

export function KPIGrid({
  findings,
  escalations,
  exceptions,
  isLoading = false,
}: KPIGridProps): JSX.Element {
  const criticalCount = findings.filter(
    (f) => f.severity === 'critical' && f.status !== 'resolved' && f.status !== 'excepted',
  ).length;

  const highCount = findings.filter(
    (f) => f.severity === 'high' && f.status !== 'resolved' && f.status !== 'excepted',
  ).length;

  const blockedCount = escalations.filter((e) => e.status === 'blocked').length;
  const pendingExceptionsCount = exceptions.length;

  return (
    <SimpleGrid
      cols={{ base: 1, xs: 2, md: 4 }}
      spacing="md"
      data-testid="security-kpi-grid"
    >
      <KPICard
        title="Critical Findings"
        value={isLoading ? '…' : criticalCount}
        subtitle="Unresolved critical severity"
        style={
          criticalCount > 0
            ? { borderLeft: '4px solid var(--mantine-color-red-6)' }
            : undefined
        }
        data-testid="kpi-critical-count"
      />
      <KPICard
        title="High Findings"
        value={isLoading ? '…' : highCount}
        subtitle="Unresolved high severity"
        style={
          highCount > 0
            ? { borderLeft: '4px solid var(--mantine-color-orange-6)' }
            : undefined
        }
        data-testid="kpi-high-count"
      />
      <KPICard
        title="Blocked Releases"
        value={isLoading ? '…' : blockedCount}
        subtitle="Security-blocked release decisions"
        data-testid="kpi-blocked-releases"
      />
      <KPICard
        title="Pending Exceptions"
        value={isLoading ? '…' : pendingExceptionsCount}
        subtitle="Awaiting Security Reviewer approval"
        style={
          pendingExceptionsCount > 0
            ? { borderLeft: '4px solid var(--mantine-color-yellow-6)' }
            : undefined
        }
        data-testid="kpi-pending-exceptions"
      />
    </SimpleGrid>
  );
}
