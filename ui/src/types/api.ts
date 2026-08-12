/**
 * API response types matching backend Pydantic models.
 * Keep in sync with backend schema changes.
 */

// --------------------------------------------------------------------------
// Enums
// --------------------------------------------------------------------------

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
