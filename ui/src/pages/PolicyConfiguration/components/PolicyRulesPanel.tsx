import { type JSX, useState } from 'react';
import { Button, Group, Loader, Stack, Text } from '@mantine/core';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { notifications } from '@mantine/notifications';

import { type PolicyRule } from '@/types/api';
import { apiClient } from '@/lib/api-client';
import { policyKeys, usePolicies, type PolicyFilters } from '@/hooks/api/usePolicies';
import { FilterBar } from './FilterBar';
import { RulesTable } from './RulesTable';
import { CreateRuleModal } from './CreateRuleModal';

function useToggleRule() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, enabled }: { id: string; enabled: boolean }) =>
      apiClient<PolicyRule>(`/api/v1/policies/${id}`, {
        method: 'PUT',
        body: JSON.stringify({ enabled }),
      }),
    onSettled: () => {
      void queryClient.invalidateQueries({ queryKey: policyKeys.all });
    },
  });
}

export function PolicyRulesPanel(): JSX.Element {
  const [filters, setFilters] = useState<PolicyFilters>({});
  const [modalOpen, setModalOpen] = useState(false);

  const { data, isLoading } = usePolicies(filters);
  const rules = data?.items ?? [];
  const { mutate: toggleRule } = useToggleRule();

  function handleToggle(rule: PolicyRule) {
    toggleRule(
      { id: rule.id, enabled: !rule.enabled },
      {
        onSuccess: () =>
          notifications.show({
            title: rule.enabled ? 'Rule disabled' : 'Rule enabled',
            message: `"${rule.name}" has been ${rule.enabled ? 'disabled' : 'enabled'}.`,
            color: rule.enabled ? 'orange' : 'green',
          }),
        onError: () =>
          notifications.show({
            title: 'Update failed',
            message: 'Failed to update rule status.',
            color: 'red',
          }),
      },
    );
  }

  return (
    <Stack gap="md" data-testid="policy-rules-panel">
      <Group justify="space-between">
        <Text fw={500}>Policy Rules</Text>
        <Button
          onClick={() => setModalOpen(true)}
          data-testid="create-rule-btn"
        >
          Create Rule
        </Button>
      </Group>

      <FilterBar
        search={filters.search ?? ''}
        dimension={filters.dimension ?? ''}
        severity={filters.severity ?? ''}
        onSearchChange={(v) => setFilters((f) => ({ ...f, search: v || undefined }))}
        onDimensionChange={(v) => setFilters((f) => ({ ...f, dimension: v || undefined }))}
        onSeverityChange={(v) => setFilters((f) => ({ ...f, severity: v || undefined }))}
      />

      {isLoading ? (
        <Stack align="center" py="xl">
          <Loader size="sm" />
        </Stack>
      ) : (
        <RulesTable
          rules={rules}
          isLoading={false}
          onToggleEnabled={handleToggle}
          onCreateClick={() => setModalOpen(true)}
        />
      )}

      <CreateRuleModal opened={modalOpen} onClose={() => setModalOpen(false)} />
    </Stack>
  );
}
