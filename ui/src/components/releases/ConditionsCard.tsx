/**
 * ConditionsCard — informational checklist of mandatory conditions for a
 * CONDITIONAL_APPROVE decision.
 *
 * Render this component only for CONDITIONAL_APPROVE decisions; the parent
 * is responsible for conditional mounting.
 *
 * - Non-empty conditions array → renders each condition as a list item.
 * - Empty conditions array → renders a fallback message.
 * - Conditions are read-only (informational), not interactive checkboxes.
 */

import { Card, List, Stack, Text, ThemeIcon, Title } from '@mantine/core';
import { type JSX } from 'react';

export interface ConditionsCardProps {
  /** Array of condition description strings. May be empty. */
  conditions: string[];
}

/**
 * Renders mandatory conditions for a CONDITIONAL_APPROVE decision.
 *
 * @example
 * <ConditionsCard conditions={['Increase test coverage to >= 80%', 'Resolve CVE-2024-1234']} />
 * <ConditionsCard conditions={[]} />
 */
export function ConditionsCard({ conditions }: ConditionsCardProps): JSX.Element {
  return (
    <Card withBorder radius="md" p="md" data-testid="conditions-card">
      <Stack gap="sm">
        <Title order={5}>Mandatory Conditions</Title>
        <Text size="sm" c="dimmed">
          The following conditions must be met before this release proceeds to deployment.
        </Text>

        {conditions.length === 0 ? (
          <Text size="sm" c="dimmed" data-testid="conditions-empty-message">
            No specific conditions defined — review findings before proceeding.
          </Text>
        ) : (
          <List
            spacing="xs"
            icon={
              <ThemeIcon color="warning" size={20} radius="xl">
                <span aria-hidden="true" style={{ fontSize: 12, lineHeight: 1 }}>!</span>
              </ThemeIcon>
            }
          >
            {conditions.map((condition, index) => (
              <List.Item key={index} data-testid={`condition-item-${index}`}>
                <Text size="sm" style={{ wordBreak: 'break-word' }}>
                  {condition}
                </Text>
              </List.Item>
            ))}
          </List>
        )}
      </Stack>
    </Card>
  );
}
