/**
 * FindingsEmptyState — shown when a service has no findings.
 * Satisfies AC-2 of WO-085.
 */

import { type JSX } from 'react';
import { EmptyState } from '@/components/common/EmptyState';
import { EmptyFindings } from '@/assets/illustrations/EmptyFindings';

export interface FindingsEmptyStateProps {
  /** Called when the user clicks the CTA to trigger an evaluation. */
  onTriggerEvaluation: () => void;
}

const STEPS = [
  { label: 'Run a policy evaluation', description: 'Findings are generated when your service is evaluated against configured policies.' },
  { label: 'Review results', description: 'Any policy violations appear here as findings with severity ratings.' },
  { label: 'Remediate and re-evaluate', description: 'Fix the flagged issues and run another evaluation to confirm resolution.' },
];

export function FindingsEmptyState({ onTriggerEvaluation }: FindingsEmptyStateProps): JSX.Element {
  return (
    <EmptyState
      illustration={<EmptyFindings />}
      title="No Findings"
      description="Great news — no findings have been generated for this service yet. Run a policy evaluation to check for any engineering policy violations."
      steps={STEPS}
      ctaLabel="Run Evaluation"
      ctaAction={onTriggerEvaluation}
      testId="findings-empty-state"
    />
  );
}
