/**
 * API response types matching backend Pydantic models.
 * Keep in sync with backend schema changes.
 */

// --------------------------------------------------------------------------
// Enums
// --------------------------------------------------------------------------

export enum PolicyDimension {
  CodeQuality = 'code_quality',
  TestCoverage = 'test_coverage',
  Security = 'security',
  Documentation = 'documentation',
  OperationsReadiness = 'operations_readiness',
}

export enum PolicySeverity {
  Critical = 'critical',
  High = 'high',
  Medium = 'medium',
  Low = 'low',
}

// --------------------------------------------------------------------------
// Policies
// --------------------------------------------------------------------------

export interface PolicyRule {
  id: string;
  name: string;
  dimension: PolicyDimension;
  severity: PolicySeverity;
  threshold: number;
  description: string | null;
  enabled: boolean;
  created_at: string;
  updated_at: string;
}

export interface PolicyRulesResponse {
  items: PolicyRule[];
  cursor: string | null;
  total: number;
}

export interface CreatePolicyRuleBody {
  name: string;
  dimension: PolicyDimension;
  severity: PolicySeverity;
  threshold: number;
  description?: string;
}

export interface UpdatePolicyRuleBody {
  name?: string;
  dimension?: PolicyDimension;
  severity?: PolicySeverity;
  threshold?: number;
  description?: string;
  enabled?: boolean;
}

export interface DimensionWeight {
  dimension: PolicyDimension;
  weight: number;
}

export interface ScoreThresholds {
  approve: { min_health: number; max_risk: number };
  conditional: { min_health: number; max_risk: number };
  block_explanation: string;
}

export enum FindingSeverity {
  Critical = 'critical',
  High = 'high',
  Medium = 'medium',
  Low = 'low',
  Info = 'info',
}

export enum FindingStatus {
  Open = 'open',
  InProgress = 'in_progress',
  Resolved = 'resolved',
  Excepted = 'excepted',
}

export enum DecisionType {
  Approve = 'approve',
  ConditionalApprove = 'conditional_approve',
  Block = 'block',
  Pending = 'pending',
}

// --------------------------------------------------------------------------
// Services
// --------------------------------------------------------------------------

export interface Service {
  id: string;
  name: string;
  description: string | null;
  repository_url: string | null;
  health_score: number | null;
  last_evaluated_at: string | null;
  /** True when this is a demo/simulated service. Defaults to false when absent. */
  is_demo?: boolean;
}

// --------------------------------------------------------------------------
// Scores
// --------------------------------------------------------------------------

export interface DimensionScore {
  name: string;
  score: number;
  weight: number;
  rule_count: number;
  pass_count: number;
}

export interface ServiceScore {
  overall_score: number;
  dimensions: DimensionScore[];
}

// --------------------------------------------------------------------------
// Findings
// --------------------------------------------------------------------------

export interface Finding {
  id: string;
  service_id: string;
  title: string;
  description: string;
  severity: FindingSeverity;
  dimension: string;
  status: FindingStatus;
  created_at: string;
  /** Inherited from the parent service. True when finding belongs to a demo service. */
  is_demo?: boolean;
}

export interface RemediationRecommendation {
  id: string;
  finding_id: string;
  recommendation_text: string;
  implementation_guide: string;
  confidence_score: number;
}

// --------------------------------------------------------------------------
// Releases
// --------------------------------------------------------------------------

export interface ReleaseAssessment {
  id: string;
  service_id: string;
  commit_sha: string;
  pr_reference: string | null;
  status: string;
  risk_score: number | null;
  change_analysis: string | null;
  created_at: string;
  completed_at: string | null;
  /** Inherited from the parent service. True when assessment belongs to a demo service. */
  is_demo?: boolean;
}

export interface ReleaseDecision {
  id: string;
  release_assessment_id: string;
  health_score_at_decision: number;
  risk_score_at_decision: number;
  decision: DecisionType;
  decided_by_role: string;
  rationale: string;
  comment: string | null;
  was_escalated: boolean;
}

// --------------------------------------------------------------------------
// Remediation / Exceptions
// --------------------------------------------------------------------------

export interface Exception {
  id: string;
  finding_id: string;
  justification: string;
  status: string;
  expires_at: string | null;
}

// --------------------------------------------------------------------------
// Pagination
// --------------------------------------------------------------------------

export interface PaginatedResponse<T> {
  items: T[];
  cursor: string | null;
  total_count: number;
}

// --------------------------------------------------------------------------
// Platform Health (WO-081)
// --------------------------------------------------------------------------

/** Response from GET /health — basic liveness check. */
export interface SystemHealthStatus {
  status: string;
  timestamp: string;
  version: string;
}

/** Response from GET /ready — readiness check including database. */
export interface ReadinessCheck {
  status: string;
  database: { status: string; latency_ms: number };
  migration_version: string;
}

