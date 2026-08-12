"""Pydantic response schema for severity metadata (WO-036)."""

from __future__ import annotations

from decimal import Decimal

from pydantic import Field

from forgeguard.core.validation import ForgeGuardBaseModel
from forgeguard.services.domain.severity import SeverityLevel, SeverityMetadata


class SeverityResponse(ForgeGuardBaseModel):
    """API serialisation of a SeverityMetadata record.

    Returned by endpoints that expose severity metadata to clients (dashboards,
    policy rule detail views, finding cards).
    """

    level: SeverityLevel = Field(description="Canonical severity level identifier.")
    display_label: str = Field(description="Human-readable label for UI display.")
    numeric_weight: Decimal = Field(
        description="Scoring weight used in dimension score calculations (0.0–1.0)."
    )
    color_code: str = Field(
        description="Hex color code for UI badges and severity indicators."
    )
    escalation_required: bool = Field(
        description="True when findings at this level require escalation to Security Reviewer."
    )
    sla_hours: int = Field(
        description="Resolution SLA in hours from finding detection."
    )

    @classmethod
    def from_metadata(cls, metadata: SeverityMetadata) -> "SeverityResponse":
        """Construct from a SeverityMetadata domain object."""
        return cls(
            level=metadata.level,
            display_label=metadata.display_label,
            numeric_weight=metadata.numeric_weight,
            color_code=metadata.color_code,
            escalation_required=metadata.escalation_required,
            sla_hours=metadata.sla_hours,
        )
