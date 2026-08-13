"""Pydantic schemas for decision threshold admin API (WO-049)."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Optional

from pydantic import Field, field_validator, model_validator

from forgeguard.core.validation import ForgeGuardBaseModel


class DecisionThresholdCreate(ForgeGuardBaseModel):
    """Request body for POST /api/v1/admin/decision-thresholds."""

    name: str = Field(min_length=1, max_length=255)
    approve_health_min: Decimal = Field(
        default=Decimal("70.00"),
        ge=Decimal("0"),
        le=Decimal("100"),
        description="Minimum health score required for APPROVE (0–100).",
    )
    approve_risk_max: Decimal = Field(
        default=Decimal("30.00"),
        ge=Decimal("0"),
        le=Decimal("100"),
        description="Maximum risk score allowed for APPROVE (0–100).",
    )
    conditional_health_min: Decimal = Field(
        default=Decimal("50.00"),
        ge=Decimal("0"),
        le=Decimal("100"),
        description="Minimum health score required for CONDITIONAL_APPROVE (0–100).",
    )
    conditional_risk_max: Decimal = Field(
        default=Decimal("60.00"),
        ge=Decimal("0"),
        le=Decimal("100"),
        description="Maximum risk score allowed for CONDITIONAL_APPROVE (0–100).",
    )

    @model_validator(mode="after")
    def approve_stricter_than_conditional(self) -> "DecisionThresholdCreate":
        if self.approve_health_min <= self.conditional_health_min:
            raise ValueError(
                "approve_health_min must be strictly greater than conditional_health_min"
            )
        if self.approve_risk_max >= self.conditional_risk_max:
            raise ValueError(
                "approve_risk_max must be strictly less than conditional_risk_max"
            )
        return self


class DecisionThresholdUpdate(ForgeGuardBaseModel):
    """Request body for PUT /api/v1/admin/decision-thresholds/{id}."""

    name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    approve_health_min: Optional[Decimal] = Field(
        default=None, ge=Decimal("0"), le=Decimal("100")
    )
    approve_risk_max: Optional[Decimal] = Field(
        default=None, ge=Decimal("0"), le=Decimal("100")
    )
    conditional_health_min: Optional[Decimal] = Field(
        default=None, ge=Decimal("0"), le=Decimal("100")
    )
    conditional_risk_max: Optional[Decimal] = Field(
        default=None, ge=Decimal("0"), le=Decimal("100")
    )


class DecisionThresholdResponse(ForgeGuardBaseModel):
    """Response schema for a single threshold record."""

    id: uuid.UUID
    name: str
    approve_health_min: Decimal
    approve_risk_max: Decimal
    conditional_health_min: Decimal
    conditional_risk_max: Decimal
    is_active: bool
    created_by: Optional[uuid.UUID] = None
    updated_by: Optional[uuid.UUID] = None
    created_at: datetime
    updated_at: datetime


class DecisionThresholdListResponse(ForgeGuardBaseModel):
    """Paginated list of threshold records."""

    items: list[DecisionThresholdResponse]
    next_cursor: Optional[str] = None
    total: int


class MergeScoresRequest(ForgeGuardBaseModel):
    """Request body for the score-merge preview endpoint."""

    health_score: Decimal = Field(ge=Decimal("0"), le=Decimal("100"))
    risk_score: Decimal = Field(ge=Decimal("0"), le=Decimal("100"))
    threshold_id: Optional[uuid.UUID] = Field(
        default=None,
        description="Optional: use a specific threshold by ID instead of the active one.",
    )


class MergeScoresResponse(ForgeGuardBaseModel):
    """Result of a score-merge computation."""

    decision: str
    health_score: Decimal
    risk_score: Decimal
    threshold_config_id: Optional[uuid.UUID] = None
    contributing_factors: dict = {}
