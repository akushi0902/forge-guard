/**
 * StatCard / KPICard — metric display cards for the engineering dashboard.
 *
 * StatCard: compact card with title, value, optional trend indicator and icon.
 * KPICard:  larger display with subtitle and responsive sizing.
 */

import {
  Card,
  type CardProps,
  Group,
  Stack,
  Text,
  ThemeIcon,
  type ThemeIconProps,
} from '@mantine/core';
import { type ReactNode } from 'react';

export type TrendDirection = 'up' | 'down' | 'neutral';

export interface StatCardProps extends Omit<CardProps, 'children'> {
  /** Card heading / metric label. */
  title: string;
  /** Primary display value (number, percentage string, etc.). */
  value: string | number;
  /** Optional description shown below the value. */
  subtitle?: string;
  /** Visual trend indicator. */
  trend?: TrendDirection;
  /** Icon element rendered in a ThemeIcon. */
  icon?: ReactNode;
  /** Color of the icon background. Defaults to 'brand'. */
  iconColor?: ThemeIconProps['color'];
}

const TREND_SYMBOL: Record<TrendDirection, string> = {
  up: '↑',
  down: '↓',
  neutral: '→',
};

const TREND_COLOR: Record<TrendDirection, string> = {
  up: 'var(--mantine-color-success-6)',
  down: 'var(--mantine-color-danger-6)',
  neutral: 'var(--mantine-color-neutral-5)',
};

/**
 * @example
 * <StatCard title="Open Findings" value={24} trend="down" />
 * <StatCard title="Health Score" value="87%" icon={<IconShield />} iconColor="success" />
 */
export function StatCard({
  title,
  value,
  subtitle,
  trend,
  icon,
  iconColor = 'brand',
  ...cardProps
}: StatCardProps) {
  return (
    <Card {...cardProps}>
      <Group justify="space-between" align="flex-start">
        <Stack gap={2} style={{ flex: 1 }}>
          <Text size="sm" c="dimmed" fw={500}>
            {title}
          </Text>
          <Group align="baseline" gap="xs">
            <Text size="xl" fw={700}>
              {value}
            </Text>
            {trend && (
              <Text
                size="sm"
                fw={600}
                style={{ color: TREND_COLOR[trend] }}
                aria-label={`Trend: ${trend}`}
              >
                {TREND_SYMBOL[trend]}
              </Text>
            )}
          </Group>
          {subtitle && (
            <Text size="xs" c="dimmed">
              {subtitle}
            </Text>
          )}
        </Stack>
        {icon && (
          <ThemeIcon color={iconColor} variant="light" size="lg" radius="md">
            {icon}
          </ThemeIcon>
        )}
      </Group>
    </Card>
  );
}

// ---------------------------------------------------------------------------
// KPICard — larger variant used in the main dashboard hero row
// ---------------------------------------------------------------------------

export interface KPICardProps extends StatCardProps {
  /** Additional label below the subtitle. */
  caption?: string;
}

export function KPICard({ caption, ...props }: KPICardProps) {
  return (
    <StatCard
      {...props}
      style={{ minHeight: 120, ...props.style }}
      subtitle={
        props.subtitle
          ? caption
            ? `${props.subtitle} · ${caption}`
            : props.subtitle
          : caption
      }
    />
  );
}
