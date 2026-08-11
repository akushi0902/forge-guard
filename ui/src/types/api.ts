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
