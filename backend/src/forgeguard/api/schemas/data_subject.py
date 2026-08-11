"""Pydantic schemas for GDPR data subject rights endpoints (WO-034).

Covers all four GDPR Article 15/16/17/20 operations:
  - GET  /api/v1/users/me/data        — access (UserDataResponse)
  - PATCH /api/v1/users/me/data       — rectification (UserDataRectifyRequest)
  - DELETE /api/v1/users/me/data      — erasure (204, no schema)
  - GET  /api/v1/users/me/data?export=true — portability (UserDataExport)
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Optional

from pydantic import Field

from forgeguard.core.validation import EmailField, ForgeGuardBaseModel


# ---------------------------------------------------------------------------
# Related records count (embedded in access response)
# ---------------------------------------------------------------------------

class RelatedRecordCounts(ForgeGuardBaseModel):
    """Summary count of records referencing the user across domain tables."""

    audit_log_count: int = Field(
        default=0,
        ge=0,
        description="Number of audit log entries where the user is the actor.",
    )
    assessments_count: int = Field(
        default=0,
        ge=0,
        description="Number of assessments the user has requested.",
    )
    decisions_count: int = Field(
        default=0,
        ge=0,
        description="Number of release decisions the user has made.",
    )


# ---------------------------------------------------------------------------
# Access (GET /api/v1/users/me/data)
# ---------------------------------------------------------------------------

class UserDataProfile(ForgeGuardBaseModel):
    """Decrypted user profile fields returned to the data subject."""

    model_config = {  # type: ignore[assignment]
        "strict": True,
        "extra": "ignore",
        "frozen": False,
        "str_strip_whitespace": True,
        "populate_by_name": True,
    }

    id: uuid.UUID
    email: str
    name: Optional[str] = Field(default=None)
    role: str
    created_at: datetime
    related_records: RelatedRecordCounts


class UserDataResponse(ForgeGuardBaseModel):
    """Response body for GET /api/v1/users/me/data."""

    data: UserDataProfile


# ---------------------------------------------------------------------------
# Rectification (PATCH /api/v1/users/me/data)
# ---------------------------------------------------------------------------

class UserDataRectifyRequest(ForgeGuardBaseModel):
    """Request body for PATCH /api/v1/users/me/data.

    Both fields are optional — send only the fields you want to update.
    At least one field must be provided.
    """

    email: Optional[EmailField] = Field(
        default=None,
        description="New email address.  Must not already be in use by another account.",
    )
    name: Optional[str] = Field(
        default=None,
        min_length=1,
        max_length=255,
        description="New display name.",
    )


class UserDataRectifyResponse(ForgeGuardBaseModel):
    """Response body for PATCH /api/v1/users/me/data."""

    model_config = {  # type: ignore[assignment]
        "strict": True,
        "extra": "ignore",
        "frozen": False,
        "str_strip_whitespace": True,
        "populate_by_name": True,
    }

    id: uuid.UUID
    email: str
    name: Optional[str] = Field(default=None)
    role: str
    updated_at: datetime


# ---------------------------------------------------------------------------
# Export (GET /api/v1/users/me/data?export=true)
# ---------------------------------------------------------------------------

class UserDataExport(ForgeGuardBaseModel):
    """Full data export payload for GET /api/v1/users/me/data?export=true.

    Returned as a downloadable JSON attachment via StreamingResponse with
    Content-Disposition: attachment; filename=user-data-export-<timestamp>.json
    """

    model_config = {  # type: ignore[assignment]
        "strict": False,
        "extra": "ignore",
        "frozen": False,
        "str_strip_whitespace": True,
        "populate_by_name": True,
    }

    profile: dict[str, Any] = Field(
        description="Decrypted user profile (id, email, name, role, created_at).",
    )
    audit_logs: list[dict[str, Any]] = Field(
        default_factory=list,
        description="All audit log entries where the user is the actor.",
    )
    assessments: list[dict[str, Any]] = Field(
        default_factory=list,
        description="All assessments the user has requested.",
    )
    decisions: list[dict[str, Any]] = Field(
        default_factory=list,
        description="All release decisions the user has made.",
    )
