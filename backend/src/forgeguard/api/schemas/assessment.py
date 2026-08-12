"""Pydantic response schemas for the health assessment API (WO-042)."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any, Optional

from forgeguard.core.validation import ForgeGuardBaseModel


class DimensionScoreResponse(ForgeGuardBaseModel):
    """Score and rule-count breakdown for a single governance dimension."""

    dimension: str
    score: Optional[Decimal] = None
    total_rules: int = 0
    passed_rules: int = 0
    failed_rules: int = 0
    inconclusive_rules: int = 0
    error_rules: int = 0
    has_data: bool = False


class AssessmentTriggerResponse(ForgeGuardBaseModel):
    """Response body for POST /api/v1/services/{id}/assess.

    When all pipeline stages complete within the request, status='completed'
    and overall_score/dimension_scores are populated.  A null overall_score
    indicates no active policies were configured.
    """

    assessment_id: uuid.UUID
    status: str
    overall_score: Optional[Decimal] = None
    dimension_scores: dict[str, DimensionScoreResponse] = {}
    finding_counts: dict[str, int] = {}
    evaluated_at: datetime
    message: Optional[str] = None


class HealthScoreResponse(ForgeGuardBaseModel):
    """Response body for GET /api/v1/services/{id}/scores.

    Returns the most recent health score for the service, or nulls with an
    informational message when no assessments have been run.
    """

    service_id: uuid.UUID
    overall_score: Optional[Decimal] = None
    dimension_scores: dict[str, DimensionScoreResponse] = {}
    weights_used: dict[str, Decimal] = {}
    finding_counts: dict[str, int] = {}
    last_evaluated_at: Optional[datetime] = None
    message: Optional[str] = None


class FindingDetailResponse(ForgeGuardBaseModel):
    """Full finding record returned by GET /api/v1/services/{id}/findings/{finding_id}."""

    id: uuid.UUID
    assessment_id: uuid.UUID
    service_id: uuid.UUID
    title: str
    description: Optional[str] = None
    severity: str
    dimension: str
    status: str
    evidence: Optional[dict[str, Any]] = None
    ai_explanation: Optional[dict[str, Any]] = None
    escalation_required: bool = False
    created_at: datetime
    resolved_at: Optional[datetime] = None


class FindingListResponse(ForgeGuardBaseModel):
    """Cursor-paginated findings list returned by GET /api/v1/services/{id}/findings."""

    items: list[FindingDetailResponse]
    next_cursor: Optional[str] = None
    total_count: int
