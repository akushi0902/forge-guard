/**
 * FindingsTable — domain-specific table for displaying policy findings.
 *
 * Extends the generic DataTable from WOREF-068 with findings-specific:
 *   - Severity filter bar (All / Critical / High / Medium / Low)
 *   - Sortable columns: title, severity, dimension, created_at
 *   - Cursor-based pagination with prev/next buttons
 *   - Expandable rows lazy-loading AI recommendations
 *   - Error/loading/empty states
 *   - Configurable for full-page and dashboard-card contexts
 *
 * Props:
 *   serviceId            — service whose findings to load
 *   initialSeverityFilter — pre-selected severity filter (default "all")
 *   showDimensionColumn  — show the Dimension column (default true)
 *   showPagination       — show pagination controls (default true)
 *   maxRows              — cap rows for dashboard card mode
 *   onFindingClick       — optional navigation callback on row click
 */

import {
  Box,
  Button,
  Group,
  Loader,
  Stack,
  Text,
  Tooltip,
} from '@mantine/core';
import {
  useCallback,
  useEffect,
  useState,
  type JSX,
} from 'react';
import { useDebouncedValue } from '@mantine/hooks';

import { Alert, DataTable, SeverityBadge, type ColumnDef, type SortState } from '@/components/shared';
import { useServiceFindings } from '@/hooks/api/useFindings';
import { type Finding } from '@/types/api';
import { type FindingSeverity } from '@/types';
import { FindingExpandedRow } from './FindingExpandedRow';
import { SeverityFilterBar, type SeverityFilterValue } from './SeverityFilterBar';

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const STATUS_LABELS: Record<string, string> = {
  open: 'Open',
  in_progress: 'In Progress',
  resolved: 'Resolved',
  excepted: 'Excepted',
};

const SEVERITY_ORDER: Record<string, number> = {
  critical: 0,
  high: 1,
  medium: 2,
  low: 3,
  info: 4,
};

const PAGE_SIZE = 20;

