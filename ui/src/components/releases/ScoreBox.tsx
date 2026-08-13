/**
 * ScoreBox — compact score display card with color-coded background.
 *
 * Supports three colour schemes:
 *   'health'   — green ≥ 70, amber 50-69, red < 50  (higher is better)
 *   'risk'     — green ≤ 30, amber 31-60, red > 60   (lower is safer)
 *   'decision' — maps decision string to APPROVE/CONDITIONAL/BLOCK/Pending color
 */

import { Badge, Card, Stack, Text, type CardProps } from '@mantine/core';
import { type JSX } from 'react';

export type ScoreBoxColorScheme = 'health' | 'risk' | 'decision';

export interface ScoreBoxProps extends Omit<CardProps, 'children'> {
  /** Display label shown above the score. */
  label: string;
  /** Numeric score (0–100). Pass null to show 'Score unavailable'. */
  score: number | null;
  /** Colour coding scheme. */
  colorScheme: ScoreBoxColorScheme;
  /** Optional descriptive subtitle shown below the value. */
  subtitle?: string;
  /**
   * The decision string ('APPROVE' | 'CONDITIONAL_APPROVE' | 'BLOCK' | null).
   * Required when colorScheme is 'decision'.
   */
  decision?: string | null;
}

type MantineSemanticColor = 'success' | 'warning' | 'danger' | 'neutral';

function getHealthColor(score: number): MantineSemanticColor {
  if (score >= 70) return 'success';
  if (score >= 50) return 'warning';
  return 'danger';
}

function getRiskColor(score: number): MantineSemanticColor {
  if (score <= 30) return 'success';
  if (score <= 60) return 'warning';
  return 'danger';
}

function getDecisionColor(decision: string | null | undefined): MantineSemanticColor {
  switch ((decision ?? '').toUpperCase()) {
    case 'APPROVE':
      return 'success';
    case 'CONDITIONAL_APPROVE':
      return 'warning';
    case 'BLOCK':
      return 'danger';
    default:
      return 'neutral';
  }
}

function getDecisionDisplayText(decision: string | null | undefined): string {
  switch ((decision ?? '').toUpperCase()) {
    case 'APPROVE':
      return 'APPROVE';
    case 'CONDITIONAL_APPROVE':
      return 'CONDITIONAL';
    case 'BLOCK':
      return 'BLOCK';
    default:
      return 'Pending Review';
  }
}

const COLOR_BADGE_LABEL: Record<MantineSemanticColor, string> = {
  success: 'Good',
  warning: 'Fair',
  danger: 'Poor',
  neutral: 'N/A',
};

/**
 * Color-coded score card with a large numeric display, label, and badge.
 *
 * @example
 * <ScoreBox label="Health Score" score={85} colorScheme="health" />
 * <ScoreBox label="Risk Score" score={22} colorScheme="risk" />
 * <ScoreBox label="Combined Decision" score={null} colorScheme="decision" decision="APPROVE" />
 */
export function ScoreBox({
  label,
  score,
  colorScheme,
  subtitle,
  decision,
  style,
  ...cardProps
}: ScoreBoxProps): JSX.Element {
  let color: MantineSemanticColor;

  if (colorScheme === 'health') {
    color = score !== null ? getHealthColor(score) : 'neutral';
  } else if (colorScheme === 'risk') {
    color = score !== null ? getRiskColor(score) : 'neutral';
  } else {
    color = getDecisionColor(decision);
  }

  return (
    <Card
      withBorder
      radius="md"
      p="md"
      style={{
        backgroundColor: `var(--mantine-color-${color}-0)`,
        borderColor: `var(--mantine-color-${color}-3)`,
        flex: 1,
        minWidth: 150,
        ...style,
      }}
      data-testid={`score-box-${label.toLowerCase().replace(/\s+/g, '-')}`}
      data-color={color}
      {...cardProps}
    >
      <Stack gap="xs" align="center">
        <Text size="sm" c="dimmed" fw={500} ta="center">
          {label}
        </Text>

        {colorScheme === 'decision' ? (
          <Text
            fw={700}
            ta="center"
            style={{ color: `var(--mantine-color-${color}-6)`, fontSize: 18 }}
            data-testid="score-box-value"
          >
            {getDecisionDisplayText(decision)}
          </Text>
        ) : score !== null ? (
          <Text
            fw={700}
            ta="center"
            style={{
              color: `var(--mantine-color-${color}-6)`,
              fontSize: 36,
              lineHeight: 1,
            }}
            data-testid="score-box-value"
          >
            {score}
          </Text>
        ) : (
          <Text size="sm" c="dimmed" ta="center" data-testid="score-box-value">
            Score unavailable
          </Text>
        )}

        {subtitle && (
          <Text size="xs" c="dimmed" ta="center">
            {subtitle}
          </Text>
        )}

        {colorScheme !== 'decision' && score !== null && (
          <Badge
            color={color}
            size="xs"
            variant="light"
            data-testid="score-box-badge"
          >
            {COLOR_BADGE_LABEL[color]}
          </Badge>
        )}
      </Stack>
    </Card>
  );
}
