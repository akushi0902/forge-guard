"""Pydantic schemas for the Prompt Template admin API.

These schemas validate and document the request/response contracts for
POST /api/v1/admin/prompt-templates, GET, PATCH, and DELETE endpoints.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import Field, field_validator

from forgeguard.core.validation import ForgeGuardBaseModel
from forgeguard.data.models.prompt_template import (
    _DIMENSION_CHECK_EXPR as _DIM_EXPR,  # noqa: PLC2701
)

_VALID_DIMENSIONS = (
    "code_quality",
    "test_coverage",
    "security",
    "documentation",
    "operations_readiness",
)

_VALID_SEVERITIES = ("critical", "high", "medium", "low")


class PromptTemplateCreate(ForgeGuardBaseModel):
    """Request body for POST /api/v1/admin/prompt-templates."""

    name: str = Field(
        min_length=1,
        max_length=255,
        description="Human-readable template identifier.",
    )
    template_text: str = Field(
        min_length=1,
        description="Prompt text with $variable placeholders for substitution.",
    )
    variables: dict[str, Any] = Field(
        default_factory=dict,
        description="Schema of expected substitution variables, e.g. {'finding_title': 'str'}.",
    )
    dimension: str = Field(
        description="Policy dimension this template targets.",
    )
    severity_level: str = Field(
        description="Severity level this template targets.",
    )

    @field_validator("template_text")
    @classmethod
    def template_text_not_whitespace(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("template_text must not be empty or whitespace-only.")
        return v

    @field_validator("dimension")
    @classmethod
    def validate_dimension(cls, v: str) -> str:
        if v not in _VALID_DIMENSIONS:
            raise ValueError(
                f"dimension must be one of {list(_VALID_DIMENSIONS)}, got {v!r}."
            )
        return v

    @field_validator("severity_level")
    @classmethod
    def validate_severity_level(cls, v: str) -> str:
        if v not in _VALID_SEVERITIES:
            raise ValueError(
                f"severity_level must be one of {list(_VALID_SEVERITIES)}, got {v!r}."
            )
        return v


class PromptTemplateUpdate(ForgeGuardBaseModel):
    """Request body for PATCH /api/v1/admin/prompt-templates/{id}.

    Only template_text and variables can be updated; name, dimension, and
    severity_level are immutable (create a new template instead).
    """

    template_text: str | None = Field(
        default=None,
        min_length=1,
        description="Replacement prompt text.",
    )
    variables: dict[str, Any] | None = Field(
        default=None,
        description="Replacement variable schema.",
    )

    @field_validator("template_text")
    @classmethod
    def template_text_not_whitespace(cls, v: str | None) -> str | None:
        if v is not None and not v.strip():
            raise ValueError("template_text must not be empty or whitespace-only.")
        return v


class PromptTemplateResponse(ForgeGuardBaseModel):
    """Response body for all prompt template endpoints."""

    id: uuid.UUID
    name: str
    version: int
    template_text: str
    variables: dict[str, Any]
    dimension: str
    severity_level: str
    is_active: bool
    created_by: uuid.UUID | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class PromptTemplateListResponse(ForgeGuardBaseModel):
    """Response body for GET /api/v1/admin/prompt-templates."""

    items: list[PromptTemplateResponse]
    total: int
    limit: int
    offset: int


class PromptTemplateDeactivateResponse(ForgeGuardBaseModel):
    """Response body for DELETE /api/v1/admin/prompt-templates/{id}."""

    id: uuid.UUID
    is_active: bool
    deactivated_at: datetime

    model_config = {"from_attributes": True}
