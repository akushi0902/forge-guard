import { type JSX } from 'react';
import {
  Badge,
  Button,
  Center,
  Stack,
  Switch,
  Table,
  Text,
} from '@mantine/core';
import { PolicyDimension, PolicySeverity, type PolicyRule } from '@/types/api';

const SEVERITY_COLORS: Record<PolicySeverity, string> = {
  [PolicySeverity.Critical]: 'red',
  [PolicySeverity.High]: 'orange',
  [PolicySeverity.Medium]: 'blue',
  [PolicySeverity.Low]: 'gray',
};

const DIMENSION_LABELS: Record<PolicyDimension, string> = {
  [PolicyDimension.CodeQuality]: 'Code Quality',
  [PolicyDimension.TestCoverage]: 'Test Coverage',
  [PolicyDimension.Security]: 'Security',
  [PolicyDimension.Documentation]: 'Documentation',
  [PolicyDimension.OperationsReadiness]: 'Ops Readiness',
};

export interface RulesTableProps {
  rules: PolicyRule[];
  isLoading: boolean;
  onToggleEnabled: (rule: PolicyRule) => void;
  onCreateClick: () => void;
}

export function RulesTable({
  rules,
  isLoading,
  onToggleEnabled,
  onCreateClick,
}: RulesTableProps): JSX.Element {
  if (!isLoading && rules.length === 0) {
    return (
      <Center py="xl" data-testid="empty-state">
        <Stack align="center" gap="sm">
          <Text c="dimmed" size="sm">No policy rules found.</Text>
          <Button
            onClick={onCreateClick}
            data-testid="create-first-rule-btn"
          >
            Create First Rule
          </Button>
        </Stack>
      </Center>
    );
  }

  return (
    <Table striped highlightOnHover data-testid="rules-table">
      <Table.Thead>
        <Table.Tr>
          <Table.Th>Name</Table.Th>
          <Table.Th>Dimension</Table.Th>
          <Table.Th>Severity</Table.Th>
          <Table.Th>Threshold</Table.Th>
          <Table.Th>Enabled</Table.Th>
        </Table.Tr>
      </Table.Thead>
      <Table.Tbody>
        {isLoading
          ? Array.from({ length: 3 }).map((_, i) => (
              <Table.Tr key={i}>
                {Array.from({ length: 5 }).map((__, j) => (
                  <Table.Td key={j}>
                    <Text c="dimmed" size="xs">—</Text>
                  </Table.Td>
                ))}
              </Table.Tr>
            ))
          : rules.map((rule) => (
              <Table.Tr key={rule.id} data-testid={`rule-row-${rule.id}`}>
                <Table.Td>
                  <Text size="sm" fw={500}>{rule.name}</Text>
                  {rule.description && (
                    <Text size="xs" c="dimmed" lineClamp={1}>{rule.description}</Text>
                  )}
                </Table.Td>
                <Table.Td>
                  <Badge variant="light" size="sm">
                    {DIMENSION_LABELS[rule.dimension] ?? rule.dimension}
                  </Badge>
                </Table.Td>
                <Table.Td>
                  <Badge color={SEVERITY_COLORS[rule.severity] ?? 'gray'} size="sm">
                    {rule.severity}
                  </Badge>
                </Table.Td>
                <Table.Td>
                  <Text size="sm">{rule.threshold}</Text>
                </Table.Td>
                <Table.Td>
                  <Switch
                    checked={rule.enabled}
                    onChange={() => onToggleEnabled(rule)}
                    aria-label={`Toggle ${rule.name}`}
                    data-testid={`toggle-${rule.id}`}
                  />
                </Table.Td>
              </Table.Tr>
            ))}
      </Table.Tbody>
    </Table>
  );
}
