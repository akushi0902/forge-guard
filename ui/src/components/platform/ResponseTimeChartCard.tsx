import { type JSX } from 'react';
import { Card, Center, Loader, Text, Title } from '@mantine/core';
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from 'recharts';

import { type ResponseTimePoint } from '@/types/api';

export interface ResponseTimeChartCardProps {
  data: ResponseTimePoint[] | undefined;
  isLoading: boolean;
}

export function ResponseTimeChartCard({ data, isLoading }: ResponseTimeChartCardProps): JSX.Element {
  return (
    <Card padding="md" withBorder data-testid="response-time-chart-card">
      <Title order={4} mb="md">API Response Times — Last Hour</Title>

      {isLoading && (
        <Center h={200}>
          <Loader size="md" />
        </Center>
      )}

      {!isLoading && (!data || data.length === 0) && (
        <Center h={200}>
          <Text c="dimmed" size="sm">No response time data available.</Text>
        </Center>
      )}

      {!isLoading && data && data.length > 0 && (
        <ResponsiveContainer width="100%" height={200}>
          <BarChart data={data} margin={{ top: 4, right: 16, bottom: 4, left: 0 }}>
            <CartesianGrid strokeDasharray="3 3" vertical={false} />
            <XAxis
              dataKey="minute"
              tick={{ fontSize: 10 }}
              tickFormatter={(v: string) => {
                const d = new Date(v);
                return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`;
              }}
              interval="preserveStartEnd"
              label={{ value: 'Time', position: 'insideBottomRight', offset: -4, fontSize: 10 }}
            />
            <YAxis
              tick={{ fontSize: 10 }}
              unit="ms"
              width={44}
              label={{ value: 'Latency', angle: -90, position: 'insideLeft', fontSize: 10 }}
            />
            <Tooltip
              formatter={(value: number) => [`${value}ms`, 'P50 Latency']}
              labelFormatter={(label: string) => new Date(label).toLocaleTimeString()}
            />
            <Bar dataKey="p50_ms" fill="var(--mantine-color-blue-5)" radius={[2, 2, 0, 0]} />
          </BarChart>
        </ResponsiveContainer>
      )}
    </Card>
  );
}
