"""Pydantic response schemas for the demo governance evaluation endpoint (WO-056)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


class ContributingFactor(BaseModel):
    rule_name: str
    dimension: str
    passed: bool
    weight: float
    impact: float


class DimensionScores(BaseModel):
    code_quality: Optional[float] = None
    test_coverage: Optional[float] = None
    security: Optional[float] = None
    documentation: Optional[float] = None
    operations_readiness: Optional[float] = None


class HealthScoreBreakdown(BaseModel):
    overall: float = Field(ge=0.0, le=100.0)
    dimensions: DimensionScores
    contributing_factors: list[ContributingFactor] = Field(default_factory=list)


class RemediationDetail(BaseModel):
    recommendation_text: str
    implementation_guide: str
    confidence_score: float = Field(ge=0.0, le=1.0)
    source: str


class FindingDetail(BaseModel):
    id: uuid.UUID
    severity: str
    dimension: str
    title: str
    description: str
    evidence: dict[str, Any]
    ai_explanation: str
    confidence_score: float = Field(ge=0.0, le=1.0)
    remediation: RemediationDetail


class SeverityBreakdown(BaseModel):
    critical: int = 0
    high: int = 0
    medium: int = 0
    low: int = 0


class EvaluationSummary(BaseModel):
    total_findings: int
    by_severity: SeverityBreakdown
    evaluated_at: datetime
    evaluation_duration_ms: int


class DemoEvaluationResponse(BaseModel):
    assessment_id: uuid.UUID
    service_id: uuid.UUID
    service_name: str
    is_simulated: bool = True
    health_score: HealthScoreBreakdown
    findings: list[FindingDetail]
    summary: EvaluationSummary
