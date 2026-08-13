/**
 * RemediationEmptyState — shown when no remediation items exist.
 * Satisfies AC-4 of WO-085.
 */

import { type JSX } from 'react';
import { EmptyState } from '@/components/common/EmptyState';
import { EmptyRemediation } from '@/assets/illustrations/EmptyRemediation';

export interface RemediationEmptyStateProps {
  /** Called when the user clicks 'View Findings'. */
  onViewFindings: () => void;
}

const STEPS = [
  { label: 'Generate findings via evaluation', description: 'Policy evaluations produce findings that require remediation.' },
  { label: 'Review AI recommendations', description: 'ForgeGuard provides AI-generated remediation guidance for each finding.' },
  { label: 'Fix, re-evaluate, or request exception', description: 'Apply the fix, trigger a re-evaluation, and watch your Health Score improve.' },
];

export function RemediationEmptyState({ onViewFindings }: RemediationEmptyStateProps): JSX.Element {
  return (
    <EmptyState
      illustration={<EmptyRemediation />}
      title="No Remediation Items"
      description="There are no open remediation items at the moment. Remediation items are created when findings require action — run a policy evaluation to get started."
      steps={STEPS}
      ctaLabel="View Findings"
      ctaAction={onViewFindings}
      testId="remediation-empty-state"
    />
  );
}
