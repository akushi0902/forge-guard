import { type JSX, useEffect, useState } from 'react';
import {
  Alert,
  Button,
  Card,
  Group,
  Loader,
  NumberInput,
  Stack,
  Text,
  Title,
} from '@mantine/core';
import { notifications } from '@mantine/notifications';

import { type ScoreThresholds } from '@/types/api';
import { useScoreThresholds, useUpdateScoreThresholds } from '@/hooks/api/usePolicies';

const DEFAULT_THRESHOLDS: ScoreThresholds = {
  approve: { min_health: 70, max_risk: 30 },
  conditional: { min_health: 50, max_risk: 60 },
  block_explanation: 'Services scoring below the conditional threshold are blocked from release.',
};

export function ScoreThresholdsPanel(): JSX.Element {
  const { data, isLoading } = useScoreThresholds();
  const { mutateAsync: updateThresholds, isPending } = useUpdateScoreThresholds();

  const [thresholds, setThresholds] = useState<ScoreThresholds>(DEFAULT_THRESHOLDS);

  useEffect(() => {
    if (data) setThresholds(data);
  }, [data]);

  function validationError(): string | null {
    if (thresholds.approve.min_health <= thresholds.conditional.min_health) {
      return 'Approve minimum health must be strictly greater than conditional minimum health.';
    }
    if (thresholds.approve.max_risk >= thresholds.conditional.max_risk) {
      return 'Approve maximum risk must be strictly less than conditional maximum risk.';
    }
    return null;
  }

  const error = validationError();

  async function handleSave() {
    if (error) return;
    try {
      await updateThresholds(thresholds);
      notifications.show({
        title: 'Thresholds saved',
        message: 'Score thresholds updated successfully.',
        color: 'green',
      });
    } catch {
      notifications.show({
        title: 'Save failed',
        message: 'Failed to update score thresholds. Please try again.',
        color: 'red',
      });
    }
  }

  if (isLoading) {
    return (
      <Stack align="center" py="xl">
        <Loader size="sm" />
      </Stack>
    );
  }

  return (
    <Stack gap="md" data-testid="score-thresholds-panel">
      <Text size="sm" c="dimmed">
        Configure the health and risk score thresholds for release gate decisions.
      </Text>

      {/* Approve card */}
      <Card withBorder data-testid="approve-threshold-card">
        <Stack gap="sm">
          <Title order={5} c="green">Approve</Title>
          <Text size="xs" c="dimmed">
            Release proceeds automatically when both conditions are met.
          </Text>
          <Group gap="md">
            <NumberInput
              label="Min health score"
              value={thresholds.approve.min_health}
              onChange={(v) =>
                setThresholds((prev) => ({
                  ...prev,
                  approve: { ...prev.approve, min_health: Number(v) || 0 },
                }))
              }
              min={0}
              max={100}
              suffix="%"
              style={{ flex: 1 }}
              data-testid="approve-min-health"
            />
            <NumberInput
              label="Max risk score"
              value={thresholds.approve.max_risk}
              onChange={(v) =>
                setThresholds((prev) => ({
                  ...prev,
                  approve: { ...prev.approve, max_risk: Number(v) || 0 },
                }))
              }
              min={0}
              max={100}
              suffix="%"
              style={{ flex: 1 }}
              data-testid="approve-max-risk"
            />
          </Group>
        </Stack>
      </Card>

      {/* Conditional approve card */}
      <Card withBorder data-testid="conditional-threshold-card">
        <Stack gap="sm">
          <Title order={5} c="yellow">Conditional Approve</Title>
          <Text size="xs" c="dimmed">
            Release requires manual review and approval from a Tech Lead.
          </Text>
          <Group gap="md">
            <NumberInput
              label="Min health score"
              value={thresholds.conditional.min_health}
              onChange={(v) =>
                setThresholds((prev) => ({
                  ...prev,
                  conditional: { ...prev.conditional, min_health: Number(v) || 0 },
                }))
              }
              min={0}
              max={100}
              suffix="%"
              style={{ flex: 1 }}
              data-testid="conditional-min-health"
            />
            <NumberInput
              label="Max risk score"
              value={thresholds.conditional.max_risk}
              onChange={(v) =>
                setThresholds((prev) => ({
                  ...prev,
                  conditional: { ...prev.conditional, max_risk: Number(v) || 0 },
                }))
              }
              min={0}
              max={100}
              suffix="%"
              style={{ flex: 1 }}
              data-testid="conditional-max-risk"
            />
          </Group>
        </Stack>
      </Card>

      {/* Block explanation card */}
      <Card withBorder data-testid="block-explanation-card">
        <Stack gap="sm">
          <Title order={5} c="red">Block</Title>
          <Text size="xs" c="dimmed">
            Services that do not meet the conditional threshold are automatically blocked.
          </Text>
          <Text size="sm">{thresholds.block_explanation}</Text>
        </Stack>
      </Card>

      {error && (
        <Alert color="red" data-testid="thresholds-validation-alert">
          {error}
        </Alert>
      )}

      <Group justify="flex-end">
        <Button
          onClick={handleSave}
          loading={isPending}
          disabled={Boolean(error)}
          data-testid="save-thresholds-btn"
        >
          Save Thresholds
        </Button>
      </Group>
    </Stack>
  );
}
