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

import { type AssessmentTrendPoint } from '@/types/api';

export interface TrendChartCardProps {
  data: AssessmentTrendPoint[] | undefined;
  isLoading: boolean;
}

export function TrendChartCard({ data, isLoading }: TrendChartCardProps): JSX.Element {
  return (
    <Card withBorder data-testid="trend-chart-card">
      <Stack gap="md">
        <Title order={4}>Health Score Trend — Last 6 Months</Title>

        {isLoading && (
          <Center h={220}>
            <Text c="dimmed" size="sm">Loading trend data…</Text>
          </Center>
        )}

        {!isLoading && (!data || data.length === 0) && (
          <Center h={220}>
            <Text c="dimmed" size="sm">No trend data available.</Text>
          </Center>
        )}

        {!isLoading && data && data.length > 0 && (
          <div
            role="img"
            aria-label="Bar chart showing monthly average health scores for the last 6 months"
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
                  width={36}
                  label={{ value: 'Avg Score', angle: -90, position: 'insideLeft', fontSize: 11 }}
                />
                <Tooltip
                  formatter={(value: number) => [`${value}`, 'Avg Health Score']}
                  labelFormatter={(label: string) => `Month: ${label}`}
                />
                <Bar
                  dataKey="avg_score"
                  fill="var(--mantine-color-blue-5)"
                  radius={[3, 3, 0, 0]}
                  name="Avg Health Score"
                />
              </BarChart>
            </ResponsiveContainer>
          </div>
        )}
      </Stack>
    </Card>
  );
}
