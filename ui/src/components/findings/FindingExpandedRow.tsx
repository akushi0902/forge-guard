/**
 * FindingExpandedRow — expanded panel for a finding row in FindingsTable.
 *
 * Lazy-loads the AI recommendation on mount via useFindingRecommendation.
 * Displays:
 *   - recommendation_text   — formatted text
 *   - implementation_guide  — code-like block
 *   - confidence_score      — ConfidenceMeter progress bar
 *
 * Edge cases handled:
 *   - 404 API response     → "No AI recommendation available" message
 *   - Other error          → inline error with retry link
 *   - Loading state        → skeleton placeholder
 */

import {
  Box,
  Button,
  Code,
  Group,
  Skeleton,
  Stack,
  Text,
  Title,
} from '@mantine/core';
import type { JSX } from 'react';

import { useFindingRecommendation } from '@/hooks/api/useFindings';
import { ApiError } from '@/types/errors';
import { ConfidenceMeter } from './ConfidenceMeter';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface FindingExpandedRowProps {
  findingId: string;
  /** Test id for the container. */
  'data-testid'?: string;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

/**
 * @example
 * <FindingExpandedRow findingId="fnd-001" />
 */
export function FindingExpandedRow({
  findingId,
  'data-testid': testId,
}: FindingExpandedRowProps): JSX.Element {
  const { data, isLoading, isError, error, refetch } =
    useFindingRecommendation(findingId);

  // ── Loading state ──────────────────────────────────────────────────────
  if (isLoading) {
    return (
      <Box p="md" data-testid={testId ?? 'finding-expanded-row'}>
        <Stack gap="sm">
          <Skeleton height={16} width="60%" />
          <Skeleton height={12} width="90%" />
          <Skeleton height={12} width="80%" />
          <Skeleton height={8} width="40%" mt="sm" />
        </Stack>
      </Box>
    );
  }

  // ── 404 → No recommendation available ─────────────────────────────────
  const is404 =
    isError && error instanceof ApiError && error.status === 404;

  if (is404) {
    return (
      <Box p="md" data-testid={testId ?? 'finding-expanded-row'}>
        <Text size="sm" c="dimmed">
          No AI recommendation available for this finding.
        </Text>
      </Box>
    );
  }

  // ── Generic error ──────────────────────────────────────────────────────
  if (isError) {
    return (
      <Box p="md" data-testid={testId ?? 'finding-expanded-row'}>
        <Group gap="xs" align="center">
          <Text size="sm" c="red">
            Failed to load AI recommendation.
          </Text>
          <Button
            variant="subtle"
            size="xs"
            color="red"
            onClick={() => void refetch()}
          >
            Retry
          </Button>
        </Group>
      </Box>
    );
  }

  // ── Success ────────────────────────────────────────────────────────────
  if (!data) {
    return (
      <Box p="md" data-testid={testId ?? 'finding-expanded-row'}>
        <Text size="sm" c="dimmed">
          No AI recommendation available for this finding.
        </Text>
      </Box>
    );
  }

  return (
    <Box
      p="md"
      bg="gray.0"
      style={{ borderTop: '1px solid var(--mantine-color-gray-2)' }}
      data-testid={testId ?? 'finding-expanded-row'}
    >
      <Stack gap="md">
        {/* AI Recommendation text */}
        <Box>
          <Title order={6} mb={4} c="dimmed">
            AI Recommendation
          </Title>
          <Text size="sm">{data.recommendation_text}</Text>
        </Box>

        {/* Implementation guide */}
        <Box>
          <Title order={6} mb={4} c="dimmed">
            Implementation Guide
          </Title>
          <Code
            block
            style={{
              whiteSpace: 'pre-wrap',
              fontSize: 'var(--mantine-font-size-xs)',
            }}
          >
            {data.implementation_guide}
          </Code>
        </Box>

        {/* Confidence meter */}
        <ConfidenceMeter
          score={data.confidence_score}
          label="AI Confidence"
          data-testid="finding-confidence-meter"
        />
      </Stack>
    </Box>
  );
}
