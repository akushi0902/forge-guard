"""Pydantic request/response schemas for exception request API (WO-062, WO-064)."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator, model_validator

_MAX_EXCEPTION_DAYS = 90


class ExceptionRequest(BaseModel):
    """Request body for POST /api/v1/findings/{finding_id}/exceptions."""

    justification: str = Field(..., min_length=1)
    expires_at: datetime

    @field_validator("justification")
    @classmethod
    def justification_min_length(cls, v: str) -> str:
        stripped = v.strip()
        if len(stripped) < 20:
            raise ValueError(
                "justification must be at least 20 characters (after trimming whitespace)"
            )
        return stripped

    @field_validator("expires_at")
    @classmethod
    def expires_at_must_be_future(cls, v: datetime) -> datetime:
        now = datetime.now(timezone.utc)
        if v.tzinfo is None:
            v = v.replace(tzinfo=timezone.utc)
        if v <= now:
            raise ValueError("expires_at must be strictly in the future")
        max_dt = now + timedelta(days=_MAX_EXCEPTION_DAYS)
        if v > max_dt:
            raise ValueError(
                f"expires_at must be no more than {_MAX_EXCEPTION_DAYS} days from now"
            )
        return v


class ExceptionResponse(BaseModel):
    """Response body for exception creation and retrieval."""

    id: uuid.UUID
    finding_id: uuid.UUID
    requested_by: Optional[uuid.UUID] = None
    justification: str
    status: str
    approver_role: str
    decided_by: Optional[uuid.UUID] = None
    decision_comment: Optional[str] = None
    expires_at: datetime
    decided_at: Optional[datetime] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class ExceptionDecisionRequest(BaseModel):
    """Request body for POST /api/v1/exceptions/{exception_id}/decide."""

    decision: Literal["approved", "denied"]
    decision_comment: str = Field(..., min_length=10)


class HealthScoreImpact(BaseModel):
    """Before/after health score delta from an exception approval."""

    before: float
    after: float
    delta: float


class ExceptionDecisionResponse(BaseModel):
    """Response body for POST /api/v1/exceptions/{exception_id}/decide."""

    id: uuid.UUID
    finding_id: uuid.UUID
    status: str
    decided_by: Optional[uuid.UUID] = None
    decision_comment: str
    decided_at: datetime
    finding_status: str
    health_score_impact: Optional[HealthScoreImpact] = None

    model_config = {"from_attributes": True}


class ExceptionListResponse(BaseModel):
    """Paginated list of exceptions."""

    items: list[ExceptionResponse]
    total: int
    cursor: Optional[str] = None
