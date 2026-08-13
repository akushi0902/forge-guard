/**
 * EmptyState — reusable zero-data placeholder component (WO-085).
 *
 * Renders a centred Paper card with an optional illustration, a title,
 * a description, optional onboarding steps, and a primary CTA button.
 * Used by view-specific wrappers in src/components/empty-states/.
 */

import { type JSX } from 'react';
import {
  Button,
  List,
  Paper,
  Stack,
  Text,
  Title,
} from '@mantine/core';
import { type EmptyStateProps } from './EmptyState.types';

/**
 * Reusable empty state component for all data-absent views.
 *
 * @example
 * <EmptyState
 *   illustration={<EmptyEvaluation />}
 *   title="No Evaluations Yet"
 *   description="Run your first evaluation to see results."
 *   steps={[{ label: 'Register your service' }]}
 *   ctaLabel="Run First Evaluation"
 *   ctaAction={() => navigate('/releases/new')}
 * />
 */
export function EmptyState({
  illustration,
  title,
  description,
  steps,
  ctaLabel,
  ctaAction,
  ctaIcon,
  testId,
}: EmptyStateProps): JSX.Element {
  const handleClick =
    typeof ctaAction === 'function' ? ctaAction : undefined;
  const href = typeof ctaAction === 'string' ? ctaAction : undefined;

  return (
    <Paper
      withBorder
      p="xl"
      data-testid={testId ?? 'empty-state'}
      style={{ textAlign: 'center' }}
    >
      <Stack align="center" gap="lg">
        {illustration && (
          <div aria-hidden="true">{illustration}</div>
        )}

        <Title order={3} data-testid="empty-state-title">
          {title}
        </Title>

        <Text
          size="sm"
          c="dimmed"
          maw={480}
          data-testid="empty-state-description"
        >
          {description}
        </Text>

        {steps && steps.length > 0 && (
          <List
            type="ordered"
            spacing="xs"
            style={{ textAlign: 'left', width: '100%', maxWidth: 380 }}
            data-testid="empty-state-steps"
          >
            {steps.map((step, idx) => (
              <List.Item key={idx}>
                <Text size="sm" fw={500} component="span">
                  {step.label}
                </Text>
                {step.description && (
                  <Text size="xs" c="dimmed">
                    {step.description}
                  </Text>
                )}
              </List.Item>
            ))}
          </List>
        )}

        {href ? (
          <Button
            component="a"
            href={href}
            leftSection={ctaIcon}
            data-testid="empty-state-cta"
          >
            {ctaLabel}
          </Button>
        ) : (
          <Button
            onClick={handleClick}
            leftSection={ctaIcon}
            data-testid="empty-state-cta"
          >
            {ctaLabel}
          </Button>
        )}
      </Stack>
    </Paper>
  );
}
