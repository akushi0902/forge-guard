/**
 * FindingsTable — sortable findings table with severity filter and expandable
 * AI explanations (created as part of WO-075 / referenced by WOREF-073).
 *
 * Features:
 *   - Severity filter buttons (All, Critical, High, Medium, Low)
 *   - Expandable rows showing AI explanation, business impact, and remediation steps
 *   - Color-coded severity badges
 *   - Empty state when no findings match the active filter
 */

import {
  Alert,
  Badge,
  Box,
  Button,
  Group,
  List,
  Stack,
  Table,
  Text,
} from '@mantine/core';
import { useState, type JSX } from 'react';

import { type ReleaseAssessmentFinding } from '@/types/api';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export type FindingSeverityFilter = 'all' | 'critical' | 'high' | 'medium' | 'low';

export interface FindingsTableProps {
  /** Findings to display. */
  findings: ReleaseAssessmentFinding[];
  /** Controlled active severity filter. Defaults to 'all'. */
  severityFilter?: FindingSeverityFilter;
  /** Called when the user changes the severity filter. */
  onSeverityFilterChange?: (filter: FindingSeverityFilter) => void;
  /** Show loading placeholder rows. */
  loading?: boolean;
  /** Error message to display in place of the table. */
  error?: string;
}

// ---------------------------------------------------------------------------
// Severity configuration
// ---------------------------------------------------------------------------

const SEVERITY_CONFIG: Record<
  string,
  { color: string; label: string; order: number }
> = {
  critical: { color: 'red', label: 'Critical', order: 0 },
  high:     { color: 'orange', label: 'High', order: 1 },
  medium:   { color: 'yellow', label: 'Medium', order: 2 },
  low:      { color: 'blue', label: 'Low', order: 3 },
  info:     { color: 'gray', label: 'Info', order: 4 },
};

function severityColor(severity: string): string {
  return SEVERITY_CONFIG[severity.toLowerCase()]?.color ?? 'gray';
}

function severityLabel(severity: string): string {
  return SEVERITY_CONFIG[severity.toLowerCase()]?.label ?? severity;
}

function severityOrder(severity: string): number {
  return SEVERITY_CONFIG[severity.toLowerCase()]?.order ?? 99;
}

// ---------------------------------------------------------------------------
// Expandable row
// ---------------------------------------------------------------------------

