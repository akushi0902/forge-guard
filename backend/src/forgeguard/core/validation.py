"""Base Pydantic model and reusable field types for ForgeGuard request models.

All domain request/response schemas should inherit from :class:`ForgeGuardBaseModel`
to get strict type enforcement, extra-field rejection, and whitespace stripping
without any per-model boilerplate.

Reusable annotated field types exported here cover the most common cross-domain
validation patterns (UUID, commit SHA, email, score range) so individual domain
modules don't duplicate regex constants or constraint logic.
"""

from __future__ import annotations

import re

from pydantic import BaseModel, ConfigDict, Field
from typing import Annotated


# ---------------------------------------------------------------------------
# Regex constants (module-level for auditability)
# ---------------------------------------------------------------------------

_UUID_PATTERN = (
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
)
_COMMIT_SHA_PATTERN = r"^[0-9a-f]{40}$"
# Simplified RFC-5321 pattern suitable for API validation.
_EMAIL_PATTERN = r"^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$"

# Pre-compiled for use in tests / manual checks.
UUID_RE = re.compile(_UUID_PATTERN, re.IGNORECASE)
COMMIT_SHA_RE = re.compile(_COMMIT_SHA_PATTERN)
EMAIL_RE = re.compile(_EMAIL_PATTERN)


# ---------------------------------------------------------------------------
# Base model
# ---------------------------------------------------------------------------

class ForgeGuardBaseModel(BaseModel):
    """Strict Pydantic base model for all ForgeGuard request/response schemas.

    Configuration:
        strict             — no implicit type coercion (string '123' ≠ int 123)
        extra='forbid'     — unknown fields rejected to prevent mass-assignment
        frozen=False       — models are mutable after construction (intentional)
        str_strip_whitespace — leading/trailing whitespace stripped from strings
        populate_by_name   — allow field population by Python field name as well
                             as alias, supporting flexible DTO patterns
    """

    model_config = ConfigDict(
        strict=True,
        extra="forbid",
        frozen=False,
        str_strip_whitespace=True,
        populate_by_name=True,
    )


# ---------------------------------------------------------------------------
# Reusable annotated field types
# ---------------------------------------------------------------------------

UUIDField = Annotated[
    str,
    Field(
        pattern=_UUID_PATTERN,
        description="RFC-4122 UUID v4 string (lowercase hex with hyphens).",
        examples=["550e8400-e29b-41d4-a716-446655440000"],
    ),
]
"""String field that must be a valid RFC-4122 UUID (case-insensitive)."""

CommitSHAField = Annotated[
    str,
    Field(
        min_length=40,
        max_length=40,
        pattern=_COMMIT_SHA_PATTERN,
        description="40-character lowercase hexadecimal Git commit SHA.",
        examples=["a3f5e1b0c2d4e6f8a0b2c4d6e8f0a2b4c6d8e0f2"],
    ),
]
"""String field constrained to a 40-character lowercase hex Git SHA-1 digest."""

EmailField = Annotated[
    str,
    Field(
        pattern=_EMAIL_PATTERN,
        max_length=254,
        description="RFC-5321 compliant email address.",
        examples=["user@example.com"],
    ),
]
"""String field constrained to a basic RFC-5321 email address format."""

ScoreField = Annotated[
    float,
    Field(
        ge=0.0,
        le=100.0,
        description="Numeric score in the range [0, 100] inclusive.",
        examples=[85.5],
    ),
]
"""Float field constrained to the inclusive range [0, 100]."""
