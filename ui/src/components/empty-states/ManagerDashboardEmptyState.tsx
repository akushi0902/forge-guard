/**
 * ManagerDashboardEmptyState — shown when an Engineering Manager has no onboarded services.
 * Satisfies AC-5 of WO-085.
 */

import { type JSX } from 'react';
import { EmptyState } from '@/components/common/EmptyState';
import { EmptyDashboard } from '@/assets/illustrations/EmptyDashboard';

export interface ManagerDashboardEmptyStateProps {
  /** Called when the user clicks 'Onboard a Service'. */
  onOnboardService: () => void;
}

const STEPS = [
  { label: 'Register your first service', description: 'Add your services to the ForgeGuard catalog to start tracking Engineering Health.' },
  { label: 'Assign teams and policies', description: 'Configure which engineering policies apply to each service and team.' },
  { label: 'Run evaluations to populate metrics', description: 'Once services are evaluated, Health Scores and trends will appear here.' },
];

export function ManagerDashboardEmptyState({ onOnboardService }: ManagerDashboardEmptyStateProps): JSX.Element {
  return (
    <EmptyState
      illustration={<EmptyDashboard />}
      title="No Services Onboarded"
      description="Your Engineering Manager Dashboard is empty because no services have been registered yet. Onboard your first service to start tracking team health scores and trends."
      steps={STEPS}
      ctaLabel="Onboard a Service"
      ctaAction={onOnboardService}
      testId="manager-dashboard-empty-state"
    />
  );
}
