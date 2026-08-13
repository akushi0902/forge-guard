import { type JSX } from 'react';
import { Badge, Card, Group, Stack, Text, Title } from '@mantine/core';

export type ServiceStatus = 'up' | 'degraded' | 'down' | 'unknown';

export interface ServiceHealthRow {
  name: string;
  status: ServiceStatus;
  lastChecked: string;
  detail?: string;
}

export interface ServiceHealthCardProps {
  rows: ServiceHealthRow[];
  lastUpdated: string | null;
}

const STATUS_CONFIG: Record<ServiceStatus, { icon: string; color: string; label: string }> = {
  up:      { icon: '✅', color: 'green',  label: 'Operational' },
  degraded:{ icon: '⚠️', color: 'yellow', label: 'Degraded'    },
  down:    { icon: '❌', color: 'red',    label: 'Down'        },
  unknown: { icon: '❓', color: 'gray',   label: 'Unknown'     },
};

export function HealthCheckRow({ name, status, lastChecked, detail }: ServiceHealthRow): JSX.Element {
  const config = STATUS_CONFIG[status];
  const testId = `service-status-${name.toLowerCase().replace(/\s+/g, '-')}`;

  return (
    <Group
      justify="space-between"
      py={8}
      style={{ borderBottom: '1px solid var(--mantine-color-gray-2)' }}
      data-testid={`health-row-${name.toLowerCase().replace(/\s+/g, '-')}`}
    >
      <Group gap="sm">
        <span aria-hidden="true" style={{ fontSize: 16 }}>{config.icon}</span>
        <Stack gap={0}>
          <Text size="sm" fw={500}>{name}</Text>
          {detail && <Text size="xs" c="dimmed">{detail}</Text>}
        </Stack>
      </Group>
      <Group gap="sm">
        <Badge
          color={config.color}
          variant="light"
          data-testid={testId}
        >
          {config.label}
        </Badge>
        <Text size="xs" c="dimmed">{lastChecked}</Text>
      </Group>
    </Group>
  );
}

export function ServiceHealthCard({ rows, lastUpdated }: ServiceHealthCardProps): JSX.Element {
  return (
    <Card padding="md" withBorder data-testid="service-health-card">
      <Group justify="space-between" mb="md">
        <Title order={4}>Service Health Checks</Title>
        {lastUpdated && (
          <Text size="xs" c="dimmed">Last checked: {lastUpdated}</Text>
        )}
      </Group>
      <Stack gap={0}>
        {rows.map((row) => (
          <HealthCheckRow key={row.name} {...row} />
        ))}
      </Stack>
    </Card>
  );
}
