"""Pydantic request/response schemas for Release Assessment endpoints (WO-048)."""

from __future__ import annotations

import base64
import re
import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, field_validator, model_validator


_SHA_PATTERN = re.compile(r"^[0-9a-fA-F]{40}$")


class ReleaseAssessmentRequest(BaseModel):
    service_id: uuid.UUID
    commit_sha: Optional[str] = None
    pr_reference: Optional[str] = Field(default=None, max_length=255)

    @field_validator("commit_sha")
    @classmethod
    def validate_commit_sha(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and not _SHA_PATTERN.match(v):
            raise ValueError("commit_sha must be a 40-character hexadecimal string")
        return v

    @model_validator(mode="after")
    def require_one_reference(self) -> "ReleaseAssessmentRequest":
        if not self.commit_sha and not self.pr_reference:
            raise ValueError(
                "At least one of commit_sha or pr_reference must be provided"
            )
        return self


class ContributingFactorResponse(BaseModel):
    metric_name: str
    actual_value: float
    threshold: float
    risk_contribution: float
    dimension: str


class RiskScoreResponse(BaseModel):
    overall_score: int
    dimension_scores: dict[str, int]
    contributing_factors: list[ContributingFactorResponse]


class FindingResponse(BaseModel):
    id: uuid.UUID
    title: str
    severity: str
    dimension: str
    explanation: str
    business_impact: str
    remediation_steps: list[str]
    confidence_score: float
    source: str


class ReleaseAssessmentResponse(BaseModel):
    id: uuid.UUID
    service_id: uuid.UUID
    commit_sha: Optional[str] = None
    pr_reference: Optional[str] = None
    status: str
    created_at: datetime
    completed_at: Optional[datetime] = None


class ReleaseAssessmentDetailResponse(ReleaseAssessmentResponse):
    risk_score: Optional[RiskScoreResponse] = None
    findings: list[FindingResponse] = []
    change_analysis_summary: Optional[dict] = None


class PaginatedAssessmentResponse(BaseModel):
    items: list[ReleaseAssessmentResponse]
    cursor: Optional[str] = None
    has_more: bool


def encode_cursor(created_at: datetime, record_id: uuid.UUID) -> str:
    """Encode a (created_at, id) pair as an opaque base64 cursor string."""
    raw = f"{created_at.isoformat()}|{record_id}"
    return base64.urlsafe_b64encode(raw.encode()).decode()


def decode_cursor(cursor: str) -> tuple[datetime, uuid.UUID]:
    """Decode a base64 cursor to (created_at, id).

    Raises:
        ValueError: If the cursor is malformed or contains invalid values.
    """
    try:
        raw = base64.urlsafe_b64decode(cursor.encode()).decode()
        ts_str, id_str = raw.split("|", 1)
        return datetime.fromisoformat(ts_str), uuid.UUID(id_str)
    except Exception as exc:
        raise ValueError(f"Invalid pagination cursor: {exc}") from exc
