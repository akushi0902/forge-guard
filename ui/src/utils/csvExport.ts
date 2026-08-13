import { type ServiceWithMetrics } from '@/types/api';

/**
 * Escapes a CSV field value: wraps in quotes if it contains commas, quotes,
 * or newlines, and doubles any internal double-quote characters.
 */
function escapeCsvField(value: string | number | null): string {
  if (value === null || value === undefined) return '';
  const str = String(value);
  if (str.includes(',') || str.includes('"') || str.includes('\n')) {
    return `"${str.replace(/"/g, '""')}"`;
  }
  return str;
}

function buildCsvRow(fields: (string | number | null)[]): string {
  return fields.map(escapeCsvField).join(',');
}

/** CSV headers — no PII, only service names, scores, and finding counts. */
const CSV_HEADERS = [
  'Service Name',
  'Team',
  'Health Score',
  'Trend',
  'Critical Findings',
  'High Findings',
  'Medium Findings',
  'Low Findings',
  'Avg TTR (hours)',
  'Last Evaluated',
];

/**
 * Converts an array of ServiceWithMetrics to a CSV string.
 * Excludes PII fields (repository_url, description, id).
 */
export function buildServicesCsv(services: ServiceWithMetrics[]): string {
  const header = CSV_HEADERS.join(',');
  const rows = services.map((s) =>
    buildCsvRow([
      s.name,
      s.team,
      s.health_score ?? 'N/A',
      s.trend_direction,
      s.critical_findings,
      s.high_findings,
      s.medium_findings,
      s.low_findings,
      s.avg_ttr_hours ?? 'N/A',
      s.last_evaluated_at ? new Date(s.last_evaluated_at).toLocaleDateString() : 'Never',
    ]),
  );
  return [header, ...rows].join('\n');
}

/**
 * Triggers a CSV file download in the browser.
 * @param csv    — CSV string content
 * @param filename — suggested filename (without extension)
 */
export function downloadCsv(csv: string, filename: string): void {
  const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = `${filename}.csv`;
  document.body.appendChild(anchor);
  anchor.click();
  document.body.removeChild(anchor);
  URL.revokeObjectURL(url);
}
