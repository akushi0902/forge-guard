import { type JSX } from 'react';
import { Group, Select, TextInput } from '@mantine/core';
import { PolicyDimension, PolicySeverity } from '@/types/api';

const DIMENSION_OPTIONS = [
  { value: '', label: 'All dimensions' },
  { value: PolicyDimension.CodeQuality, label: 'Code Quality' },
  { value: PolicyDimension.TestCoverage, label: 'Test Coverage' },
  { value: PolicyDimension.Security, label: 'Security' },
  { value: PolicyDimension.Documentation, label: 'Documentation' },
  { value: PolicyDimension.OperationsReadiness, label: 'Operations Readiness' },
];

const SEVERITY_OPTIONS = [
  { value: '', label: 'All severities' },
  { value: PolicySeverity.Critical, label: 'Critical' },
  { value: PolicySeverity.High, label: 'High' },
  { value: PolicySeverity.Medium, label: 'Medium' },
  { value: PolicySeverity.Low, label: 'Low' },
];

export interface FilterBarProps {
  search: string;
  dimension: string;
  severity: string;
  onSearchChange: (v: string) => void;
  onDimensionChange: (v: string) => void;
  onSeverityChange: (v: string) => void;
}

export function FilterBar({
  search,
  dimension,
  severity,
  onSearchChange,
  onDimensionChange,
  onSeverityChange,
}: FilterBarProps): JSX.Element {
  return (
    <Group gap="sm" data-testid="filter-bar">
      <TextInput
        placeholder="Search rules…"
        value={search}
        onChange={(e) => onSearchChange(e.currentTarget.value)}
        data-testid="filter-search"
        style={{ flex: 1, minWidth: 200 }}
      />
      <Select
        placeholder="Dimension"
        data={DIMENSION_OPTIONS}
        value={dimension}
        onChange={(v) => onDimensionChange(v ?? '')}
        data-testid="filter-dimension"
        clearable
        style={{ minWidth: 180 }}
      />
      <Select
        placeholder="Severity"
        data={SEVERITY_OPTIONS}
        value={severity}
        onChange={(v) => onSeverityChange(v ?? '')}
        data-testid="filter-severity"
        clearable
        style={{ minWidth: 150 }}
      />
    </Group>
  );
}
