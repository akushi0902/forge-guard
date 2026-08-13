/**
 * ConfidenceMeter — horizontal progress bar showing AI confidence score.
 *
 * Color coding:
 *   green  — score >= 0.8 (≥ 80%)
 *   amber  — score 0.5–0.79 (50–79%)
 *   red    — score < 0.5 (< 50%)
 *
 * Accepts score as a fraction (0–1) or percentage (0–100); values > 1 are
 * treated as percentages and normalised automatically.
 */

import { Group, Progress, Text } from '@mantine/core';
import type { JSX } from 'react';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface ConfidenceMeterProps {
  /** Confidence score: 0–1 fraction or 0–100 percentage. */
  score: number;
  /** Optional label prefix (defaults to "Confidence"). */
  label?: string;
  /** Test id for targeting in tests. */
  'data-testid'?: string;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** Normalise any value to a 0–100 percentage. */
function toPercent(score: number): number {
  if (score > 1) {
    // Already a percentage (e.g. 95 → 95%)
    return Math.min(100, Math.max(0, score));
  }
  return Math.min(100, Math.max(0, score * 100));
}

/** Return Mantine colour token based on percentage. */
function scoreColor(pct: number): string {
  if (pct >= 80) return 'teal';
  if (pct >= 50) return 'yellow';
  return 'red';
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

/**
 * @example
 * <ConfidenceMeter score={0.92} />           // "92%"
 * <ConfidenceMeter score={75} />             // "75%"
 * <ConfidenceMeter score={0} label="Score" /> // "0%"
 */
export function ConfidenceMeter({
  score,
  label = 'Confidence',
  'data-testid': testId,
}: ConfidenceMeterProps): JSX.Element {
  const pct = toPercent(score);
  const color = scoreColor(pct);
  const displayValue = `${Math.round(pct)}%`;

  return (
    <Group gap="xs" align="center" data-testid={testId ?? 'confidence-meter'}>
      <Text size="sm" c="dimmed" style={{ minWidth: 80 }}>
        {label}
      </Text>
      {/*
       * Mantine Progress v7 renders a <div role="progressbar"> internally with
       * aria-valuenow set from `value`. We wrap with a div that provides the
       * accessible label so screen readers announce label + percentage.
       */}
      <div
        role="progressbar"
        aria-label={`${label}: ${displayValue}`}
        aria-valuenow={Math.round(pct)}
        aria-valuemin={0}
        aria-valuemax={100}
        style={{ flex: 1, minWidth: 80 }}
      >
        <Progress
          value={pct}
          color={color}
          size="sm"
          aria-hidden="true"
        />
      </div>
      <Text size="sm" fw={500} style={{ minWidth: 36, textAlign: 'right' }}>
        {displayValue}
      </Text>
    </Group>
  );
}
