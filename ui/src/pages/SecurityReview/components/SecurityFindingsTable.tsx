/**
 * SecurityFindingsTable — sortable, filterable table of security findings.
 *
 * Columns: Severity, Service, Title, Status, Detected At
 * Features:
 *   - Client-side sorting by any column (click column header)
 *   - Severity badge colour coding: critical=red, high=orange, medium=yellow, low=blue
 *   - Row click navigates to finding detail (/findings/:id)
 *   - Empty state when no findings
 *   - Truncates long descriptions with title attribute for full text
 */

import {
  Badge,
  Group,
  Skeleton,
  Stack,
  Table,
  Text,
  UnstyledButton,
} from '@mantine/core';
import { type JSX, useState } from 'react';
import { useNavigate } from 'react-router-dom';

import { type SecurityFinding } from '@/hooks/api/useSecurityFindings';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

type SortKey = 'severity' | 'service_name' | 'title' | 'status' | 'created_at';
type SortDir = 'asc' | 'desc';

const SEVERITY_ORDER: Record<string, number> = {
  critical: 0,
  high: 1,
  medium: 2,
  low: 3,
  info: 4,
};

const SEVERITY_COLORS: Record<string, string> = {
  critical: 'red',
  high: 'orange',
  medium: 'yellow',
  low: 'blue',
  info: 'gray',
};

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function compareFinding(a: SecurityFinding, b: SecurityFinding, key: SortKey): number {
  if (key === 'severity') {
    return (SEVERITY_ORDER[a.severity] ?? 99) - (SEVERITY_ORDER[b.severity] ?? 99);
  }
  const av = a[key] ?? '';
  const bv = b[key] ?? '';
  return String(av).localeCompare(String(bv));
}

function formatDate(iso: string): string {
  try {
    return new Date(iso).toLocaleDateString(undefined, {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
    });
  } catch {
    return iso;
  }
}

// ---------------------------------------------------------------------------
// Column header with sort indicator
// ---------------------------------------------------------------------------

interface SortableHeaderProps {
  label: string;
  sortKey: SortKey;
  currentKey: SortKey;
  direction: SortDir;
  onSort: (key: SortKey) => void;
}

function SortableHeader({
  label,
  sortKey,
  currentKey,
  direction,
  onSort,
}: SortableHeaderProps): JSX.Element {
  const isActive = currentKey === sortKey;
  const indicator = isActive ? (direction === 'asc' ? ' ↑' : ' ↓') : '';

  return (
    <Table.Th>
      <UnstyledButton
        onClick={() => onSort(sortKey)}
        style={{ fontWeight: 600, cursor: 'pointer', whiteSpace: 'nowrap' }}
        aria-label={`Sort by ${label}${isActive ? `, currently ${direction}ending` : ''}`}
      >
        {label}
        <Text component="span" c={isActive ? 'brand' : 'dimmed'} size="xs" aria-hidden="true">
          {indicator || ' ↕'}
        </Text>
      </UnstyledButton>
    </Table.Th>
  );
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export interface SecurityFindingsTableProps {
  findings: SecurityFinding[];
  isLoading?: boolean;
}

export function SecurityFindingsTable({
  findings,
  isLoading = false,
}: SecurityFindingsTableProps): JSX.Element {
  const navigate = useNavigate();
  const [sortKey, setSortKey] = useState<SortKey>('severity');
  const [sortDir, setSortDir] = useState<SortDir>('asc');

  function handleSort(key: SortKey): void {
    if (key === sortKey) {
      setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'));
    } else {
      setSortKey(key);
      setSortDir('asc');
    }
  }

  const sorted = [...findings].sort((a, b) => {
    const cmp = compareFinding(a, b, sortKey);
    return sortDir === 'asc' ? cmp : -cmp;
  });

  return (
    <Stack gap="sm">
      {/* Loading skeleton */}
      {isLoading && (
        <Stack gap="xs" data-testid="findings-table-skeleton">
          {Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} height={40} radius="sm" />
          ))}
        </Stack>
      )}

      {/* Empty state */}
      {!isLoading && findings.length === 0 && (
        <Stack align="center" gap="xs" py="xl" data-testid="findings-table-empty">
          <Text size="xl">🔒</Text>
          <Text fw={500}>No security findings detected</Text>
          <Text size="sm" c="dimmed" ta="center">
            No critical or high security findings have been detected across your services.
            Keep monitoring to stay ahead of emerging threats.
          </Text>
        </Stack>
      )}

      {/* Findings table */}
      {!isLoading && findings.length > 0 && (
        <Table
          striped
          highlightOnHover
          withTableBorder
          withColumnBorders
          data-testid="security-findings-table"
          aria-label="Security findings"
        >
          <Table.Thead>
            <Table.Tr>
              <SortableHeader
                label="Severity"
                sortKey="severity"
                currentKey={sortKey}
                direction={sortDir}
                onSort={handleSort}
              />
              <SortableHeader
                label="Service"
                sortKey="service_name"
                currentKey={sortKey}
                direction={sortDir}
                onSort={handleSort}
              />
              <SortableHeader
                label="Title"
                sortKey="title"
                currentKey={sortKey}
                direction={sortDir}
                onSort={handleSort}
              />
              <SortableHeader
                label="Status"
                sortKey="status"
                currentKey={sortKey}
                direction={sortDir}
                onSort={handleSort}
              />
              <SortableHeader
                label="Detected"
                sortKey="created_at"
                currentKey={sortKey}
                direction={sortDir}
                onSort={handleSort}
              />
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {sorted.map((finding) => (
              <Table.Tr
                key={finding.id}
                onClick={() => void navigate(`/findings/${finding.id}`)}
                style={{ cursor: 'pointer' }}
                data-testid={`finding-row-${finding.id}`}
                role="row"
                aria-label={`Finding: ${finding.title}`}
                tabIndex={0}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' || e.key === ' ') {
                    e.preventDefault();
                    void navigate(`/findings/${finding.id}`);
                  }
                }}
              >
                <Table.Td>
                  <Badge
                    color={SEVERITY_COLORS[finding.severity.toLowerCase()] ?? 'gray'}
                    variant="filled"
                    size="sm"
                    data-testid={`finding-severity-${finding.id}`}
                  >
                    {finding.severity.toUpperCase()}
                  </Badge>
                </Table.Td>
                <Table.Td>
                  <Text size="sm" fw={500}>
                    {finding.service_name}
                  </Text>
                </Table.Td>
                <Table.Td>
                  <Text
                    size="sm"
                    lineClamp={2}
                    title={finding.title}
                    data-testid={`finding-title-${finding.id}`}
                  >
                    {finding.title}
                  </Text>
                </Table.Td>
                <Table.Td>
                  <Group gap="xs">
                    <Badge
                      color={
                        finding.status === 'resolved'
                          ? 'green'
                          : finding.status === 'in_progress'
                            ? 'blue'
                            : finding.status === 'excepted'
                              ? 'violet'
                              : 'red'
                      }
                      variant="light"
                      size="sm"
                    >
                      {finding.status.replace('_', ' ')}
                    </Badge>
                  </Group>
                </Table.Td>
                <Table.Td>
                  <Text size="sm" c="dimmed">
                    {formatDate(finding.created_at)}
                  </Text>
                </Table.Td>
              </Table.Tr>
            ))}
          </Table.Tbody>
        </Table>
      )}
    </Stack>
  );
}
