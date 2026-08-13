/**
 * SeverityFilterBar — horizontal filter button group for findings severity.
 *
 * Renders 5 buttons: All, Critical, High, Medium, Low.
 * Each button optionally displays a count badge showing the number of findings
 * at that severity level.
 * The currently active filter is visually distinct.
 */

import { Badge, Button, Group } from '@mantine/core';
import type { JSX } from 'react';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export type SeverityFilterValue = 'all' | 'critical' | 'high' | 'medium' | 'low';

export interface SeverityCounts {
  critical?: number;
  high?: number;
  medium?: number;
  low?: number;
}

export interface SeverityFilterBarProps {
  /** Currently active severity filter. */
  value: SeverityFilterValue;
  /** Called when the user clicks a filter button. */
  onFilterChange: (value: SeverityFilterValue) => void;
  /** Per-severity finding counts shown as badge labels. */
  severityCounts?: SeverityCounts;
  /** Test id for the container. */
  'data-testid'?: string;
}

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

interface FilterOption {
  value: SeverityFilterValue;
  label: string;
  color: string;
}

const FILTER_OPTIONS: FilterOption[] = [
  { value: 'all',      label: 'All',      color: 'gray' },
  { value: 'critical', label: 'Critical', color: 'red' },
  { value: 'high',     label: 'High',     color: 'orange' },
  { value: 'medium',   label: 'Medium',   color: 'yellow' },
  { value: 'low',      label: 'Low',      color: 'blue' },
];

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

/**
 * @example
 * <SeverityFilterBar
 *   value="all"
 *   onFilterChange={setSeverity}
 *   severityCounts={{ critical: 3, high: 5, medium: 2, low: 1 }}
 * />
 */
export function SeverityFilterBar({
  value,
  onFilterChange,
  severityCounts = {},
  'data-testid': testId,
}: SeverityFilterBarProps): JSX.Element {
  const totalCount =
    (severityCounts.critical ?? 0) +
    (severityCounts.high ?? 0) +
    (severityCounts.medium ?? 0) +
    (severityCounts.low ?? 0);

  function getCount(opt: FilterOption): number | undefined {
    if (opt.value === 'all') return totalCount > 0 ? totalCount : undefined;
    return (severityCounts as Record<string, number | undefined>)[opt.value];
  }

  return (
    <Group gap="xs" data-testid={testId ?? 'severity-filter-bar'} role="toolbar" aria-label="Filter by severity">
      {FILTER_OPTIONS.map((opt) => {
        const isActive = value === opt.value;
        const count = getCount(opt);

        return (
          <Button
            key={opt.value}
            variant={isActive ? 'filled' : 'light'}
            color={isActive ? opt.color : 'gray'}
            size="xs"
            onClick={() => onFilterChange(opt.value)}
            aria-pressed={isActive}
            data-testid={`severity-filter-${opt.value}`}
            rightSection={
              count !== undefined ? (
                <Badge
                  size="xs"
                  variant="filled"
                  color={isActive ? 'white' : opt.color}
                  style={{ color: isActive ? opt.color : undefined }}
                  aria-label={`${count} ${opt.label} findings`}
                >
                  {count}
                </Badge>
              ) : undefined
            }
          >
            {opt.label}
          </Button>
        );
      })}
    </Group>
  );
}