function FindingRow({ finding }: { finding: ReleaseAssessmentFinding }): JSX.Element {
  const [expanded, setExpanded] = useState(false);

  return (
    <>
      <Table.Tr
        style={{ cursor: 'pointer' }}
        onClick={() => setExpanded((prev) => !prev)}
        aria-expanded={expanded}
        data-testid={`finding-row-${finding.id}`}
      >
        <Table.Td>
          <Badge color={severityColor(finding.severity)} size="sm" variant="light">
            {severityLabel(finding.severity)}
          </Badge>
        </Table.Td>
        <Table.Td>
          <Text size="sm" fw={500}>{finding.title}</Text>
        </Table.Td>
        <Table.Td>
          <Text size="sm" c="dimmed" tt="capitalize">
            {finding.dimension.replace(/_/g, ' ')}
          </Text>
        </Table.Td>
        <Table.Td>
          <Text size="xs" c="dimmed">
            {expanded ? '▲ Hide details' : '▼ Show details'}
          </Text>
        </Table.Td>
      </Table.Tr>
      {expanded && (
        <Table.Tr data-testid={`finding-expanded-${finding.id}`}>
          <Table.Td colSpan={4} style={{ backgroundColor: 'var(--mantine-color-gray-0)' }}>
            <Stack gap="xs" p="sm">
              {finding.explanation && (
                <Box>
                  <Text size="sm" fw={600} mb={4}>AI Explanation</Text>
                  <Text size="sm">{finding.explanation}</Text>
                </Box>
              )}
              {finding.business_impact && (
                <Box>
                  <Text size="sm" fw={600} mb={4}>Business Impact</Text>
                  <Text size="sm">{finding.business_impact}</Text>
                </Box>
              )}
              {finding.remediation_steps.length > 0 && (
                <Box>
                  <Text size="sm" fw={600} mb={4}>Remediation Steps</Text>
                  <List size="sm" spacing={2}>
                    {finding.remediation_steps.map((step, i) => (
                      <List.Item key={i}>{step}</List.Item>
                    ))}
                  </List>
                </Box>
              )}
              {finding.confidence_score > 0 && (
                <Text size="xs" c="dimmed">
                  AI confidence: {Math.round(finding.confidence_score * 100)}%
                </Text>
              )}
            </Stack>
          </Table.Td>
        </Table.Tr>
      )}
    </>
  );
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

const FILTER_OPTIONS: { value: FindingSeverityFilter; label: string }[] = [
  { value: 'all', label: 'All' },
  { value: 'critical', label: 'Critical' },
  { value: 'high', label: 'High' },
  { value: 'medium', label: 'Medium' },
  { value: 'low', label: 'Low' },
];

/**
 * Displays release assessment findings with severity filtering and expandable AI explanations.
 *
 * @example
 * <FindingsTable findings={findings} />
 * <FindingsTable findings={findings} severityFilter="critical" onSeverityFilterChange={setFilter} />
 */
export function FindingsTable({
  findings,
  severityFilter = 'all',
  onSeverityFilterChange,
  loading = false,
  error,
}: FindingsTableProps): JSX.Element {
  const [internalFilter, setInternalFilter] = useState<FindingSeverityFilter>('all');

  const activeFilter = onSeverityFilterChange ? severityFilter : internalFilter;
  const handleFilterChange = onSeverityFilterChange
    ? onSeverityFilterChange
    : setInternalFilter;

  if (error) {
    return (
      <Alert color="danger" title="Failed to load findings">
        {error}
      </Alert>
    );
  }

  const filtered = activeFilter === 'all'
    ? findings
    : findings.filter((f) => f.severity.toLowerCase() === activeFilter);

  const sorted = [...filtered].sort(
    (a, b) => severityOrder(a.severity) - severityOrder(b.severity),
  );

  return (
    <Stack gap="sm">
      {/* Severity filter bar */}
      <Group gap="xs">
        {FILTER_OPTIONS.map(({ value, label }) => {
          const count =
            value === 'all'
              ? findings.length
              : findings.filter((f) => f.severity.toLowerCase() === value).length;
          return (
            <Button
              key={value}
              variant={activeFilter === value ? 'filled' : 'outline'}
              color={value === 'all' ? 'brand' : severityColor(value)}
              size="xs"
              onClick={() => handleFilterChange(value)}
              aria-pressed={activeFilter === value}
              data-testid={`filter-${value}`}
            >
              {label} {count > 0 && `(${count})`}
            </Button>
          );
        })}
      </Group>

      {/* Table */}
      {loading ? (
        <Text size="sm" c="dimmed">Loading findings…</Text>
      ) : sorted.length === 0 ? (
        <Text size="sm" c="dimmed" ta="center" py="lg">
          {activeFilter === 'all'
            ? 'No findings for this assessment.'
            : `No ${activeFilter} findings.`}
        </Text>
      ) : (
        <Table
          striped
          highlightOnHover
          withTableBorder
          withColumnBorders={false}
          data-testid="findings-table"
        >
          <Table.Thead>
            <Table.Tr>
              <Table.Th style={{ width: 100 }}>Severity</Table.Th>
              <Table.Th>Title</Table.Th>
              <Table.Th style={{ width: 160 }}>Dimension</Table.Th>
              <Table.Th style={{ width: 120 }}></Table.Th>
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {sorted.map((finding) => (
              <FindingRow key={finding.id} finding={finding} />
            ))}
          </Table.Tbody>
        </Table>
      )}
    </Stack>
  );
}
