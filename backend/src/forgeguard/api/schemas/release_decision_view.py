"""Pydantic response schemas for GET /api/v1/releases/{id}/decision (WO-052)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel


# ---------------------------------------------------------------------------
# Nested models
# ---------------------------------------------------------------------------


class AssessmentMetadata(BaseModel):
    id: uuid.UUID
    service_id: uuid.UUID
    commit_sha: Optional[str] = None
    pr_reference: Optional[str] = None
    status: str
    created_at: datetime
    completed_at: Optional[datetime] = None


class SystemRecommendation(BaseModel):
    decision: str
    threshold_config_id: Optional[uuid.UUID] = None
    threshold_config_name: Optional[str] = None


class DimensionBreakdown(BaseModel):
    name: str
    score: float
    rule_count: int
    pass_count: int


class HealthScoreBreakdown(BaseModel):
    overall: float
    dimensions: list[DimensionBreakdown] = []


class ContributingFactor(BaseModel):
    factor: str
    impact: str
    weight: float


class RiskScoreBreakdown(BaseModel):
    overall: float
    contributing_factors: list[ContributingFactor] = []


class FindingItem(BaseModel):
    id: uuid.UUID
    title: str
    severity: str
    dimension: str
    explanation: Optional[str] = None
    business_impact: Optional[str] = None
    remediation_steps: list[str] = []
    confidence_score: float = 0.0
    source: Optional[str] = None


class SeverityGroup(BaseModel):
    count: int
    items: list[FindingItem] = []


class FindingsSummary(BaseModel):
    total: int
    by_severity: dict[str, SeverityGroup] = {}


class EscalationInfo(BaseModel):
    is_escalated: bool
    reasons: Optional[list[dict]] = None


class ConditionItem(BaseModel):
    condition: str
    source_finding_id: uuid.UUID


class DecisionRecord(BaseModel):
    id: uuid.UUID
    decided_by: Optional[uuid.UUID] = None
    decided_by_role: Optional[str] = None
    decision: str
    rationale: Optional[str] = None
    comment: Optional[str] = None
    was_escalated: bool = False
    created_at: datetime


# ---------------------------------------------------------------------------
# Top-level response
# ---------------------------------------------------------------------------


class CombinedDecisionViewResponse(BaseModel):
    """Complete combined decision view for a release assessment."""

    assessment: AssessmentMetadata
    system_recommendation: SystemRecommendation
    health_score: Optional[HealthScoreBreakdown] = None
    risk_score: Optional[RiskScoreBreakdown] = None
    findings_summary: FindingsSummary
    escalation: EscalationInfo
    conditions: Optional[list[ConditionItem]] = None
    decision_record: Optional[DecisionRecord] = None
    scoring_incomplete: bool = False
    scoring_incomplete_reason: Optional[str] = None
