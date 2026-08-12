import { SimpleGrid } from '@mantine/core';
import { StatCard } from '@/components/shared';

/** Return a CSS color based on the health-score range. */
function scoreColor(score: number): string {
  if (score >= 70) return 'var(--mantine-color-green-6, #16a34a)';
  if (score >= 50) return 'var(--mantine-color-yellow-6, #d97706)';
  return 'var(--mantine-color-red-6, #dc2626)';
}

/** Simple relative-time formatter — no date-fns dependency required. */
export function formatRelativeTime(isoDate: string | null | undefined): string {
  if (!isoDate) return 'Never';
  const diffMs = Date.now() - new Date(isoDate).getTime();
  if (isNaN(diffMs)) return 'Unknown';
  const mins = Math.floor(diffMs / 60_000);
  if (mins < 1) return 'Just now';
  if (mins < 60) return `${mins} min ago`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  return days === 1 ? 'Yesterday' : `${days} days ago${days > 30 ? ' ⚠' : ''}`;
}

export interface StatsGridProps {
  overallScore: number;
  openFindingsCount: number;
  criticalHighCount: number;
  lastEvaluatedAt: string | null | undefined;
}

/**
 * 2×2 responsive grid of KPI StatCards for the developer dashboard.
 *
 * @example
 * <StatsGrid overallScore={85} openFindingsCount={4} criticalHighCount={2} lastEvaluatedAt="2026-08-11T10:00:00Z" />
 */
export function StatsGrid({
  overallScore,
  openFindingsCount,
  criticalHighCount,
  lastEvaluatedAt,
}: StatsGridProps) {
  const hasCriticalHigh = criticalHighCount > 0;

  return (
    <SimpleGrid cols={{ base: 1, xs: 2 }} spacing="md">
      <StatCard
        title="Health Score"
        value={overallScore}
        subtitle="Overall engineering score"
        style={{ borderLeft: `4px solid ${scoreColor(overallScore)}` }}
      />
      <StatCard
        title="Open Findings"
        value={openFindingsCount}
        subtitle="Active policy violations"
      />
      <StatCard
        title="Critical / High"
        value={criticalHighCount}
        subtitle="Highest-severity findings"
        style={
          hasCriticalHigh
            ? { borderLeft: '4px solid var(--mantine-color-red-6, #dc2626)' }
            : undefined
        }
      />
      <StatCard
        title="Last Evaluation"
        value={formatRelativeTime(lastEvaluatedAt)}
        subtitle="Since last assessment"
      />
    </SimpleGrid>
  );
}