function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  });
}

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface FindingsTableProps {
  /** Service whose findings to display. */
  serviceId: string;
  /** Pre-selected severity filter on mount. */
  initialSeverityFilter?: SeverityFilterValue;
  /** Whether to render the Dimension column (default true). */
  showDimensionColumn?: boolean;
  /** Whether to render pagination controls (default true). */
  showPagination?: boolean;
  /** Cap the number of displayed rows — for dashboard card mode. */
  maxRows?: number;
  /** Optional navigation callback when a finding row is clicked. */
  onFindingClick?: (finding: Finding) => void;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function sortFindings(
  items: Finding[],
  sort: SortState<Finding> | undefined,
): Finding[] {
  if (!sort) return items;
  const { key, direction } = sort;
  const multiplier = direction === 'asc' ? 1 : -1;

  return [...items].sort((a, b) => {
    if (key === 'severity') {
      const diff =
        (SEVERITY_ORDER[a.severity] ?? 99) - (SEVERITY_ORDER[b.severity] ?? 99);
      return diff * multiplier;
    }
    const av = String((a as unknown as Record<string, unknown>)[key as string] ?? '');
    const bv = String((b as unknown as Record<string, unknown>)[key as string] ?? '');
    return av.localeCompare(bv) * multiplier;
  });
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

/**
 * @example
 * // Full page
 * <FindingsTable serviceId="svc-001" />
 *
 * // Dashboard card mode (no pagination, max 5 rows)
 * <FindingsTable serviceId="svc-001" showPagination={false} maxRows={5} />
 */
export function FindingsTable({
  serviceId,
  initialSeverityFilter = 'all',
  showDimensionColumn = true,
  showPagination = true,
  maxRows,
  onFindingClick,
}: FindingsTableProps): JSX.Element {
  // ── Filter state ───────────────────────────────────────────────────────
  const [severityFilter, setSeverityFilter] =
    useState<SeverityFilterValue>(initialSeverityFilter);

  // Debounce rapid filter switches (300 ms) to prevent excessive API calls.
  const [debouncedSeverity] = useDebouncedValue(severityFilter, 300);

  // ── Sort state ─────────────────────────────────────────────────────────
  const [sort, setSort] = useState<SortState<Finding> | undefined>(undefined);

  // ── Cursor-based pagination ────────────────────────────────────────────
  const [cursor, setCursor] = useState<string | null>(null);
  const [cursorHistory, setCursorHistory] = useState<(string | null)[]>([]);

  // ── Reset pagination when filter or sort changes ───────────────────────
  useEffect(() => {
    setCursor(null);
    setCursorHistory([]);
  }, [debouncedSeverity, sort]);

  // ── API query ──────────────────────────────────────────────────────────
  const filters = {
    severity: debouncedSeverity !== 'all' ? debouncedSeverity : undefined,
    cursor: cursor ?? undefined,
    limit: maxRows ?? PAGE_SIZE,
    sort_by: sort?.key as string | undefined,
    sort_dir: sort?.direction,
  };

  const { data, isLoading, isError, refetch } = useServiceFindings(
    serviceId,
    filters,
  );

  // ── Derived data ───────────────────────────────────────────────────────
  const allItems = data?.items ?? [];
  const nextCursor = data?.cursor ?? null;

  // Sort client-side as a fallback (server-side sort params also sent).
  const sortedItems = sortFindings(allItems, sort);
  const visibleItems = maxRows ? sortedItems.slice(0, maxRows) : sortedItems;

  // Severity counts for the filter bar (from current page).
  const severityCounts = {
    critical: allItems.filter((f) => f.severity === 'critical').length,
    high: allItems.filter((f) => f.severity === 'high').length,
    medium: allItems.filter((f) => f.severity === 'medium').length,
    low: allItems.filter((f) => f.severity === 'low').length,
  };

  // ── Filter change handler ──────────────────────────────────────────────
  const handleFilterChange = useCallback((value: SeverityFilterValue) => {
    setSeverityFilter(value);
  }, []);

  // ── Sort handler ───────────────────────────────────────────────────────
  const handleSort = useCallback((newSort: SortState<Finding>) => {
    setSort(newSort);
  }, []);

  // ── Pagination handlers ────────────────────────────────────────────────
  const handleNext = useCallback(() => {
    if (!nextCursor) return;
    setCursorHistory((h) => [...h, cursor]);
    setCursor(nextCursor);
  }, [cursor, nextCursor]);

  const handlePrev = useCallback(() => {
    if (cursorHistory.length === 0) return;
    const newHistory = [...cursorHistory];
    const prevCursor = newHistory.pop() ?? null;
    setCursorHistory(newHistory);
    setCursor(prevCursor);
  }, [cursorHistory]);

  const isFirstPage = cursorHistory.length === 0;
  const isLastPage = !nextCursor;

  // ── Column definitions ─────────────────────────────────────────────────
  const columns: ColumnDef<Finding>[] = [
    {
      key: 'title',
      header: 'Title',
      sortKey: 'title',
      render: (row) => (
        <Tooltip label={row.title} withArrow disabled={row.title.length <= 50}>
          <Text
            size="sm"
            style={{
              maxWidth: 280,
              overflow: 'hidden',
              textOverflow: 'ellipsis',
              whiteSpace: 'nowrap',
              cursor: onFindingClick ? 'pointer' : undefined,
            }}
            onClick={onFindingClick ? () => onFindingClick(row) : undefined}
          >
            {row.title}
          </Text>
        </Tooltip>
      ),
    },
    {
      key: 'severity',
      header: 'Severity',
      sortKey: 'severity',
      render: (row) => (
        <SeverityBadge severity={row.severity as unknown as FindingSeverity} />
      ),
    },
    ...(showDimensionColumn
      ? [
          {
            key: 'dimension',
            header: 'Dimension',
            sortKey: 'dimension' as keyof Finding,
            render: (row: Finding) => (
              <Text size="sm" tt="capitalize">
                {row.dimension.replace(/_/g, ' ')}
              </Text>
            ),
          } as ColumnDef<Finding>,
        ]
      : []),
    {
      key: 'status',
      header: 'Status',
      render: (row) => (
        <Text size="sm">{STATUS_LABELS[row.status] ?? row.status}</Text>
      ),
    },
    {
      key: 'created_at',
      header: 'Created',
      sortKey: 'created_at',
      render: (row) => (
        <Text size="sm" c="dimmed">
          {formatDate(row.created_at)}
        </Text>
      ),
    },
  ];

  // ── Render ─────────────────────────────────────────────────────────────

  // Error state
  if (isError) {
    return (
      <Stack gap="md">
        <SeverityFilterBar
          value={severityFilter}
          onFilterChange={handleFilterChange}
          severityCounts={severityCounts}
        />
        <Alert
          type="error"
          title="Failed to load findings"
          withCloseButton={false}
        >
          <Group gap="xs" align="center">
            <Text size="sm">Unable to fetch findings. Please try again.</Text>
            <Button
              variant="subtle"
              size="xs"
              onClick={() => void refetch()}
            >
              Retry
            </Button>
          </Group>
        </Alert>
      </Stack>
    );
  }

  return (
    <Stack gap="md">
      {/* Severity filter bar */}
      <SeverityFilterBar
        value={severityFilter}
        onFilterChange={handleFilterChange}
        severityCounts={severityCounts}
      />

      {/* Loading spinner */}
      {isLoading && (
        <Group justify="center" py="xl">
          <Loader size="sm" />
          <Text size="sm" c="dimmed">
            Loading findings…
          </Text>
        </Group>
      )}

      {/* Table — DataTable manages its own expand/collapse toggle via renderExpanded */}
      {!isLoading && (
        <Box>
          <DataTable<Finding>
            columns={columns}
            rows={visibleItems}
            rowKey={(r) => r.id}
            sort={sort}
            onSort={handleSort}
            emptyMessage={
              severityFilter !== 'all'
                ? 'No findings match this filter'
                : 'No findings — your service is fully compliant'
            }
            renderExpanded={(row) => (
              <FindingExpandedRow findingId={row.id} />
            )}
          />
        </Box>
      )}

      {/* Cursor-based pagination */}
      {showPagination && !isLoading && (
        <Group justify="space-between" align="center" mt="xs">
          <Button
            variant="default"
            size="sm"
            disabled={isFirstPage}
            onClick={handlePrev}
            aria-label="Previous page"
          >
            ← Previous
          </Button>
          <Text size="sm" c="dimmed">
            {isFirstPage && isLastPage
              ? 'All results'
              : isFirstPage
                ? 'Page 1'
                : `Page ${cursorHistory.length + 1}`}
          </Text>
          <Button
            variant="default"
            size="sm"
            disabled={isLastPage}
            onClick={handleNext}
            aria-label="Next page"
          >
            Next →
          </Button>
        </Group>
      )}
    </Stack>
  );
}
