import { describe, expect, it } from 'vitest';
import { buildServicesCsv } from '@/utils/csvExport';
import { SERVICES_WITH_METRICS } from '@/test/fixtures/managerDashboardData';

describe('buildServicesCsv', () => {
  it('starts with a header row containing all required columns', () => {
    const csv = buildServicesCsv(SERVICES_WITH_METRICS);
    const headerRow = csv.split('\n')[0]!;
    expect(headerRow).toContain('Service Name');
    expect(headerRow).toContain('Team');
    expect(headerRow).toContain('Health Score');
    expect(headerRow).toContain('Trend');
    expect(headerRow).toContain('Critical Findings');
    expect(headerRow).toContain('High Findings');
  });

  it('does not include PII fields (id, repository_url, description)', () => {
    const csv = buildServicesCsv(SERVICES_WITH_METRICS);
    expect(csv).not.toContain('svc-001');
    expect(csv).not.toContain('github.com/org');
    // "payment-service service" is the description — should not appear
    expect(csv).not.toContain('payment-service service');
  });

  it('includes service names in the data rows', () => {
    const csv = buildServicesCsv(SERVICES_WITH_METRICS);
    expect(csv).toContain('payment-service');
    expect(csv).toContain('auth-service');
  });

  it('includes team names in the data rows', () => {
    const csv = buildServicesCsv(SERVICES_WITH_METRICS);
    expect(csv).toContain('payments');
    expect(csv).toContain('platform');
  });

  it('produces correct row count (header + one row per service)', () => {
    const csv = buildServicesCsv(SERVICES_WITH_METRICS);
    const rows = csv.split('\n').filter(Boolean);
    expect(rows).toHaveLength(SERVICES_WITH_METRICS.length + 1);
  });

  it('returns only the header row for an empty array', () => {
    const csv = buildServicesCsv([]);
    const rows = csv.split('\n').filter(Boolean);
    expect(rows).toHaveLength(1);
  });

  it('escapes service names containing commas', () => {
    const svcWithComma = {
      ...SERVICES_WITH_METRICS[0]!,
      name: 'service, with comma',
    };
    const csv = buildServicesCsv([svcWithComma]);
    expect(csv).toContain('"service, with comma"');
  });

  it('escapes service names containing double quotes', () => {
    const svcWithQuote = {
      ...SERVICES_WITH_METRICS[0]!,
      name: 'service "quoted" name',
    };
    const csv = buildServicesCsv([svcWithQuote]);
    expect(csv).toContain('"service ""quoted"" name"');
  });

  it('shows N/A for null health score', () => {
    const svcNoScore = {
      ...SERVICES_WITH_METRICS[0]!,
      health_score: null,
    };
    const csv = buildServicesCsv([svcNoScore]);
    expect(csv).toContain('N/A');
  });
});
