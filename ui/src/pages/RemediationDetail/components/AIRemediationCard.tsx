/**
 * AIRemediationCard — displays the AI-generated remediation recommendation.
 *
 * Contains:
 *   - ConfidenceMeter (RingProgress, colour-coded by score)
 *   - Low-confidence warning banner (shown when confidence < 50%)
 *   - RemediationSteps (numbered list with optional code blocks)
 *   - Disclaimer that recommendations should be reviewed before implementation
 *
 * Edge cases:
 *   - null recommendation (generating) → loading skeleton
 *   - recommendation 404 → "not available" placeholder with retry
 */

import {
  Alert,
  Card,
  Divider,
  Skeleton,
  Stack,
  Text,
  Title,
} from '@mantine/core';
import type { JSX } from 'react';

import { type FindingRecommendation } from '@/types/api';
import { ConfidenceMeter } from './ConfidenceMeter';
import { RemediationSteps } from './RemediationSteps';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface AIRemediationCardProps {
  recommendation: FindingRecommendation | null | undefined;
  /** True while the recommendation fetch is in-flight. */
  isLoading: boolean;
  /** True when the fetch returned a 404 (not yet generated). */
  isNotFound: boolean;
  /** Callback to retry the recommendation fetch. */
  onRetry?: () => void;
  /** Test id for targeting in tests. */
  'data-testid'?: string;
}

// ---------------------------------------------------------------------------
// Loading skeleton sub-component
// ---------------------------------------------------------------------------

function AIRemediationSkeleton(): JSX.Element {
  return (
    <Stack gap="sm" data-testid="ai-remediation-skeleton">
      <Skeleton height={20} width="60%" />
      <Skeleton height={80} />
      <Skeleton height={16} />
      <Skeleton height={16} />
      <Skeleton height={16} width="70%" />
    </Stack>
  );
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export function AIRemediationCard({
  recommendation,
  isLoading,
  isNotFound,
  onRetry,
  'data-testid': testId,
}: AIRemediationCardProps): JSX.Element {
  // -- Loading state (recommendation still generating) -----------------------
  if (isLoading) {
    return (
      <Card withBorder padding="lg" data-testid={testId ?? 'ai-remediation-card'}>
        <Stack gap="sm">
          <Title order={4}>AI Remediation Recommendation</Title>
          <Text size="sm" c="dimmed" fs="italic">
            Generating recommendation…
          </Text>
          <AIRemediationSkeleton />
        </Stack>
      </Card>
    );
  }

  // -- Not available state (404) ---------------------------------------------
  if (isNotFound || !recommendation) {
    return (
      <Card withBorder padding="lg" data-testid={testId ?? 'ai-remediation-card'}>
        <Stack gap="sm">
          <Title order={4}>AI Remediation Recommendation</Title>
          <Alert
            color="gray"
            title="Recommendation not yet available"
            data-testid="recommendation-not-available"
          >
            <Stack gap="xs">
              <Text size="sm">
                The AI recommendation for this finding is still being generated.
                Check back shortly.
              </Text>
              {onRetry && (
                <Text
                  size="sm"
                  c="blue"
                  style={{ cursor: 'pointer', textDecoration: 'underline' }}
                  onClick={onRetry}
                  data-testid="recommendation-retry-btn"
                >
                  Retry
                </Text>
              )}
            </Stack>
          </Alert>
        </Stack>
      </Card>
    );
  }

  // -- Normal state ----------------------------------------------------------

  // Normalise confidence score to percentage (backend may return 0–1 or 0–100)
  const confidencePct =
    recommendation.confidence_score > 1
      ? recommendation.confidence_score
      : recommendation.confidence_score * 100;

  const isLowConfidence = confidencePct < 50;

  return (
    <Card withBorder padding="lg" data-testid={testId ?? 'ai-remediation-card'}>
      <Stack gap="md">
        <Title order={4}>AI Remediation Recommendation</Title>

        {/* Confidence indicator */}
        <ConfidenceMeter
          score={recommendation.confidence_score}
          data-testid="recommendation-confidence-meter"
        />

        {/* Low-confidence warning banner */}
        {isLowConfidence && (
          <Alert
            color="yellow"
            title="Low confidence recommendation"
            data-testid="low-confidence-warning"
          >
            This recommendation has a confidence score below 50%. Please
            review it carefully and verify it independently with your team
            before implementing it in production.
          </Alert>
        )}

        <Divider />

        {/* Recommendation summary text */}
        <div>
          <Title order={5} mb="xs">
            Summary
          </Title>
          <Text size="sm" data-testid="recommendation-text">
            {recommendation.recommendation_text}
          </Text>
        </div>

        {/* Step-by-step guide */}
        {recommendation.implementation_guide && (
          <div>
            <Title order={5} mb="sm">
              Implementation Steps
            </Title>
            <RemediationSteps
              guide={recommendation.implementation_guide}
              data-testid="remediation-steps"
            />
          </div>
        )}

        <Divider />

        {/* Disclaimer */}
        <Alert
          color="gray"
          variant="outline"
          title="Disclaimer"
          data-testid="ai-disclaimer"
        >
          <Text size="xs">
            AI-generated recommendations are provided as guidance only. They
            should be reviewed by a qualified engineer before implementation.
            ForgeGuard does not guarantee the correctness or completeness of
            AI suggestions.
          </Text>
        </Alert>
      </Stack>
    </Card>
  );
}
