"""Pydantic request/response schemas for the Policy Guardian CRUD API (WO-035).

Includes per-rule_type validation:
  - threshold_gte / threshold_lte / threshold_eq: threshold_config must contain
    a numeric `numeric_value` field.
  - regex_match / regex_no_match: threshold_config must contain a `pattern` field
    that is a valid, compilable regular expression.
"""

from __future__ import annotations

import re
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field, field_validator, model_validator

from forgeguard.data.models.governance import (
    VALID_DIMENSIONS,
    VALID_RULE_TYPES,
    VALID_SEVERITIES,
)

# ---------------------------------------------------------------------------
# Literal type aliases (self-documenting and IDE-friendly)
# ---------------------------------------------------------------------------

PolicyDimension = Literal[
    "code_quality",
    "test_coverage",
    "security",
    "documentation",
    "operations_readiness",
]

PolicyRuleType = Literal[
    "threshold_gte",
    "threshold_lte",
    "threshold_eq",
    "regex_match",
    "regex_no_match",
]

PolicySeverity = Literal["critical", "high", "medium", "low"]

_THRESHOLD_RULE_TYPES = {"threshold_gte", "threshold_lte", "threshold_eq"}
_REGEX_RULE_TYPES = {"regex_match", "regex_no_match"}


# ---------------------------------------------------------------------------
# Policy schemas
# ---------------------------------------------------------------------------


class PolicyCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    dimension: PolicyDimension
    description: Optional[str] = None
    is_active: bool = True

    @field_validator("dimension")
    @classmethod
    def dimension_must_be_valid(cls, v: str) -> str:
        if v not in VALID_DIMENSIONS:
            raise ValueError(
                f"dimension must be one of: {', '.join(VALID_DIMENSIONS)}"
            )
        return v


class PolicyUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    description: Optional[str] = None
    is_active: Optional[bool] = None
    expected_version: Optional[int] = Field(
        default=None,
        description="If provided, update is rejected with 409 on version mismatch.",
    )


class PolicyResponse(BaseModel):
    id: uuid.UUID
    name: str
    dimension: str
    description: Optional[str] = None
    is_active: bool
    version: int
    created_by: Optional[uuid.UUID] = None
    created_at: datetime
    updated_at: datetime
    rule_count: Optional[int] = None
    effect_note: str = (
        "Policy changes take effect on the next evaluation cycle."
    )

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Policy rule schemas
# ---------------------------------------------------------------------------


class PolicyRuleCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    rule_type: PolicyRuleType
    threshold_config: dict[str, Any]
    severity: PolicySeverity
    weight: Decimal = Field(..., ge=Decimal("0"), le=Decimal("100"))
    is_active: bool = True

    @field_validator("severity")
    @classmethod
    def severity_must_be_valid(cls, v: str) -> str:
        if v not in VALID_SEVERITIES:
            raise ValueError(
                f"severity must be one of: {', '.join(VALID_SEVERITIES)}"
            )
        return v

    @field_validator("rule_type")
    @classmethod
    def rule_type_must_be_valid(cls, v: str) -> str:
        if v not in VALID_RULE_TYPES:
            raise ValueError(
                f"rule_type must be one of: {', '.join(VALID_RULE_TYPES)}"
            )
        return v

    @model_validator(mode="after")
    def validate_threshold_config(self) -> "PolicyRuleCreate":
        rt = self.rule_type
        cfg = self.threshold_config

        if rt in _THRESHOLD_RULE_TYPES:
            if "numeric_value" not in cfg:
                raise ValueError(
                    f"threshold_config must contain 'numeric_value' for rule_type '{rt}'"
                )
            try:
                float(cfg["numeric_value"])
            except (TypeError, ValueError):
                raise ValueError(
                    "threshold_config.numeric_value must be a number"
                )

        elif rt in _REGEX_RULE_TYPES:
            if "pattern" not in cfg:
                raise ValueError(
                    f"threshold_config must contain 'pattern' for rule_type '{rt}'"
                )
            if not cfg["pattern"]:
                raise ValueError("threshold_config.pattern must not be empty")
            try:
                re.compile(cfg["pattern"])
            except re.error as exc:
                raise ValueError(
                    f"threshold_config.pattern is not a valid regex: {exc}"
                )

        return self


class PolicyRuleUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    rule_type: Optional[PolicyRuleType] = None
    threshold_config: Optional[dict[str, Any]] = None
    severity: Optional[PolicySeverity] = None
    weight: Optional[Decimal] = Field(default=None, ge=Decimal("0"), le=Decimal("100"))
    is_active: Optional[bool] = None

    @model_validator(mode="after")
    def validate_threshold_config_when_rule_type_set(self) -> "PolicyRuleUpdate":
        rt = self.rule_type
        cfg = self.threshold_config
        if rt is None or cfg is None:
            return self

        if rt in _THRESHOLD_RULE_TYPES:
            if "numeric_value" not in cfg:
                raise ValueError(
                    f"threshold_config must contain 'numeric_value' for rule_type '{rt}'"
                )
            try:
                float(cfg["numeric_value"])
            except (TypeError, ValueError):
                raise ValueError("threshold_config.numeric_value must be a number")

        elif rt in _REGEX_RULE_TYPES:
            if "pattern" not in cfg:
                raise ValueError(
                    f"threshold_config must contain 'pattern' for rule_type '{rt}'"
                )
            if not cfg["pattern"]:
                raise ValueError("threshold_config.pattern must not be empty")
            try:
                re.compile(cfg["pattern"])
            except re.error as exc:
                raise ValueError(
                    f"threshold_config.pattern is not a valid regex: {exc}"
                )

        return self


class PolicyRuleResponse(BaseModel):
    id: uuid.UUID
    policy_id: uuid.UUID
    name: str
    rule_type: str
    threshold_config: Any
    severity: str
    weight: Decimal
    is_active: bool
    created_at: datetime
    updated_at: datetime
    effect_note: str = (
        "Rule changes take effect on the next evaluation cycle."
    )

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# List response
# ---------------------------------------------------------------------------


class PolicyListResponse(BaseModel):
    items: list[PolicyResponse]
    next_cursor: Optional[str] = None
    total_count: int
