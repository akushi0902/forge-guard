import { type JSX } from 'react';
import { SimpleGrid } from '@mantine/core';

import { KPICard } from '@/components/shared/StatCard';
import { type ServiceWithMetrics } from '@/types/api';

export interface KPIGridProps {
  services: ServiceWithMetrics[];
}

function computeKPIs(services: ServiceWithMetrics[]) {
  const scored = services.filter((s) => s.health_score != null);
  const avgScore =
    scored.length > 0
      ? Math.round(scored.reduce((sum, s) => sum + (s.health_score ?? 0), 0) / scored.length)
      : 0;
  const aboveThreshold = scored.filter((s) => (s.health_score ?? 0) >= 70).length;
  const totalCritical = services.reduce((sum, s) => sum + s.critical_findings, 0);
  const withTtr = services.filter((s) => s.avg_ttr_hours != null);
  const avgTtr =
    withTtr.length > 0
      ? Math.round(
          withTtr.reduce((sum, s) => sum + (s.avg_ttr_hours ?? 0), 0) / withTtr.length,
        )
      : null;
  return { avgScore, aboveThreshold, totalCritical, avgTtr };
}

export function KPIGrid({ services }: KPIGridProps): JSX.Element {
  const { avgScore, aboveThreshold, totalCritical, avgTtr } = computeKPIs(services);

  return (
    <SimpleGrid cols={{ base: 1, xs: 2, md: 4 }} spacing="md" data-testid="kpi-grid">
      <KPICard
        title="Avg Health Score"
        value={services.length > 0 ? avgScore : '—'}
        subtitle="Across all services"
        style={{ borderLeft: `4px solid ${avgScore >= 70 ? 'var(--mantine-color-green-6)' : avgScore >= 50 ? 'var(--mantine-color-yellow-6)' : 'var(--mantine-color-red-6)'}` }}
        data-testid="kpi-avg-score"
      />
      <KPICard
        title="Services ≥ 70"
        value={aboveThreshold}
        subtitle={`of ${services.filter((s) => s.health_score != null).length} evaluated`}
        data-testid="kpi-above-threshold"
      />
      <KPICard
        title="Critical Findings"
        value={totalCritical}
        subtitle="Across all services"
        style={totalCritical > 0 ? { borderLeft: '4px solid var(--mantine-color-red-6)' } : undefined}
        data-testid="kpi-critical-findings"
      />
      <KPICard
        title="Avg Time to Remediate"
        value={avgTtr != null ? `${avgTtr}h` : '—'}
        subtitle="Average hours to resolve"
        data-testid="kpi-avg-ttr"
      />
    </SimpleGrid>
  );
}
