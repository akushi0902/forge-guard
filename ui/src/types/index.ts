/**
 * Shared TypeScript interfaces for the ForgeGuard domain model.
 *
 * These types mirror the Pydantic response schemas in the backend. Keep them
 * in sync with any backend schema changes.
 */

// --------------------------------------------------------------------------
// RBAC
// --------------------------------------------------------------------------

export enum Role {
  Developer = 'developer',
  TechLead = 'tech_lead',
  SecurityReviewer = 'security_reviewer',
  PlatformAdmin = 'platform_admin',
  EngineeringManager = 'engineering_manager',
  Operator = 'operator',
}

export interface User {
  id: string;
  email: string;
  displayName: string;
  role: Role;
  permissions: string[];
  createdAt: string;
}

// --------------------------------------------------------------------------
// Services
// --------------------------------------------------------------------------

export interface Service {
  id: string;
  name: string;
  team: string;
  repositoryUrl: string;
  lastEvaluatedAt: string | null;
}

// --------------------------------------------------------------------------
// Health Scores
// --------------------------------------------------------------------------

export type ScoreDimension =
  | 'test_coverage'
  | 'documentation'
  | 'security'
  | 'dependency_health'
  | 'code_quality';

export interface DimensionScore {
  dimension: ScoreDimension;
  score: number;
  weight: number;
  passingRules: number;
  totalRules: number;
}

export interface HealthScore {
  id: string;
  serviceId: string;
  overallScore: number;
  dimensions: DimensionScore[];
  evaluatedAt: string;
}

// --------------------------------------------------------------------------
// Findings
// --------------------------------------------------------------------------

export type FindingSeverity = 'critical' | 'high' | 'medium' | 'low' | 'info';
export type FindingStatus = 'open' | 'in_progress' | 'resolved' | 'excepted';

export interface Finding {
  id: string;
  serviceId: string;
  policyRuleId: string;
  dimension: ScoreDimension;
  severity: FindingSeverity;
  title: string;
  description: string;
  status: FindingStatus;
  detectedAt: string;
  resolvedAt: string | null;
}

// --------------------------------------------------------------------------
// Release Assessments
// --------------------------------------------------------------------------

export type DecisionOutcome = 'approve' | 'conditional_approve' | 'block' | 'pending';

export interface Assessment {
  id: string;
  serviceId: string;
  commitSha: string;
  prUrl: string | null;
  riskScore: number;
  healthScore: number;
  decision: DecisionOutcome;
  aiExplanation: string | null;
  createdAt: string;
}

export interface ReleaseDecision {
  id: string;
  assessmentId: string;
  outcome: DecisionOutcome;
  rationale: string;
  decidedBy: string;
  decidedAt: string;
  conditions: string[];
}

// --------------------------------------------------------------------------
// API response envelope
// --------------------------------------------------------------------------

export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  page: number;
  pageSize: number;
  totalPages: number;
}

export interface ApiError {
  detail: string;
  requestId: string | null;
  statusCode: number;
}
