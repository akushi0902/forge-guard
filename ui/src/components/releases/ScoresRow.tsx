/**
 * ScoresRow — horizontal layout composing Health Score, Risk Score, and
 * Combined Decision into three side-by-side ScoreBox cards.
 *
 * - Health Score uses 'health' colour scheme (green ≥ 70, amber 50-69, red < 50)
 * - Risk Score uses 'risk' colour scheme (green ≤ 30, amber 31-60, red > 60)
 * - Combined Decision uses 'decision' colour scheme (maps decision string to colour)
 */

import { Group } from '@mantine/core';
import { type JSX } from 'react';

import { ScoreBox } from './ScoreBox';

export interface ScoresRowProps {
  /** Engineering Health Score (0–100) or null if unavailable. */
  healthScore: number | null;
  /** Release Risk Score (0–100, lower is safer) or null if unavailable. */
  riskScore: number | null;
  /**
   * Combined decision string from the system recommendation or decision record.
   * Pass null to show 'Pending Review' in neutral colour.
   */
  decision: string | null;
}

/**
 * Renders three ScoreBox cards in a responsive horizontal row.
 *
 * @example
 * <ScoresRow healthScore={85} riskScore={20} decision="APPROVE" />
 * <ScoresRow healthScore={60} riskScore={45} decision="CONDITIONAL_APPROVE" />
 * <ScoresRow healthScore={null} riskScore={null} decision={null} />
 */
export function ScoresRow({ healthScore, riskScore, decision }: ScoresRowProps): JSX.Element {
  return (
    <Group
      gap="md"
      grow
      align="stretch"
      wrap="wrap"
      data-testid="scores-row"
    >
      <ScoreBox
        label="Health Score"
        score={healthScore}
        colorScheme="health"
        subtitle="Engineering health (higher is better)"
      />
      <ScoreBox
        label="Risk Score"
        score={riskScore}
        colorScheme="risk"
        subtitle="Release risk (lower is safer)"
      />
      <ScoreBox
        label="Combined Decision"
        score={null}
        colorScheme="decision"
        decision={decision}
        subtitle="System recommendation"
      />
    </Group>
  );
}