/** Response from GET /api/v1/platform/health — aggregated metrics summary. */
export interface PlatformHealthSummary {
  status: string;
  timestamp: string;
  /** % of requests with 2xx status (0–100). */
  api_success_rate: number;
  /** Assessment queue completion rate (0–100). */
  assessment_completion_rate: number;
  /** Audit log write success rate (0–100). */
  audit_log_write_success_rate: number;
  /** DB connection pool utilization as a fraction (0–1). */
  db_connection_pool_utilization: number;
  /** LLM circuit breaker state: 'closed' | 'open' | 'half-open'. */
  llm_circuit_breaker_status: string;
}

/** One data point in the response time time-series chart. */
export interface ResponseTimePoint {
  /** ISO 8601 timestamp for this minute. */
  minute: string;
  /** P50 (median) response latency in milliseconds. */
  p50_ms: number;
}

/** Response from GET /api/v1/platform/metrics — response time history. */
export interface PlatformMetrics {
  response_times: ResponseTimePoint[];
}

/** Single operational log entry shown in RecentLogsCard. */
export interface PlatformLogEntry {
  id: string;
  timestamp: string;
  level: 'info' | 'warn' | 'error';
  service: string;
  message: string;
}

/** Response from GET /api/v1/platform/logs — recent operational log entries. */
export interface PlatformLogsResponse {
  entries: PlatformLogEntry[];
  total: number;
}

// --------------------------------------------------------------------------
// Release Decision Review (WO-075)
// --------------------------------------------------------------------------

/** A single finding embedded in a release assessment's change_analysis. */
export interface ReleaseAssessmentFinding {
  id: string;
  title: string;
  severity: string;
  dimension: string;
  explanation: string | null;
  business_impact: string | null;
  remediation_steps: string[];
  confidence_score: number;
  source: string | null;
}

/** A persisted human decision record returned by the decision view endpoint. */
export interface ReleaseDecisionRecord {
  id: string;
  decided_by: string | null;
  decided_by_role: string | null;
  decision: string;
  rationale: string | null;
  comment: string | null;
  was_escalated: boolean;
  created_at: string;
  /** Health Score recorded at the moment the decision was made. */
  health_score_at_decision?: number | null;
  /** Risk Score recorded at the moment the decision was made. */
  risk_score_at_decision?: number | null;
  /** Conditions that must be met before deployment (for CONDITIONAL_APPROVE). */
  conditions?: string[] | null;
}

/** Full combined decision view from GET /api/v1/releases/{id}/decision. */
export interface CombinedDecisionView {
  assessment: {
    id: string;
    service_id: string;
    commit_sha: string | null;
    pr_reference: string | null;
    status: string;
    created_at: string;
    completed_at: string | null;
    /** True when the parent service is a demo/simulated service. */
    is_demo?: boolean;
    /** Change analysis JSONB from the assessment pipeline. */
    change_analysis?: Record<string, unknown> | null;
  };
  system_recommendation: {
    decision: string;
  };
  health_score: {
    overall: number;
    dimensions: { name: string; score: number; rule_count: number; pass_count: number }[];
  } | null;
  risk_score: {
    overall: number;
    contributing_factors: { factor: string; impact: string; weight: number }[];
  } | null;
  findings_summary: {
    total: number;
    by_severity: Record<string, { count: number; items: ReleaseAssessmentFinding[] }>;
  };
  escalation: {
    is_escalated: boolean;
    reasons: { finding_id: string; title: string }[] | null;
  };
  decision_record: ReleaseDecisionRecord | null;
  scoring_incomplete: boolean;
  scoring_incomplete_reason: string | null;
}

// --------------------------------------------------------------------------
// Engineering Manager Dashboard (WO-078)
// --------------------------------------------------------------------------

export type TrendDirection = 'up' | 'down' | 'stable';

/** Service with aggregated metrics for the Engineering Manager dashboard. */
export interface ServiceWithMetrics {
  id: string;
  name: string;
  team: string;
  description: string | null;
  repository_url: string | null;
  health_score: number | null;
  previous_health_score: number | null;
  trend_direction: TrendDirection;
  last_evaluated_at: string | null;
  critical_findings: number;
  high_findings: number;
  medium_findings: number;
  low_findings: number;
  avg_ttr_hours: number | null;
}

export interface ServicesWithMetricsResponse {
  items: ServiceWithMetrics[];
  total_count: number;
}

/** Single monthly data point for the health score trend chart. */
export interface AssessmentTrendPoint {
  month: string;
  avg_score: number;
  assessment_count: number;
}

/** Single monthly data point for the resolution rate chart. */
export interface ResolutionRatePoint {
  month: string;
  resolved_count: number;
  total_count: number;
  resolution_rate: number;
}

export interface AssessmentTrendsResponse {
  trends: AssessmentTrendPoint[];
  resolution_rates: ResolutionRatePoint[];
}
