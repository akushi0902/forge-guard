/**
* ScoreComparisonCard — before/after health score comparison with action buttons.
 *
 * Contains:
 *   BeforeAfterGrid — two-column grid showing score values with delta indicator.
 *   ActionButtons   — Re-evaluate (with loading state), Request Exception.
 *
 * Re-evaluation constraints (work order):
 *   - May take up to 30 seconds
 *   - Loading state must persist with a progress indicator
 *   - User must not be able to trigger multiple concurrent re-evaluations
 *
 * Edge cases:
 *   - No previous re-evaluation → show only action buttons
 *   - score_delta === 0 → display "No change detected"
 *   - Finding resolved → hide action buttons
 */

import {
  Badge,
  Button,
  Card,
  Divider,
  Grid,
  Group,
  Loader,
  Stack,
  Text,
  Title,
} from '@mantine/core';
import type { JSX } from 'react';

import { type ReEvaluationResult } from '@/types/api';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface ScoreComparisonCardProps {
  /** Most recent re-evaluation result. Null if never re-evaluated. */
  reEvalResult: ReEvaluationResult | null;
  /** True while the re-evaluate mutation is in-flight. */
  isReEvaluating: boolean;
  /** True when the finding is resolved — hides action buttons. */
  isResolved: boolean;
  /** Handler for the Re-evaluate button click. */
  onReEvaluate: () => void;
  /** Handler for the Request Exception button click. */
  onRequestException: () => void;
  /** Test id for targeting in tests. */
  'data-testid'?: string;
}

// ---------------------------------------------------------------------------
// Delta helpers
// ---------------------------------------------------------------------------

function getDeltaConfig(delta: number | null): {
  label: string;
  color: string;
  icon: string;
} {
  if (delta === null || delta === 0) {
    return { label: 'No change detected', color: 'gray', icon: '→' };
  }
  if (delta > 0) {
    return { label: `+${delta.toFixed(1)} improvement`, color: 'teal', icon: '↑' };
  }
  return { label: `${delta.toFixed(1)} regression`, color: 'red', icon: '↓' };
}

// ---------------------------------------------------------------------------
// BeforeAfterGrid sub-component
// ---------------------------------------------------------------------------

function BeforeAfterGrid({
  result,
}: {
  result: ReEvaluationResult;
}): JSX.Element {
  const delta = getDeltaConfig(result.score_delta);

  return (
    <Stack gap="sm" data-testid="before-after-grid">
      <Grid>
        {/* Before score */}
        <Grid.Col span={5}>
          <Card withBorder padding="sm" ta="center">
            <Text size="xs" c="dimmed" mb={4}>
              Before
            </Text>
            <Text
              size="2rem"
              fw={700}
              {...(result.before_health_score === null ? { c: 'dimmed' as const } : {})}
              data-testid="before-score"
            >
              {result.before_health_score !== null
                ? Math.round(result.before_health_score)
                : '–'}
            </Text>
            <Text size="xs" c="dimmed">
              Health Score
            </Text>
          </Card>
        </Grid.Col>

        {/* Delta arrow */}
        <Grid.Col span={2} style={{ display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
          <Text size="xl" fw={700} c={delta.color} aria-hidden="true">
            {delta.icon}
          </Text>
        </Grid.Col>

        {/* After score */}
        <Grid.Col span={5}>
          <Card withBorder padding="sm" ta="center">
            <Text size="xs" c="dimmed" mb={4}>
              After
            </Text>
            <Text
              size="2rem"
              fw={700}
              c={delta.color}
              data-testid="after-score"
            >
              {Math.round(result.after_health_score)}
            </Text>
            <Text size="xs" c="dimmed">
              Health Score
            </Text>
          </Card>
        </Grid.Col>
      </Grid>

      {/* Delta summary badge */}
      <Group justify="center">
        <Badge
          color={delta.color}
          size="md"
          variant="light"
          data-testid="score-delta-badge"
        >
          {delta.label}
        </Badge>
      </Group>

      {/* Status change */}
      {result.before_finding_status !== result.after_finding_status && (
        <Text size="xs" c="dimmed" ta="center" data-testid="status-change-text">
          Finding status changed:{' '}
          <strong>{result.before_finding_status}</strong> →{' '}
          <strong>{result.after_finding_status}</strong>
        </Text>
      )}
    </Stack>
  );
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export function ScoreComparisonCard({
  reEvalResult,
  isReEvaluating,
  isResolved,
  onReEvaluate,
  onRequestException,
  'data-testid': testId,
}: ScoreComparisonCardProps): JSX.Element {
  return (
    <Card withBorder padding="lg" data-testid={testId ?? 'score-comparison-card'}>
      <Stack gap="md">
        <Title order={4}>Score Comparison</Title>

        {/* Before/after grid — only shown after at least one re-evaluation */}
        {reEvalResult ? (
          <BeforeAfterGrid result={reEvalResult} />
        ) : (
          <Text size="sm" c="dimmed" fs="italic" data-testid="no-reevaluation-text">
            No re-evaluation has been performed yet. Click "Re-evaluate" to
            check if the finding is resolved after your fix.
          </Text>
        )}

        {/* Action buttons — hidden when finding is resolved */}
        {!isResolved && (
          <>
            <Divider />
            <Group gap="sm" wrap="wrap">
              {/* Re-evaluate button */}
              <Button
                variant="filled"
                color="blue"
                onClick={onReEvaluate}
                disabled={isReEvaluating}
                leftSection={
                  isReEvaluating ? (
                    <Loader size="xs" color="white" />
                  ) : undefined
                }
                data-testid="re-evaluate-btn"
                aria-label={
                  isReEvaluating
                    ? 'Re-evaluation in progress, please wait'
                    : 'Re-evaluate this finding'
                }
              >
                {isReEvaluating ? 'Re-evaluating…' : 'Re-evaluate'}
              </Button>

              {/* Request Exception button */}
              <Button
                variant="outline"
                color="orange"
                onClick={onRequestException}
                disabled={isReEvaluating}
                data-testid="request-exception-btn"
              >
                Request Exception
              </Button>
            </Group>
          </>
        )}
      </Stack>
    </Card>
  );
}
