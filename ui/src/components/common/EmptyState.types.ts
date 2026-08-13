import { type ReactNode } from 'react';

/** A single onboarding step shown below the description. */
export interface OnboardingStep {
  /** Short step label shown as the list item text. */
  label: string;
  /** Optional longer description shown below the label. */
  description?: string;
}

/** Props for the reusable EmptyState base component. */
export interface EmptyStateProps {
  /** Optional illustration rendered above the title. Should have aria-hidden='true'. */
  illustration?: ReactNode;
  /** Primary heading text. */
  title: string;
  /** Supporting description explaining the empty condition. */
  description: string;
  /** Optional ordered list of onboarding steps. */
  steps?: OnboardingStep[];
  /** Label for the primary call-to-action button. */
  ctaLabel: string;
  /**
   * CTA action. Pass a function for programmatic navigation / mutation,
   * or a string href for direct link navigation.
   */
  ctaAction: (() => void) | string;
  /** Optional icon rendered inside the CTA button. */
  ctaIcon?: ReactNode;
  /** Optional data-testid forwarded to the root element. */
  testId?: string;
}
