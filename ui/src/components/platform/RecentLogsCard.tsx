import { type JSX } from 'react';
import { Badge, Card, Group, Stack, Text, Title } from '@mantine/core';

import { type PlatformLogEntry } from '@/types/api';

export interface RecentLogsCardProps {
  entries: PlatformLogEntry[] | undefined;
  isLoading: boolean;
}

const LEVEL_COLOR: Record<PlatformLogEntry['level'], string> = {
  info:  'blue',
  warn:  'yellow',
  error: 'red',
};

export function RecentLogsCard({ entries, isLoading }: RecentLogsCardProps): JSX.Element {
  const displayEntries = (entries ?? []).slice(0, 6);

  return (
    <Card padding="md" withBorder data-testid="recent-logs-card">
      <Title order={4} mb="md">Recent Operational Logs</Title>

      {isLoading && <Text c="dimmed" size="sm">Loading logs…</Text>}

      {!isLoading && displayEntries.length === 0 && (
        <Text c="dimmed" size="sm">No recent log entries.</Text>
      )}

      <Stack gap={8}>
        {displayEntries.map((entry) => (
          <Group
            key={entry.id}
            gap="xs"
            align="flex-start"
            wrap="nowrap"
            data-testid={`log-entry-${entry.id}`}
          >
            <Text size="xs" c="dimmed" style={{ minWidth: 56, flexShrink: 0 }}>
              {new Date(entry.timestamp).toLocaleTimeString(undefined, {
                hour: '2-digit',
                minute: '2-digit',
              })}
            </Text>
            <Badge
              size="xs"
              color={LEVEL_COLOR[entry.level]}
              variant="filled"
              style={{ minWidth: 44, flexShrink: 0 }}
              data-testid={`log-level-${entry.id}`}
            >
              {entry.level.toUpperCase()}
            </Badge>
            <Text size="xs" style={{ flex: 1, overflow: 'hidden', textOverflow: 'ellipsis' }}>
              [{entry.service}] {entry.message}
            </Text>
          </Group>
        ))}
      </Stack>
    </Card>
  );
}
