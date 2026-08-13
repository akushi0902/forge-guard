/**
 * ReleasesEmptyState — shown when no release assessments exist for a service.
 * Satisfies AC-3 of WO-085.
 */

import { type JSX } from 'react';
import { EmptyState } from '@/components/common/EmptyState';
import { EmptyReleases } from '@/assets/illustrations/EmptyReleases';

export interface ReleasesEmptyStateProps {
  /** Called when the user clicks 'Request Release Assessment'. */
  onRequestAssessment: () => void;
}

const STEPS = [
  { label: 'Select a service and commit', description: 'Choose the service you want to release and provide a commit SHA or PR reference.' },
  { label: 'Submit the assessment request', description: 'ForgeGuard will analyse your change for release risk across multiple dimensions.' },
  { label: 'Review the decision', description: 'The combined Health Score and Risk Score determine an APPROVE, CONDITIONAL, or BLOCK decision.' },
];

export function ReleasesEmptyState({ onRequestAssessment }: ReleasesEmptyStateProps): JSX.Element {
  return (
    <EmptyState
      illustration={<EmptyReleases />}
      title="No Release Assessments"
      description="No release assessments have been requested yet. Submit a release assessment to get an AI-powered risk analysis and combined release decision."
      steps={STEPS}
      ctaLabel="Request Release Assessment"
      ctaAction={onRequestAssessment}
      testId="releases-empty-state"
    />
  );
}
