/**
 * ServiceHealthEmptyState — shown when a service has no completed evaluations.
 * Satisfies AC-1 of WO-085.
 */

import { type JSX } from 'react';
import { EmptyState } from '@/components/common/EmptyState';
import { EmptyEvaluation } from '@/assets/illustrations/EmptyEvaluation';

export interface ServiceHealthEmptyStateProps {
  /** Called when the user clicks 'Run First Evaluation'. */
  onRunEvaluation: () => void;
}

const STEPS = [
  { label: 'Register your service', description: 'Add your service to the ForgeGuard catalog.' },
  { label: 'Configure policies', description: 'Choose which engineering policies apply to your service.' },
  { label: 'Run first evaluation', description: 'Trigger an evaluation to generate your first Health Score.' },
];

export function ServiceHealthEmptyState({ onRunEvaluation }: ServiceHealthEmptyStateProps): JSX.Element {
  return (
    <EmptyState
      illustration={<EmptyEvaluation />}
      title="No Evaluations Yet"
      description="Your service hasn't been evaluated against any engineering policies. Run your first evaluation to see your Health Score and findings."
      steps={STEPS}
      ctaLabel="Run First Evaluation"
      ctaAction={onRunEvaluation}
      testId="service-health-empty-state"
    />
  );
}
