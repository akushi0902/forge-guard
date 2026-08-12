"""Severity classification framework for policy findings (WO-036).

Single source of truth for the four severity levels used across the ForgeGuard
platform — from database constraints and SQLAlchemy models to API responses,
dashboard filtering, and security escalation logic.

Design decisions:
  - str+Enum mixin so severity values compare equal to their string literals,
    making CHECK constraints, JSON serialisation, and Pydantic coercion seamless.
  - Decimal weights avoid floating-point rounding when the weights are used
    in dimension scoring calculations.
  - SEVERITY_REGISTRY is a plain frozen dict (types.MappingProxyType) so all
    lookups are O(1) and the registry cannot be mutated at runtime.
  - SeverityClassifier is a stateless class — no database or network calls.
    Escalation logic is a hard business rule: CRITICAL + security dimension only.
"""

from __future__ import annotations

import types
from dataclasses import dataclass
from decimal import Decimal
from enum import Enum


# ---------------------------------------------------------------------------
# SeverityLevel enum
# ---------------------------------------------------------------------------

class SeverityLevel(str, Enum):
    """Four-valued ordered severity taxonomy.

    Inherits from str so enum values compare equal to their string literals,
    making CHECK constraints, JSON serialisation, and Pydantic coercion seamless.
    Values are intentionally lowercase to match the database CHECK constraint
    strings and the existing VARCHAR column values throughout the system.
    """

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"

    @classmethod
    def from_string(cls, value: str) -> "SeverityLevel":
        """Case-insensitive factory.  Raises ValueError on unknown values."""
        try:
            return cls(value.lower())
        except ValueError:
            valid = ", ".join(m.value for m in cls)
            raise ValueError(
                f"Invalid severity {value!r}. Valid values are: {valid}"
            )


# ---------------------------------------------------------------------------
# SeverityMetadata dataclass
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class SeverityMetadata:
    """Immutable metadata associated with a SeverityLevel.

    Attributes:
        level:               The SeverityLevel this metadata describes.
        display_label:       Human-readable label for UI display.
        numeric_weight:      Scoring weight as Decimal (0.0–1.0 scale).
        color_code:          Hex color for UI badges and charts.
        escalation_required: True only for CRITICAL — indicates auto-escalation
                             to Security Reviewer when dimension is 'security'.
        sla_hours:           Time in hours by which the finding must be resolved.
    """

    level: SeverityLevel
    display_label: str
    numeric_weight: Decimal
    color_code: str
    escalation_required: bool
    sla_hours: int


# ---------------------------------------------------------------------------
# SEVERITY_REGISTRY — canonical metadata for all four levels
# ---------------------------------------------------------------------------

SEVERITY_REGISTRY: types.MappingProxyType[SeverityLevel, SeverityMetadata] = (
    types.MappingProxyType({
        SeverityLevel.CRITICAL: SeverityMetadata(
            level=SeverityLevel.CRITICAL,
            display_label="Critical",
            numeric_weight=Decimal("1.0"),
            color_code="#DC2626",
            escalation_required=True,
            sla_hours=48,
        ),
        SeverityLevel.HIGH: SeverityMetadata(
            level=SeverityLevel.HIGH,
            display_label="High",
            numeric_weight=Decimal("0.7"),
            color_code="#F59E0B",
            escalation_required=False,
            sla_hours=120,
        ),
        SeverityLevel.MEDIUM: SeverityMetadata(
            level=SeverityLevel.MEDIUM,
            display_label="Medium",
            numeric_weight=Decimal("0.4"),
            color_code="#3B82F6",
            escalation_required=False,
            sla_hours=240,
        ),
        SeverityLevel.LOW: SeverityMetadata(
            level=SeverityLevel.LOW,
            display_label="Low",
            numeric_weight=Decimal("0.2"),
            color_code="#6B7280",
            escalation_required=False,
            sla_hours=480,
        ),
    })
)

# Ordered from highest to lowest weight — useful for sorting and display.
SEVERITY_ORDER: tuple[SeverityLevel, ...] = (
    SeverityLevel.CRITICAL,
    SeverityLevel.HIGH,
    SeverityLevel.MEDIUM,
    SeverityLevel.LOW,
)

_SECURITY_DIMENSION = "security"


# ---------------------------------------------------------------------------
# SeverityClassifier
# ---------------------------------------------------------------------------

class SeverityClassifier:
    """Stateless service for severity classification and escalation logic.

    All methods are pure functions over the SEVERITY_REGISTRY.  There are no
    database calls, no I/O, and no mutable state.
    """

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @staticmethod
    def classify_finding(severity: str | SeverityLevel) -> SeverityLevel:
        """Normalise a raw severity string to a SeverityLevel enum value.

        Accepts case-insensitive input ('CRITICAL', 'critical', 'Critical').
        Raises ValueError for unknown values.
        """
        if isinstance(severity, SeverityLevel):
            return severity
        return SeverityLevel.from_string(severity)

    @staticmethod
    def get_severity_metadata(severity: str | SeverityLevel) -> SeverityMetadata:
        """Return the full SeverityMetadata for a given severity level.

        Raises ValueError for unknown severity strings.
        """
        level = SeverityClassifier.classify_finding(severity)
        return SEVERITY_REGISTRY[level]

    @staticmethod
    def is_escalation_required(
        severity: str | SeverityLevel,
        dimension: str,
    ) -> bool:
        """Return True only when severity is CRITICAL AND dimension is 'security'.

        This is a hard business rule that cannot be overridden by configuration:
        a CRITICAL finding in a non-security dimension does NOT escalate.
        """
        level = SeverityClassifier.classify_finding(severity)
        return (
            SEVERITY_REGISTRY[level].escalation_required
            and dimension == _SECURITY_DIMENSION
        )

    @staticmethod
    def numeric_weight(severity: str | SeverityLevel) -> Decimal:
        """Return the Decimal scoring weight for the given severity level."""
        return SeverityClassifier.get_severity_metadata(severity).numeric_weight

    @staticmethod
    def sla_hours(severity: str | SeverityLevel) -> int:
        """Return the SLA resolution window in hours for the given severity level."""
        return SeverityClassifier.get_severity_metadata(severity).sla_hours
