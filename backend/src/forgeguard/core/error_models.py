"""Pydantic response models for ForgeGuard structured error responses.

These models define the authoritative JSON schema for every error shape
returned by the global exception handlers.  They are used for documentation
and type safety; the handlers build plain dicts to avoid serialisation
overhead on the hot error path.

Error shapes
------------
Standard error::

    {"error": "not_found", "message": "Service xyz was not found", "reference_id": "<uuid>"}

Permission denied (403)::

    {
        "error": "forbidden",
        "message": "You cannot delete another team's service",
        "reference_id": "<uuid>",
        "action": "Contact platform admin to request the 'service:delete' permission.",
        "required_permission": "service:delete"
    }

Validation error (422)::

    {
        "error": "validation_error",
        "message": "Request validation failed",
        "reference_id": "<uuid>",
        "details": [{"field": "commit_sha", "message": "...", "received": "abc"}]
    }
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class ErrorResponse(BaseModel):
    """Standard structured error response for most HTTP error types."""

    error: str
    """Machine-readable error type slug (e.g. ``not_found``, ``unauthorized``)."""

    message: str
    """Human-readable error description, safe to display to end users."""

    reference_id: str
    """Correlation ID from RequestIDMiddleware — include this in support tickets."""


class ForbiddenErrorResponse(ErrorResponse):
    """HTTP 403 response — extends ErrorResponse with actionable permission guidance."""

    action: str
    """Suggested action to resolve the permission issue."""

    required_permission: str
    """The specific permission slug the caller is missing."""


class ValidationErrorDetail(BaseModel):
    """Per-field detail for a single validation failure."""

    field: str
    """Dot-notation field path (e.g. ``items[0].name``, ``commit_sha``)."""

    message: str
    """Validation failure reason for this field."""

    received: Any = None
    """The value that was received (truncated to 200 chars for strings)."""


class ValidationErrorResponse(ErrorResponse):
    """HTTP 422 response — extends ErrorResponse with per-field validation errors."""

    details: list[ValidationErrorDetail]
    """One entry per failing field."""
