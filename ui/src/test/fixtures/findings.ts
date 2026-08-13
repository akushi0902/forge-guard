import { FindingSeverity, FindingStatus, type Finding, type PaginatedResponse } from '@/types/api';

export const CRITICAL_FINDING: Finding = {
  id: 'fnd-crit-001',
  service_id: 'svc-001',
  title: 'Hardcoded credentials detected',
  description: 'AWS access key found in source code.',
  severity: FindingSeverity.Critical,
  dimension: 'security',
  status: FindingStatus.Open,
  created_at: '2026-08-10T08:00:00Z',
};

export const HIGH_FINDING: Finding = {
  id: 'fnd-high-001',
  service_id: 'svc-001',
  title: 'Test coverage below 80% threshold',
  description: 'Current coverage: 67%. Minimum required: 80%.',
  severity: FindingSeverity.High,
  dimension: 'test_coverage',
  status: FindingStatus.Open,
  created_at: '2026-08-10T09:00:00Z',
};

export const MEDIUM_FINDING: Finding = {
  id: 'fnd-med-001',
  service_id: 'svc-001',
  title: 'Outdated dependency with known vulnerability',
  description: 'lodash@4.17.20 — CVE-2021-23337.',
  severity: FindingSeverity.Medium,
  dimension: 'security',
  status: FindingStatus.InProgress,
  created_at: '2026-08-09T10:00:00Z',
};

export const LOW_FINDING: Finding = {
  id: 'fnd-low-001',
  service_id: 'svc-001',
  title: 'Missing API documentation',
  description: 'OpenAPI spec missing for 3 endpoints.',
  severity: FindingSeverity.Low,
  dimension: 'documentation',
  status: FindingStatus.Open,
  created_at: '2026-08-08T11:00:00Z',
};

export const MIXED_FINDINGS: Finding[] = [
  CRITICAL_FINDING,
  HIGH_FINDING,
  MEDIUM_FINDING,
  LOW_FINDING,
];

export const MIXED_FINDINGS_PAGINATED: PaginatedResponse<Finding> = {
  items: MIXED_FINDINGS,
  cursor: null,
  total_count: 4,
};

export const EMPTY_FINDINGS_PAGINATED: PaginatedResponse<Finding> = {
  items: [],
  cursor: null,
  total_count: 0,
};

export const CRITICAL_FINDINGS_PAGINATED: PaginatedResponse<Finding> = {
  items: [CRITICAL_FINDING],
  cursor: null,
  total_count: 1,
};

export const HIGH_FINDINGS_PAGINATED: PaginatedResponse<Finding> = {
  items: [HIGH_FINDING],
  cursor: null,
  total_count: 1,
};

export const MEDIUM_FINDINGS_PAGINATED: PaginatedResponse<Finding> = {
  items: [MEDIUM_FINDING],
  cursor: null,
  total_count: 1,
};

export const LOW_FINDINGS_PAGINATED: PaginatedResponse<Finding> = {
  items: [LOW_FINDING],
  cursor: null,
  total_count: 1,
};

// ---------------------------------------------------------------------------
// Paginated multi-page fixtures for pagination tests
// ---------------------------------------------------------------------------

/** Page 1 of 2: returns a cursor so the Next button is enabled. */
export const PAGE_1_FINDINGS: Finding[] = [
  {
    id: 'fnd-p1-001',
    service_id: 'svc-001',
    title: 'SQL injection risk in query builder',
    description: 'User input not sanitised before passing to SQL query.',
    severity: FindingSeverity.Critical,
    dimension: 'security',
    status: FindingStatus.Open,
    created_at: '2026-08-12T07:00:00Z',
  },
  {
    id: 'fnd-p1-002',
    service_id: 'svc-001',
    title: 'Missing health check endpoint',
    description: '/health endpoint not implemented.',
    severity: FindingSeverity.High,
    dimension: 'operations_readiness',
    status: FindingStatus.Open,
    created_at: '2026-08-12T06:00:00Z',
  },
];

export const PAGE_1_FINDINGS_PAGINATED: PaginatedResponse<Finding> = {
  items: PAGE_1_FINDINGS,
  cursor: 'cursor-page-2',
  total_count: 4,
};

/** Page 2 of 2: no cursor returned, so Next button is disabled. */
export const PAGE_2_FINDINGS: Finding[] = [
  {
    id: 'fnd-p2-001',
    service_id: 'svc-001',
    title: 'Outdated base image in Dockerfile',
    description: 'Base image is 18 months old.',
    severity: FindingSeverity.Medium,
    dimension: 'operations_readiness',
    status: FindingStatus.Open,
    created_at: '2026-08-11T05:00:00Z',
  },
  {
    id: 'fnd-p2-002',
    service_id: 'svc-001',
    title: 'No README contributing guide',
    description: 'CONTRIBUTING.md not present.',
    severity: FindingSeverity.Low,
    dimension: 'documentation',
    status: FindingStatus.Open,
    created_at: '2026-08-11T04:00:00Z',
  },
];

export const PAGE_2_FINDINGS_PAGINATED: PaginatedResponse<Finding> = {
  items: PAGE_2_FINDINGS,
  cursor: null,
  total_count: 4,
};
