"""Pydantic models for the AI Engine template system.

Defines the schema for template definitions loaded from YAML files
and the structured responses returned to callers.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field, field_validator


class TemplateDimension(str, Enum):
    """Risk dimensions that templates are organised by."""

    CODE_COMPLEXITY = "code_complexity"
    TEST_COVERAGE = "test_coverage"
    DEPENDENCIES = "dependencies"
    SECURITY = "security"
    HISTORICAL = "historical"
    GENERIC = "generic"


class TemplateDefinition(BaseModel):
    """Schema for a single template definition loaded from YAML.

    Templates use ``{variable_name}`` placeholders for substitution.
    Available variables: ``service_name``, ``finding_title``, ``severity``,
    ``dimension``, ``commit_sha``, ``pr_reference``, ``threshold_value``,
    ``actual_value``.
    """

    finding_type: str = Field(
        description="Unique identifier for this finding type, e.g. 'high_cyclomatic_complexity'."
    )
    dimension: TemplateDimension = Field(
        description="Risk dimension this template belongs to."
    )
    severity_levels: list[str] = Field(
        description="Severity levels this template applies to (low, medium, high, critical)."
    )
    explanation_template: str = Field(
        description="Template string for the explanation text. Supports {variable} substitution."
    )
    business_impact_template: str = Field(
        description="Template string for business impact description."
    )
    remediation_steps: list[str] = Field(
        description="Ordered list of remediation step template strings."
    )
    code_examples: list[str] | None = Field(
        default=None,
        description="Optional list of code examples (educational, never exploit code).",
    )

    @field_validator("severity_levels")
    @classmethod
    def validate_severity_levels(cls, v: list[str]) -> list[str]:
        valid = {"low", "medium", "high", "critical", "any"}
        invalid = [s for s in v if s not in valid]
        if invalid:
            raise ValueError(f"Invalid severity levels: {invalid}. Must be one of {valid}.")
        return v

    @field_validator("remediation_steps")
    @classmethod
    def validate_remediation_steps(cls, v: list[str]) -> list[str]:
        if not v:
            raise ValueError("remediation_steps must contain at least one step.")
        return v


class TemplateResponse(BaseModel):
    """Structured response returned by the TemplateEngine.

    Contains all rendered fields ready for delivery to API consumers.
    """

    finding_type: str
    dimension: str
    explanation_text: str
    business_impact: str
    remediation_steps: list[str]
    code_examples: list[str] | None = None
    source: str = "template-generated"
    confidence_score: float = Field(default=0.7, ge=0.0, le=1.0)
    is_generic_fallback: bool = False
