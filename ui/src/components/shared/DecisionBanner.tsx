/**
 * DecisionBanner — full-width status banner for release decision outcomes.
 *
 * Maps DecisionOutcome values to colour-coded banners. Each banner includes
 * both a colour fill AND a text label so the component is accessible to
 * colour-blind users (WCAG 1.4.1 Use of Color).
 */

import { Alert, type AlertProps } from '@mantine/core';
import { type DecisionOutcome } from '@/types';

export interface DecisionBannerProps
  extends Omit<AlertProps, 'color' | 'title' | 'children'> {
  decision: DecisionOutcome;
  /** Optional supplementary text. Defaults to the standard outcome description. */
  description?: string;
}

const DECISION_CONFIG: Record<
  DecisionOutcome,
  { color: string; title: string; defaultDescription: string }
> = {
  approve: {
    color: 'success',
    title: 'Approved — Ready to Release',
    defaultDescription:
      'All policy checks passed. This release meets the required engineering standards.',
  },
  conditional_approve: {
    color: 'warning',
    title: 'Conditionally Approved',
    defaultDescription:
      'Release may proceed with the documented conditions addressed within the agreed timeline.',
  },
  block: {
    color: 'danger',
    title: 'Blocked — Do Not Release',
    defaultDescription:
      'Critical policy violations detected. This release must not proceed until findings are resolved.',
  },
  pending: {
    color: 'info',
    title: 'Assessment Pending',
    defaultDescription:
      'The release assessment is in progress. A decision will be available shortly.',
  },
};

/**
 * Color-coded full-width banner for a release decision outcome.
 *
 * @example
 * <DecisionBanner decision="approve" />
 * <DecisionBanner decision="block" description="2 critical security findings." />
 */
export function DecisionBanner({
  decision,
  description,
  ...rest
}: DecisionBannerProps) {
  const config = DECISION_CONFIG[decision];

  return (
    <Alert
      color={config.color}
      title={config.title}
      variant="light"
      radius="md"
      data-decision={decision}
      {...rest}
    >
      {description ?? config.defaultDescription}
    </Alert>
  );
}
