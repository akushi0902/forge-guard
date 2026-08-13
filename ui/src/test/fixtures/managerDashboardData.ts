import {
  type ServiceWithMetrics,
  type ServicesWithMetricsResponse,
  type AssessmentTrendsResponse,
} from '@/types/api';

// ---------------------------------------------------------------------------
// 20 services across 4 teams with varied scores
// ---------------------------------------------------------------------------

const TEAMS = ['platform', 'payments', 'auth', 'data'] as const;

function svc(
  id: string,
  name: string,
  team: (typeof TEAMS)[number],
  health_score: number | null,
  prev: number | null,
  crit: number,
  high: number,
  med: number,
  low: number,
  ttr: number | null,
): ServiceWithMetrics {
  const trend =
    health_score == null || prev == null
      ? 'stable'
      : health_score > prev
        ? 'up'
        : health_score < prev
          ? 'down'
          : 'stable';
  return {
    id,
    name,
    team,
    description: `${name} service`,
    repository_url: `https://github.com/org/${name}`,
    health_score,
    previous_health_score: prev,
    trend_direction: trend,
    last_evaluated_at: '2026-08-11T09:00:00Z',
    critical_findings: crit,
    high_findings: high,
    medium_findings: med,
    low_findings: low,
    avg_ttr_hours: ttr,
  };
}

export const SERVICES_WITH_METRICS: ServiceWithMetrics[] = [
  svc('svc-001', 'payment-service',    'payments',  85, 80, 1, 2, 3, 5,  24),
  svc('svc-002', 'auth-service',       'auth',       91, 88, 0, 1, 2, 4,  12),
  svc('svc-003', 'user-service',       'auth',       72, 75, 0, 2, 4, 6,  18),
  svc('svc-004', 'notification-svc',   'platform',   55, 50, 2, 3, 5, 8,  36),
  svc('svc-005', 'api-gateway',        'platform',   88, 86, 0, 0, 1, 3,   8),
  svc('svc-006', 'data-pipeline',      'data',       45, 52, 3, 4, 6, 10, 72),
  svc('svc-007', 'analytics-service',  'data',       78, 74, 0, 1, 3, 4,  20),
  svc('svc-008', 'billing-service',    'payments',   62, 60, 1, 2, 3, 5,  30),
  svc('svc-009', 'reporting-service',  'platform',   93, 90, 0, 0, 1, 2,   6),
  svc('svc-010', 'search-service',     'data',       38, 42, 4, 5, 7, 9,  96),
  svc('svc-011', 'cache-service',      'platform',   80, 80, 0, 1, 2, 3,  15),
  svc('svc-012', 'file-storage-svc',   'data',       67, 65, 1, 2, 4, 6,  28),
  svc('svc-013', 'email-service',      'platform',   74, 70, 0, 1, 2, 4,  22),
  svc('svc-014', 'fraud-detection',    'payments',   89, 85, 0, 0, 1, 2,  10),
  svc('svc-015', 'kyc-service',        'auth',       76, 78, 0, 1, 3, 5,  16),
  svc('svc-016', 'ledger-service',     'payments',   83, 80, 0, 1, 2, 3,  14),
  svc('svc-017', 'config-service',     'platform',   96, 95, 0, 0, 0, 1,   4),
  svc('svc-018', 'event-bus',          'data',       70, 68, 0, 1, 2, 4,  20),
  svc('svc-019', 'metrics-collector',  'platform',   82, 82, 0, 1, 1, 3,  12),
  svc('svc-020', 'audit-service',      'platform',   null, null, 0, 0, 0, 0, null),
];

export const SERVICES_WITH_METRICS_RESPONSE: ServicesWithMetricsResponse = {
  items: SERVICES_WITH_METRICS,
  total_count: SERVICES_WITH_METRICS.length,
};

export const EMPTY_SERVICES_RESPONSE: ServicesWithMetricsResponse = {
  items: [],
  total_count: 0,
};

// ---------------------------------------------------------------------------
// 6 months of assessment trend data
// ---------------------------------------------------------------------------

export const ASSESSMENT_TRENDS_RESPONSE: AssessmentTrendsResponse = {
  trends: [
    { month: 'Mar 2026', avg_score: 68, assessment_count: 45 },
    { month: 'Apr 2026', avg_score: 71, assessment_count: 52 },
    { month: 'May 2026', avg_score: 74, assessment_count: 58 },
    { month: 'Jun 2026', avg_score: 72, assessment_count: 61 },
    { month: 'Jul 2026', avg_score: 76, assessment_count: 67 },
    { month: 'Aug 2026', avg_score: 79, assessment_count: 70 },
  ],
  resolution_rates: [
    { month: 'Mar 2026', resolved_count: 28, total_count: 45, resolution_rate: 62.2 },
    { month: 'Apr 2026', resolved_count: 35, total_count: 50, resolution_rate: 70.0 },
    { month: 'May 2026', resolved_count: 42, total_count: 55, resolution_rate: 76.4 },
    { month: 'Jun 2026', resolved_count: 38, total_count: 48, resolution_rate: 79.2 },
    { month: 'Jul 2026', resolved_count: 50, total_count: 60, resolution_rate: 83.3 },
    { month: 'Aug 2026', resolved_count: 48, total_count: 55, resolution_rate: 87.3 },
  ],
};

export const EMPTY_TRENDS_RESPONSE: AssessmentTrendsResponse = {
  trends: [],
  resolution_rates: [],
};
