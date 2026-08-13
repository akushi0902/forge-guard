/**
 * Barrel export for domain-specific findings components.
 *
 * Usage:
 *   import { FindingsTable, SeverityFilterBar, ConfidenceMeter } from '@/components/findings';
 */

export { ConfidenceMeter, type ConfidenceMeterProps } from './ConfidenceMeter';
export {
  SeverityFilterBar,
  type SeverityFilterBarProps,
  type SeverityFilterValue,
  type SeverityCounts,
} from './SeverityFilterBar';
export { FindingExpandedRow, type FindingExpandedRowProps } from './FindingExpandedRow';
export { FindingsTable, type FindingsTableProps } from './FindingsTable';
