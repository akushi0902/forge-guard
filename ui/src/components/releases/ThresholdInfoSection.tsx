/**
 * ThresholdInfoSection — collapsible section displaying the threshold rules
 * that drive the Combined Release Decision.
 *
 * Rules:
 *   APPROVE:      Health Score ≥ 70 AND Risk Score ≤ 30
 *   CONDITIONAL:  Health Score ≥ 50 AND Risk Score ≤ 60
 *   BLOCK:        Otherwise
 *
 * The frontend displays these rules as read-only information — the backend
 * computes the actual decision; this section makes the logic transparent.
 */

import {
  Accordion,
  Badge,
  Group,
  Stack,
  Text,
} from '@mantine/core';
import { type JSX } from 'react';

interface ThresholdRule {
  decision: string;
  color: string;
  rule: string;
}

const THRESHOLD_RULES: ThresholdRule[] = [
  {
    decision: 'APPROVE',
    color: 'success',
    rule: 'Health Score ≥ 70 AND Risk Score ≤ 30',
  },
  {
    decision: 'CONDITIONAL',
    color: 'warning',
    rule: 'Health Score ≥ 50 AND Risk Score ≤ 60',
  },
  {
    decision: 'BLOCK',
    color: 'danger',
    rule: 'Otherwise (Health Score < 50 OR Risk Score > 60)',
  },
];

/**
 * Collapsible accordion section that shows the 3 decision threshold rules.
 *
 * @example
 * <ThresholdInfoSection />
 */
export function ThresholdInfoSection(): JSX.Element {
  return (
    <Accordion variant="contained" data-testid="threshold-info-section">
      <Accordion.Item value="thresholds">
        <Accordion.Control>
          <Text size="sm" fw={500}>
            ℹ Decision Threshold Rules
          </Text>
        </Accordion.Control>
        <Accordion.Panel>
          <Stack gap="xs" data-testid="threshold-rules">
            {THRESHOLD_RULES.map(({ decision, color, rule }) => (
              <Group key={decision} gap="sm" align="center" data-testid={`threshold-rule-${decision.toLowerCase()}`}>
                <Badge color={color} variant="light" size="sm" style={{ flexShrink: 0 }}>
                  {decision}
                </Badge>
                <Text size="sm">{rule}</Text>
              </Group>
            ))}
          </Stack>
        </Accordion.Panel>
      </Accordion.Item>
    </Accordion>
  );
}
