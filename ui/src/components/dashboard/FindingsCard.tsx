import { type JSX, useState } from 'react';
import { Card, Stack, Text } from '@mantine/core';
import { type ColumnDef, DataTable, SeverityBadge, TabBar } from '@/components/shared';
import { useServiceFindings } from '@/hooks/api/useFindings';
import { type Finding } from '@/types/api';
import { type FindingSeverity } from '@/types';

const SEVERITY_TABS = [
  { value: 'all',      label: 'All' },
  { value: 'critical', label: 'Critical' },
  { value: 'high',     label: 'High' },
  { value: 'medium',   label: 'Medium' },
  { value: 'low',      label: 'Low' },
];

const STATUS_LABELS: Record<string, string> = {
  open:        'Open',
  in_progress: 'In Progress',
  resolved:    'Resolved',
  excepted:    'Excepted',
};

function formatDate(isoDate: string): string {
  return new Date(isoDate).toLocaleDateString('en-US', {
    month: 'short',
    day:   'numeric',
    year:  'numeric',
  });
}

export interface FindingsCardProps {
  serviceId: string;
}

/**
 * Findings table with severity filter tabs.
 *
 * @example
 * <FindingsCard serviceId="svc-001" />
 */
export function FindingsCard({ serviceId }: FindingsCardProps): JSX.Element {
  const [selectedSeverity, setSelectedSeverity] = useState<string>('all');

  const filters =
    selectedSeverity !== 'all' ? { severity: selectedSeverity } : undefined;

  const { data, isError } = useServiceFindings(serviceId, filters);
  const findings = data?.items ?? [];

  const columns: ColumnDef<Finding>[] = [
    {
      key: 'title',
      header: 'Title',
      render: (row) => (
        <Text size="sm" style={{ maxWidth: 320, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
          {row.title}
        </Text>
      ),
    },
    {
      key: 'severity',
      header: 'Severity',
      render: (row) => (
        <SeverityBadge severity={row.severity as unknown as FindingSeverity} />
      ),
    },
    {
      key: 'dimension',
      header: 'Dimension',
      render: (row) => (
        <Text size="sm" tt="capitalize">
          {row.dimension.replace(/_/g, ' ')}
        </Text>
      ),
    },
    {
      key: 'status',
      header: 'Status',
      render: (row) => (
        <Text size="sm">{STATUS_LABELS[row.status] ?? row.status}</Text>
      ),
    },
    {
      key: 'created_at',
      header: 'Detected',
      render: (row) => (
        <Text size="sm" c="dimmed">
          {formatDate(row.created_at)}
        </Text>
      ),
    },
  ];

  return (
    <Card withBorder>
      <Stack gap="md">
        <Text fw={600} size="lg">
          Findings
        </Text>
        <TabBar
          tabs={SEVERITY_TABS}
          value={selectedSeverity}
          onChange={(v) => v != null && setSelectedSeverity(v)}
        />
        {isError ? (
          <Text c="red" size="sm" role="alert">
            Failed to load findings. Please try again.
          </Text>
        ) : (
          <DataTable
            columns={columns}
            rows={findings}
            rowKey={(r) => r.id}
            emptyMessage="No findings — your service is fully compliant"
          />
        )}
      </Stack>
    </Card>
  );
}
