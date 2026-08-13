/**
 * Mock data fixtures for component tests.
 *
 * All data is synthetic and safe for test environments.
 */

import {
  type Assessment,
  type DimensionScore,
  type Finding,
  type HealthScore,
  type Service,
  type User,
  Role,
} from '@/types';

// ---------------------------------------------------------------------------
// Services
// ---------------------------------------------------------------------------

export const mockServices: Service[] = [
  {
    id: 'svc-001',
    name: 'payment-api',
    team: 'Platform',
    repositoryUrl: 'https://github.com/acme/payment-api',
    lastEvaluatedAt: '2024-08-01T10:00:00Z',
  },
  {
    id: 'svc-002',
    name: 'auth-service',
    team: 'Security',
    repositoryUrl: 'https://github.com/acme/auth-service',
    lastEvaluatedAt: '2024-08-02T09:30:00Z',
  },
  {
    id: 'svc-003',
    name: 'notification-service',
    team: 'Messaging',
    repositoryUrl: 'https://github.com/acme/notification-service',
    lastEvaluatedAt: null,
  },
];

// ---------------------------------------------------------------------------
// Users
// ---------------------------------------------------------------------------

export const mockUsers: User[] = [
  {
    id: 'usr-001',
    email: 'alice@example.com',
    displayName: 'Alice Chen',
    role: Role.TechLead,
    createdAt: '2024-01-01T00:00:00Z',
  },
  {
    id: 'usr-002',
    email: 'bob@example.com',
    displayName: 'Bob Smith',
    role: Role.Developer,
    createdAt: '2024-01-02T00:00:00Z',
  },
  {
    id: 'usr-003',
    email: 'carol@example.com',
    displayName: 'Carol Jones',
    role: Role.SecurityReviewer,
    createdAt: '2024-01-03T00:00:00Z',
  },
];

// ---------------------------------------------------------------------------
// Health scores
// ---------------------------------------------------------------------------

export const mockDimensionScores: DimensionScore[] = [
  {
    dimension: 'test_coverage',
    score: 82,
    weight: 0.25,
    passingRules: 8,
    totalRules: 10,
  },
  {
    dimension: 'security',
    score: 71,
    weight: 0.30,
    passingRules: 6,
    totalRules: 8,
  },
  {
    dimension: 'documentation',
    score: 95,
    weight: 0.15,
    passingRules: 5,
    totalRules: 5,
  },
  {
    dimension: 'dependency_health',
    score: 88,
    weight: 0.20,
    passingRules: 7,
    totalRules: 8,
  },
  {
    dimension: 'code_quality',
    score: 76,
    weight: 0.10,
    passingRules: 4,
    totalRules: 5,
  },
];

export const mockHealthScore: HealthScore = {
  id: 'hs-001',
  serviceId: 'svc-001',
  overallScore: 82,
  dimensions: mockDimensionScores,
  evaluatedAt: '2024-08-01T10:00:00Z',
};

// ---------------------------------------------------------------------------
// Findings
// ---------------------------------------------------------------------------

export const mockFindings: Finding[] = [
  {
    id: 'fnd-001',
    serviceId: 'svc-001',
    policyRuleId: 'rule-sec-01',
    dimension: 'security',
    severity: 'critical',
    title: 'Hardcoded credentials detected',
    description: 'AWS access key found in source code.',
    status: 'open',
    detectedAt: '2024-08-01T08:00:00Z',
    resolvedAt: null,
  },
  {
    id: 'fnd-002',
    serviceId: 'svc-001',
    policyRuleId: 'rule-test-01',
    dimension: 'test_coverage',
    severity: 'high',
    title: 'Test coverage below 80% threshold',
    description: 'Current coverage: 67%. Minimum required: 80%.',
    status: 'open',
    detectedAt: '2024-08-01T08:00:00Z',
    resolvedAt: null,
  },
  {
    id: 'fnd-003',
    serviceId: 'svc-001',
    policyRuleId: 'rule-dep-01',
    dimension: 'dependency_health',
    severity: 'medium',
    title: 'Outdated dependency with known vulnerability',
    description: 'lodash@4.17.20 — CVE-2021-23337.',
    status: 'in_progress',
    detectedAt: '2024-07-25T08:00:00Z',
    resolvedAt: null,
  },
  {
    id: 'fnd-004',
    serviceId: 'svc-001',
    policyRuleId: 'rule-doc-01',
    dimension: 'documentation',
    severity: 'low',
    title: 'Missing API documentation for 3 endpoints',
    description: 'OpenAPI spec missing for POST /refunds, DELETE /cards endpoints.',
    status: 'open',
    detectedAt: '2024-07-30T08:00:00Z',
    resolvedAt: null,
  },
  {
    id: 'fnd-005',
    serviceId: 'svc-001',
    policyRuleId: 'rule-info-01',
    dimension: 'code_quality',
    severity: 'info',
    title: 'Deprecated API usage detected',
    description: 'Function foo() is deprecated; use bar() instead.',
    status: 'resolved',
    detectedAt: '2024-07-20T08:00:00Z',
    resolvedAt: '2024-08-01T09:00:00Z',
  },
];

// Severity distribution summary
export const mockSeverityDistribution = {
  critical: 1,
  high: 1,
  medium: 1,
  low: 1,
  info: 1,
};

// ---------------------------------------------------------------------------
// Assessments
// ---------------------------------------------------------------------------

export const mockAssessments: Assessment[] = [
  {
    id: 'asmnt-001',
    serviceId: 'svc-001',
    commitSha: 'a3f5e1b0c2d4e6f8a0b2c4d6e8f0a2b4c6d8e0f2',
    prUrl: 'https://github.com/acme/payment-api/pull/42',
    riskScore: 73,
    healthScore: 82,
    decision: 'conditional_approve',
    aiExplanation:
      'The PR introduces changes to the payment processing module which carries moderate risk.',
    createdAt: '2024-08-01T10:30:00Z',
  },
  {
    id: 'asmnt-002',
    serviceId: 'svc-002',
    commitSha: 'b4e6f8a0b2c4d6e8f0a2b4c6d8e0f2a3f5e1b0c2',
    prUrl: null,
    riskScore: 15,
    healthScore: 94,
    decision: 'approve',
    aiExplanation: 'Low-risk documentation update with no functional changes.',
    createdAt: '2024-08-02T11:00:00Z',
  },
];

// ---------------------------------------------------------------------------
// Score objects
// ---------------------------------------------------------------------------

export const mockScoreObjects = {
  perfect: { score: 100, label: 'Perfect score' },
  high: { score: 87, label: 'High score' },
  medium: { score: 55, label: 'Medium score' },
  low: { score: 32, label: 'Low score' },
  zero: { score: 0, label: 'Zero score' },
};
