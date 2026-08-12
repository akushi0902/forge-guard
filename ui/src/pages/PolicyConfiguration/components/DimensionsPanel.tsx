import { type JSX, useEffect, useState } from 'react';
import { Alert, Button, Group, Loader, Stack, Text } from '@mantine/core';
import { notifications } from '@mantine/notifications';

import { PolicyDimension, type DimensionWeight } from '@/types/api';
import { useDimensionWeights, useUpdateDimensionWeights } from '@/hooks/api/usePolicies';
import { DimensionWeightRow } from './DimensionWeightRow';

const ALL_DIMENSIONS: PolicyDimension[] = [
  PolicyDimension.Security,
  PolicyDimension.TestCoverage,
  PolicyDimension.CodeQuality,
  PolicyDimension.Documentation,
  PolicyDimension.OperationsReadiness,
];

const DEFAULT_WEIGHTS: DimensionWeight[] = ALL_DIMENSIONS.map((d, i) => ({
  dimension: d,
  weight: i === 0 ? 30 : i === 1 ? 25 : i === 2 ? 20 : i === 3 ? 15 : 10,
}));

export function DimensionsPanel(): JSX.Element {
  const { data, isLoading } = useDimensionWeights();
  const { mutateAsync: updateWeights, isPending } = useUpdateDimensionWeights();

  const [weights, setWeights] = useState<DimensionWeight[]>(DEFAULT_WEIGHTS);

  useEffect(() => {
    if (data && data.length > 0) {
      // Merge server data, ensuring all dimensions present
      const map = new Map(data.map((d) => [d.dimension, d.weight]));
      setWeights(
        ALL_DIMENSIONS.map((dim) => ({
          dimension: dim,
          weight: map.get(dim) ?? 0,
        })),
      );
    }
  }, [data]);

  const total = weights.reduce((sum, w) => sum + w.weight, 0);
  const isValid = total === 100;

  function handleWeightChange(dimension: PolicyDimension, weight: number) {
    setWeights((prev) =>
      prev.map((w) => (w.dimension === dimension ? { ...w, weight } : w)),
    );
  }

  async function handleSave() {
    try {
      await updateWeights(weights);
      notifications.show({
        title: 'Weights saved',
        message: 'Dimension weights updated successfully.',
        color: 'green',
      });
    } catch {
      notifications.show({
        title: 'Save failed',
        message: 'Failed to update dimension weights. Please try again.',
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
    <Stack gap="md" data-testid="dimensions-panel">
      <Text size="sm" c="dimmed">
        Configure how each dimension contributes to the overall health score.
        Weights must sum to exactly 100.
      </Text>

      {weights.map((w) => (
        <DimensionWeightRow
          key={w.dimension}
          dimension={w.dimension}
          weight={w.weight}
          onChange={handleWeightChange}
        />
      ))}

      <Group justify="space-between" align="center" mt="sm">
        <Text
          size="sm"
          fw={600}
          c={total === 100 ? 'green' : total > 100 ? 'red' : 'orange'}
          data-testid="weights-total"
        >
          Total: {total}%{total !== 100 && ' (must equal 100)'}
        </Text>
        <Button
          onClick={handleSave}
          loading={isPending}
          disabled={!isValid}
          data-testid="save-weights-btn"
        >
          Save Weights
        </Button>
      </Group>

      {!isValid && (
        <Alert color="orange" data-testid="weights-validation-alert">
          Dimension weights must sum to exactly 100. Current total: {total}%.
        </Alert>
      )}
    </Stack>
  );
}
