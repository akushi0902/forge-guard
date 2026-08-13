import {
  PolicyDimension,
  PolicySeverity,
  type DimensionWeight,
  type PolicyRule,
  type PolicyRulesResponse,
  type ScoreThresholds,
} from '@/types/api';

export const POLICY_RULE_FIXTURES: PolicyRule[] = [
  {
    id: 'pol-001',
    name: 'No critical SQL injection vulnerabilities',
    dimension: PolicyDimension.Security,
    severity: PolicySeverity.Critical,
    threshold: 0,
    description: 'Any critical SQL injection finding blocks release.',
    enabled: true,
    created_at: '2026-07-01T10:00:00Z',
    updated_at: '2026-07-01T10:00:00Z',
  },
  {
    id: 'pol-002',
    name: 'Minimum 80% unit test coverage',
    dimension: PolicyDimension.TestCoverage,
    severity: PolicySeverity.High,
    threshold: 80,
    description: 'Services must maintain at least 80% unit test coverage.',
    enabled: true,
    created_at: '2026-07-02T10:00:00Z',
    updated_at: '2026-07-05T14:00:00Z',
  },
  {
    id: 'pol-003',
    name: 'No unused dependencies',
    dimension: PolicyDimension.CodeQuality,
    severity: PolicySeverity.Medium,
    threshold: 0,
    description: 'Unused dependencies increase attack surface and bloat builds.',
    enabled: true,
    created_at: '2026-07-03T10:00:00Z',
    updated_at: '2026-07-03T10:00:00Z',
  },
  {
    id: 'pol-004',
    name: 'API documentation coverage',
    dimension: PolicyDimension.Documentation,
    severity: PolicySeverity.Low,
    threshold: 90,
    description: 'All public API endpoints must have OpenAPI documentation.',
    enabled: true,
    created_at: '2026-07-04T10:00:00Z',
    updated_at: '2026-07-04T10:00:00Z',
  },
  {
    id: 'pol-005',
    name: 'Health check endpoint required',
    dimension: PolicyDimension.OperationsReadiness,
    severity: PolicySeverity.High,
    threshold: 0,
    description: 'All services must expose a /health endpoint for liveness checks.',
    enabled: false,
    created_at: '2026-07-05T10:00:00Z',
    updated_at: '2026-07-08T09:00:00Z',
  },
  {
    id: 'pol-006',
    name: 'No hardcoded secrets in source',
    dimension: PolicyDimension.Security,
    severity: PolicySeverity.Critical,
    threshold: 0,
    description: 'Secrets must be managed via environment variables or a secrets manager.',
    enabled: true,
    created_at: '2026-07-06T10:00:00Z',
    updated_at: '2026-07-06T10:00:00Z',
  },
];

export const POLICY_RULES_RESPONSE_FIXTURE: PolicyRulesResponse = {
  items: POLICY_RULE_FIXTURES,
  cursor: null,
  total: POLICY_RULE_FIXTURES.length,
};

export const DIMENSION_WEIGHTS_FIXTURE: DimensionWeight[] = [
  { dimension: PolicyDimension.Security, weight: 30 },
  { dimension: PolicyDimension.TestCoverage, weight: 25 },
  { dimension: PolicyDimension.CodeQuality, weight: 20 },
  { dimension: PolicyDimension.Documentation, weight: 15 },
  { dimension: PolicyDimension.OperationsReadiness, weight: 10 },
];

export const SCORE_THRESHOLDS_FIXTURE: ScoreThresholds = {
  approve: { min_health: 70, max_risk: 30 },
  conditional: { min_health: 50, max_risk: 60 },
  block_explanation: 'Services scoring below the conditional threshold are blocked from release.',
};
