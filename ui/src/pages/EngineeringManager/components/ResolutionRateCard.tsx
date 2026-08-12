import { type JSX } from 'react';
import { Card, Center, Stack, Text, Title } from '@mantine/core';
import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';

import { type ResolutionRatePoint } from '@/types/api';

export interface ResolutionRateCardProps {
  data: ResolutionRatePoint[] | undefined;
  isLoading: boolean;
}

export function ResolutionRateCard({ data, isLoading }: ResolutionRateCardProps): JSX.Element {
  return (
    <Card withBorder data-testid="resolution-rate-card">
      <Stack gap="md">
        <Title order={4}>Finding Resolution Rate — Last 6 Months</Title>

        {isLoading && (
          <Center h={220}>
            <Text c="dimmed" size="sm">Loading resolution data…</Text>
          </Center>
        )}

        {!isLoading && (!data || data.length === 0) && (
          <Center h={220}>
            <Text c="dimmed" size="sm">No resolution data available.</Text>
          </Center>
        )}

        {!isLoading && data && data.length > 0 && (
          <div
            role="img"
            aria-label="Bar chart showing monthly finding resolution rates for the last 6 months"
          >
            <ResponsiveContainer width="100%" height={220}>
              <BarChart data={data} margin={{ top: 4, right: 16, bottom: 4, left: 0 }}>
                <CartesianGrid strokeDasharray="3 3" vertical={false} />
                <XAxis
                  dataKey="month"
                  tick={{ fontSize: 11 }}
                  label={{ value: 'Month', position: 'insideBottomRight', offset: -4, fontSize: 11 }}
                />
                <YAxis
                  domain={[0, 100]}
                  tick={{ fontSize: 11 }}
                  unit="%"
                  width={44}
                  label={{ value: 'Resolution %', angle: -90, position: 'insideLeft', fontSize: 11 }}
                />
                <Tooltip
                  formatter={(value: number) => [`${value.toFixed(1)}%`, 'Resolution Rate']}
                  labelFormatter={(label: string) => `Month: ${label}`}
                />
                <Bar
                  dataKey="resolution_rate"
                  fill="var(--mantine-color-teal-5)"
                  radius={[3, 3, 0, 0]}
                  name="Resolution Rate"
                />
              </BarChart>
            </ResponsiveContainer>
          </div>
        )}
      </Stack>
    </Card>
  );
}
