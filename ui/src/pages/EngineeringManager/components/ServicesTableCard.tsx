import { type JSX, useState, useMemo } from 'react';
import {
  Badge,
  Button,
  Card,
  Center,
  Group,
  Select,
  Stack,
  Table,
  Text,
  Title,
  Tooltip,
} from '@mantine/core';

import { type ServiceWithMetrics, type TrendDirection } from '@/types/api';
import { buildServicesCsv, downloadCsv } from '@/utils/csvExport';

type SortKey = 'name' | 'team' | 'health_score' | 'critical_findings';
type SortDir = 'asc' | 'desc';

const TREND_ICON: Record<TrendDirection, string> = {
  up: '↑',
  down: '↓',
  stable: '→',
};
const TREND_COLOR: Record<TrendDirection, string> = {
  up: 'green',
  down: 'red',
  stable: 'gray',
};

function scoreColor(score: number | null): string {
  if (score == null) return 'gray';
  if (score >= 70) return 'green';
  if (score >= 50) return 'yellow';
  return 'red';
}

export interface ServicesTableCardProps {
  services: ServiceWithMetrics[];
  isLoading: boolean;
  selectedTeam: string;
  onTeamChange: (team: string) => void;
}

export function ServicesTableCard({
  services,
  isLoading,
  selectedTeam,
  onTeamChange,
}: ServicesTableCardProps): JSX.Element {
  const [sortKey, setSortKey] = useState<SortKey>('health_score');
  const [sortDir, setSortDir] = useState<SortDir>('desc');

  const teams = useMemo(() => {
    const unique = Array.from(new Set(services.map((s) => s.team))).sort();
    return [{ value: '', label: 'All Teams' }, ...unique.map((t) => ({ value: t, label: t }))];
  }, [services]);

  const filtered = useMemo(
    () => (selectedTeam ? services.filter((s) => s.team === selectedTeam) : services),
    [services, selectedTeam],
  );

  const sorted = useMemo(() => {
    return [...filtered].sort((a, b) => {
      let aVal: string | number | null;
      let bVal: string | number | null;
      switch (sortKey) {
        case 'name':            aVal = a.name; bVal = b.name; break;
        case 'team':            aVal = a.team; bVal = b.team; break;
        case 'health_score':    aVal = a.health_score ?? -1; bVal = b.health_score ?? -1; break;
        case 'critical_findings': aVal = a.critical_findings; bVal = b.critical_findings; break;
        default:                aVal = 0; bVal = 0;
      }
      if (typeof aVal === 'string' && typeof bVal === 'string') {
        return sortDir === 'asc' ? aVal.localeCompare(bVal) : bVal.localeCompare(aVal);
      }
      const av = aVal as number;
      const bv = bVal as number;
      return sortDir === 'asc' ? av - bv : bv - av;
    });
  }, [filtered, sortKey, sortDir]);

  function handleSort(key: SortKey) {
    if (key === sortKey) {
      setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'));
    } else {
      setSortKey(key);
      setSortDir('desc');
    }
  }

  function handleExport() {
    const csv = buildServicesCsv(filtered);
    downloadCsv(csv, 'engineering-manager-services');
  }

  function headerCell(label: string, key: SortKey) {
    const active = sortKey === key;
    return (
      <Table.Th
        style={{ cursor: 'pointer', userSelect: 'none' }}
        onClick={() => handleSort(key)}
        aria-sort={active ? (sortDir === 'asc' ? 'ascending' : 'descending') : 'none'}
      >
        <Group gap={4} wrap="nowrap">
          {label}
          {active && <Text size="xs" c="blue">{sortDir === 'asc' ? '↑' : '↓'}</Text>}
        </Group>
      </Table.Th>
    );
  }

  return (
    <Card withBorder data-testid="services-table-card">
      <Stack gap="md">
        <Group justify="space-between" wrap="wrap">
          <Title order={4}>Services Overview</Title>
          <Group gap="sm">
            <Select
              placeholder="Filter by team"
              data={teams}
              value={selectedTeam}
              onChange={(v) => onTeamChange(v ?? '')}
              size="sm"
              w={160}
              data-testid="team-filter-select"
              aria-label="Filter services by team"
            />
            <Button
              variant="outline"
              size="sm"
              onClick={handleExport}
              disabled={isLoading || filtered.length === 0}
              data-testid="export-csv-btn"
            >
              Export CSV
            </Button>
          </Group>
        </Group>

        {!isLoading && sorted.length === 0 && (
          <Center py="xl">
            <Stack align="center" gap="xs">
              <Text c="dimmed">No services found.</Text>
              {selectedTeam && (
                <Button variant="subtle" size="xs" onClick={() => onTeamChange('')}>
                  Clear team filter
                </Button>
              )}
            </Stack>
          </Center>
        )}

        {sorted.length > 0 && (
          <Table.ScrollContainer minWidth={600}>
            <Table striped highlightOnHover data-testid="services-table">
              <Table.Thead>
                <Table.Tr>
                  {headerCell('Service', 'name')}
                  {headerCell('Team', 'team')}
                  {headerCell('Health Score', 'health_score')}
                  <Table.Th>Trend</Table.Th>
                  {headerCell('Critical', 'critical_findings')}
                  <Table.Th>High</Table.Th>
                  <Table.Th>Medium</Table.Th>
                  <Table.Th>Low</Table.Th>
                </Table.Tr>
              </Table.Thead>
              <Table.Tbody>
                {sorted.map((s) => (
                  <Table.Tr key={s.id}>
                    <Table.Td>
                      <Tooltip label={s.name} disabled={s.name.length <= 30}>
                        <Text
                          size="sm"
                          fw={500}
                          truncate="end"
                          maw={200}
                          style={{ display: 'block' }}
                        >
                          {s.name}
                        </Text>
                      </Tooltip>
                    </Table.Td>
                    <Table.Td>
                      <Text size="sm">{s.team}</Text>
                    </Table.Td>
                    <Table.Td>
                      <Badge color={scoreColor(s.health_score)} variant="light">
                        {s.health_score ?? 'N/A'}
                      </Badge>
                    </Table.Td>
                    <Table.Td>
                      <Text
                        size="sm"
                        fw={600}
                        c={TREND_COLOR[s.trend_direction]}
                        aria-label={`Trend: ${s.trend_direction}`}
                      >
                        {TREND_ICON[s.trend_direction]}
                      </Text>
                    </Table.Td>
                    <Table.Td>
                      <Text size="sm" c={s.critical_findings > 0 ? 'red' : 'dimmed'}>
                        {s.critical_findings}
                      </Text>
                    </Table.Td>
                    <Table.Td>
                      <Text size="sm" c={s.high_findings > 0 ? 'orange' : 'dimmed'}>
                        {s.high_findings}
                      </Text>
                    </Table.Td>
                    <Table.Td>
                      <Text size="sm">{s.medium_findings}</Text>
                    </Table.Td>
                    <Table.Td>
                      <Text size="sm">{s.low_findings}</Text>
                    </Table.Td>
                  </Table.Tr>
                ))}
              </Table.Tbody>
            </Table>
          </Table.ScrollContainer>
        )}
      </Stack>
    </Card>
  );
}
