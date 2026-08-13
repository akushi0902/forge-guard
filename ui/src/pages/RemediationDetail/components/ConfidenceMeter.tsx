/**
 * ConfidenceMeter — circular ring indicator for AI recommendation confidence.
 *
 * Uses Mantine RingProgress for a visually distinct presentation on the
 * RemediationDetail page (contrast with the linear Progress bar in
 * src/components/findings/ConfidenceMeter.tsx).
 *
 * Colour thresholds (work order specification):
 *   red    — score < 30%
 *   yellow — score 30–70%
 *   green  — score > 70%
 *
 * Accessibility: follows the same pattern as the findings ConfidenceMeter —
 * a wrapper div carries role="progressbar" + aria-value* attributes, and
 * the inner RingProgress is aria-hidden so screen readers only see the
 * semantic progressbar element.
 */

import { Group, RingProgress, Text } from '@mantine/core';
import type { JSX } from 'react';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface ConfidenceMeterProps {
  /** Confidence score: 0–1 fraction or 0–100 percentage. */
  score: number;
  /** Optional label shown alongside the ring (defaults to "AI Confidence"). */
  label?: string;
  /** Test id for targeting in tests. */
  'data-testid'?: string;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** Normalise any value to a 0–100 percentage. */
function toPercent(score: number): number {
  if (score > 1) return Math.min(100, Math.max(0, score));
  return Math.min(100, Math.max(0, score * 100));
}

/** Return Mantine colour token based on percentage. */
function ringColor(pct: number): string {
  if (pct > 70) return 'teal';
  if (pct >= 30) return 'yellow';
  return 'red';
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

/**
 * Circular confidence indicator with numeric label.
 *
 * @example
 * <ConfidenceMeter score={0.92} />           // "92%" teal ring
 * <ConfidenceMeter score={40} />             // "40%" yellow ring
 * <ConfidenceMeter score={0} />              // "0%" red ring
 */
export function ConfidenceMeter({
  score,
  label = 'AI Confidence',
  'data-testid': testId,
}: ConfidenceMeterProps): JSX.Element {
  const pct = toPercent(score);
  const color = ringColor(pct);
  const displayValue = `${Math.round(pct)}%`;

  return (
    <Group
      gap="sm"
      align="center"
      data-testid={testId ?? 'remediation-confidence-meter'}
    >
      {/*
       * Wrapper div carries the ARIA progressbar semantics.
       * The inner RingProgress is presentation-only (aria-hidden).
       * This mirrors the pattern in src/components/findings/ConfidenceMeter.tsx.
       */}
      <div
        role="progressbar"
        aria-label={`${label}: ${displayValue}`}
        aria-valuenow={Math.round(pct)}
        aria-valuemin={0}
        aria-valuemax={100}
      >
        <RingProgress
          size={80}
          thickness={8}
          roundCaps
          sections={[{ value: pct, color }]}
          label={
            <Text
              ta="center"
              size="xs"
              fw={700}
              c={color}
              aria-hidden="true"
            >
              {displayValue}
            </Text>
          }
          aria-hidden="true"
        />
      </div>
      <div>
        <Text size="sm" fw={500}>
          {label}
        </Text>
        <Text size="xs" c="dimmed">
          {displayValue} confidence in this recommendation
        </Text>
      </div>
    </Group>
  );
}
