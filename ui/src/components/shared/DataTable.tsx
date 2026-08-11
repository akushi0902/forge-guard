/**
 * DataTable — generic, sortable, paginated data table.
 *
 * Features:
 *   - Generic row type via TypeScript generics
 *   - Sortable columns (aria-sort attributes for accessibility)
 *   - Cursor-based pagination (cursor + limit parameters)
 *   - Expandable rows via optional renderExpanded prop
 *   - Empty-state fallback when rows is empty
 */

import {
  Box,
  Pagination,
  Table,
  type TableProps,
  Text,
  UnstyledButton,
  Group,
  Collapse,
} from '@mantine/core';
import { useState, type ReactNode } from 'react';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface ColumnDef<T> {
  /** Unique key for the column. */
  key: string;
  /** Column header label. */
  header: string;
  /** If provided the column header becomes a sort trigger. */
  sortKey?: keyof T;
  /** Render function for the cell content. Defaults to `String(row[key])`. */
  render?: (row: T, index: number) => ReactNode;
  /** Optional additional class for the th/td. */
  className?: string;
}

export interface SortState<T> {
  key: keyof T;
  direction: 'asc' | 'desc';
}

export interface DataTableProps<T> extends Omit<TableProps, 'children'> {
  /** Column definitions. */
  columns: ColumnDef<T>[];
  /** Row data to display. */
  rows: T[];
  /** Key extractor — must return a unique string for each row. */
  rowKey: (row: T) => string;
  /** Optional expandable row renderer. */
  renderExpanded?: (row: T) => ReactNode;
  /** Total number of items (used for pagination). */
  totalItems?: number;
  /** Items per page (default 20). */
  pageSize?: number;
  /** Controlled page (1-indexed). */
  page?: number;
  /** Called when the user navigates to a different page. */
  onPageChange?: (page: number) => void;
  /** Called when the user clicks a sortable column header. */
  onSort?: (sort: SortState<T>) => void;
  /** Current sort state (controlled). */
  sort?: SortState<T>;
  /** Message shown when rows is empty. */
  emptyMessage?: string;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

/**
 * @example
 * const columns: ColumnDef<Finding>[] = [
 *   { key: 'title', header: 'Title', sortKey: 'title' },
 *   { key: 'severity', header: 'Severity', render: (r) => <SeverityBadge severity={r.severity} /> },
 * ];
 * <DataTable columns={columns} rows={findings} rowKey={(r) => r.id} />
 */
export function DataTable<T>({
  columns,
  rows,
  rowKey,
  renderExpanded,
  totalItems,
  pageSize = 20,
  page = 1,
  onPageChange,
  onSort,
  sort,
  emptyMessage = 'No data to display.',
  ...tableProps
}: DataTableProps<T>) {
  const [expandedRows, setExpandedRows] = useState<Set<string>>(new Set());

  const toggleRow = (key: string) => {
    setExpandedRows((prev) => {
      const next = new Set(prev);
      if (next.has(key)) {
        next.delete(key);
      } else {
        next.add(key);
      }
      return next;
    });
  };

  const handleSort = (colKey: keyof T) => {
    if (!onSort) return;
    const newDirection =
      sort?.key === colKey && sort?.direction === 'asc' ? 'desc' : 'asc';
    onSort({ key: colKey, direction: newDirection });
  };

  const totalPages = totalItems ? Math.ceil(totalItems / pageSize) : undefined;

  const ariaSort = (colKey: keyof T | undefined): 'ascending' | 'descending' | 'none' => {
    if (!colKey || !sort || sort.key !== colKey) return 'none';
    return sort.direction === 'asc' ? 'ascending' : 'descending';
  };

  return (
    <Box>
      <Table {...tableProps} aria-label="Data table">
        <Table.Thead>
          <Table.Tr>
            {renderExpanded && <Table.Th style={{ width: 40 }} />}
            {columns.map((col) => (
              <Table.Th
                key={col.key}
                className={col.className}
                aria-sort={col.sortKey ? ariaSort(col.sortKey) : undefined}
              >
                {col.sortKey ? (
                  <UnstyledButton
                    onClick={() => handleSort(col.sortKey as keyof T)}
                    style={{ fontWeight: 600, cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 4 }}
                  >
                    {col.header}
                    {sort?.key === col.sortKey && (
                      <span aria-hidden="true">
                        {sort.direction === 'asc' ? ' ↑' : ' ↓'}
                      </span>
                    )}
                  </UnstyledButton>
                ) : (
                  col.header
                )}
              </Table.Th>
            ))}
          </Table.Tr>
        </Table.Thead>
        <Table.Tbody>
          {rows.length === 0 ? (
            <Table.Tr>
              <Table.Td colSpan={columns.length + (renderExpanded ? 1 : 0)}>
                <Text ta="center" c="dimmed" py="xl">
                  {emptyMessage}
                </Text>
              </Table.Td>
            </Table.Tr>
          ) : (
            rows.map((row, idx) => {
              const key = rowKey(row);
              const isExpanded = expandedRows.has(key);
              return (
                <>
                  <Table.Tr
                    key={key}
                    style={renderExpanded ? { cursor: 'pointer' } : undefined}
                    onClick={renderExpanded ? () => toggleRow(key) : undefined}
                    aria-expanded={renderExpanded ? isExpanded : undefined}
                  >
                    {renderExpanded && (
                      <Table.Td>
                        <span aria-hidden="true">{isExpanded ? '▾' : '▸'}</span>
                      </Table.Td>
                    )}
                    {columns.map((col) => (
                      <Table.Td key={col.key} className={col.className}>
                        {col.render
                          ? col.render(row, idx)
                          : String((row as Record<string, unknown>)[col.key] ?? '')}
                      </Table.Td>
                    ))}
                  </Table.Tr>
                  {renderExpanded && isExpanded && (
                    <Table.Tr key={`${key}-expanded`}>
                      <Table.Td colSpan={columns.length + 1}>
                        <Collapse in={isExpanded}>
                          {renderExpanded(row)}
                        </Collapse>
                      </Table.Td>
                    </Table.Tr>
                  )}
                </>
              );
            })
          )}
        </Table.Tbody>
      </Table>

      {totalPages && totalPages > 1 && onPageChange && (
        <Group justify="center" mt="md">
          <Pagination
            total={totalPages}
            value={page}
            onChange={onPageChange}
            size="sm"
          />
        </Group>
      )}
    </Box>
  );
}
