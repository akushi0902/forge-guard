"""Pydantic schemas for remediation recommendation API (WO-058, WO-061)."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Literal, Optional

from forgeguard.core.validation import ForgeGuardBaseModel


class RemediationResponse(ForgeGuardBaseModel):
    """Response schema for GET /api/v1/findings/{finding_id}/remediation."""

    id: uuid.UUID
    finding_id: uuid.UUID
    recommendation_text: str
    implementation_guide: str
    business_impact: Optional[str] = None
    confidence_score: Optional[Decimal] = None
    source: str
    created_at: datetime


class RuleResult(ForgeGuardBaseModel):
    """Result of re-evaluating a single policy rule."""

    rule_id: uuid.UUID
    rule_name: str
    passed: bool
    actual_value: str
    threshold: str


class ReEvaluationResponse(ForgeGuardBaseModel):
    """Response schema for POST /api/v1/findings/{finding_id}/re-evaluate (WO-061)."""

    finding_id: uuid.UUID
    before_health_score: Optional[float] = None
    after_health_score: float
    score_delta: Optional[float] = None
    before_finding_status: str
    after_finding_status: str
    rule_results: list[RuleResult]
    updated_guidance: Optional[str] = None
    re_evaluated_at: datetime
