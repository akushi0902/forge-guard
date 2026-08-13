/**
 * ViolationExplanationCard — displays the AI-generated explanation for a finding
 * and a bulleted list of business impacts.
 *
 * Data sources:
 *   - explanation text: Finding.ai_explanation (or Finding.description fallback)
 *   - business impact: FindingRecommendation.business_impact
 */

import { Card, List, Skeleton, Stack, Text, ThemeIcon, Title } from '@mantine/core';
import type { JSX } from 'react';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface ViolationExplanationCardProps {
  /** AI-generated explanation for the violation. Falls back to description. */
  explanation: string | null;
  /** Business impact text (may contain bullet-separated items). */
  businessImpact: string | null;
  /** Show loading skeleton. */
  isLoading?: boolean;
  /** Test id for targeting in tests. */
  'data-testid'?: string;
}

// ---------------------------------------------------------------------------
// Helper — parse business impact into bullets
// ---------------------------------------------------------------------------

/**
 * Split business impact into individual bullet items.
 * Handles both comma-separated text and newline-separated items.
 */
function parseImpactItems(impact: string): string[] {
  // Try newline-separated first
  const byNewline = impact
    .split(/\n/)
    .map((s) => s.replace(/^[-•*]\s*/, '').trim())
    .filter(Boolean);
  if (byNewline.length > 1) return byNewline;

  // Try period-separated sentences
  const bySentence = impact
    .split(/\.\s+/)
    .map((s) => s.trim())
    .filter((s) => s.length > 0)
    .map((s) => (s.endsWith('.') ? s : `${s}.`));
  if (bySentence.length > 1) return bySentence;

  // Single item
  return [impact];
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function ViolationExplanationCard({
  explanation,
  businessImpact,
  isLoading = false,
  'data-testid': testId,
}: ViolationExplanationCardProps): JSX.Element {
  if (isLoading) {
    return (
      <Card withBorder padding="lg" data-testid={testId ?? 'violation-explanation-card'}>
        <Stack gap="sm">
          <Skeleton height={20} width="40%" />
          <Skeleton height={16} />
          <Skeleton height={16} />
          <Skeleton height={16} width="80%" />
        </Stack>
      </Card>
    );
  }

  const impactItems =
    businessImpact ? parseImpactItems(businessImpact) : [];

  return (
    <Card
      withBorder
      padding="lg"
      data-testid={testId ?? 'violation-explanation-card'}
    >
      <Stack gap="md">
        {/* Explanation section */}
        <div>
          <Title order={4} mb="xs">
            Violation Explanation
          </Title>
          {explanation ? (
            <Text size="sm" data-testid="violation-explanation-text">
              {explanation}
            </Text>
          ) : (
            <Text size="sm" c="dimmed" fs="italic">
              No AI-generated explanation available for this finding.
            </Text>
          )}
        </div>

        {/* Business impact section */}
        {impactItems.length > 0 && (
          <div>
            <Title order={5} mb="xs" data-testid="business-impact-title">
              Business Impact
            </Title>
            <List
              spacing="xs"
              size="sm"
              icon={
                <ThemeIcon color="red" size={20} radius="xl">
                  <span aria-hidden="true" style={{ fontSize: 12 }}>!</span>
                </ThemeIcon>
              }
              data-testid="business-impact-list"
            >
              {impactItems.map((item, idx) => (
                <List.Item key={idx} data-testid={`impact-item-${idx}`}>
                  {item}
                </List.Item>
              ))}
            </List>
          </div>
        )}
      </Stack>
    </Card>
  );
}
