"""Pydantic schemas for Audit Log API (WO-029, WO-031).

Models:
    AuditLogEntry            — a single immutable audit record.
    AuditLogListResponse     — paginated list (WO-029 format).
    AuditLogQueryParams      — query-string filters for GET /admin/audit-logs (WO-029).
    PaginationMeta           — pagination envelope used by WO-031 endpoints.
    AuditLogListDataResponse — data-envelope list response (WO-031 format).
    AuditLogDataResponse     — data-envelope single-record response (WO-031 format).
    AuditLogFilters          — query-string filters for GET /audit-logs (WO-031).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


class AuditLogEntry(BaseModel):
    """A single immutable audit record returned by the query endpoint."""

    id: uuid.UUID
    actor_id: Optional[uuid.UUID] = None
    actor_role: str
    action: str
    resource_type: str
    resource_id: Optional[uuid.UUID] = None
    before_state: Optional[dict[str, Any]] = None
    after_state: Optional[dict[str, Any]] = None
    ip_address_masked: Optional[str] = None
    correlation_id: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class AuditLogListResponse(BaseModel):
    """Paginated response for the audit-logs query endpoint."""

    audit_logs: list[AuditLogEntry]
    next_cursor: Optional[str] = None
    total_count: int


class AuditLogQueryParams(BaseModel):
    """Optional query-string filters for GET /api/v1/admin/audit-logs.

    All fields are optional — omitting them returns all records (paginated).
    ``event_type`` maps to the ``action`` column in the database.
    """

    event_type: Optional[str] = Field(
        default=None,
        description="Filter by action/event type (e.g. 'auth.login', 'rbac.role_change').",
    )
    actor_id: Optional[uuid.UUID] = Field(
        default=None,
        description="Filter by the actor's UUID.",
    )
    resource_type: Optional[str] = Field(
        default=None,
        description="Filter by resource type (e.g. 'users', 'services').",
    )
    resource_id: Optional[uuid.UUID] = Field(
        default=None,
        description="Filter by the affected resource's UUID.",
    )
    from_date: Optional[datetime] = Field(
        default=None,
        alias="from",
        description="Include only records on or after this timestamp (ISO 8601).",
    )
    to_date: Optional[datetime] = Field(
        default=None,
        alias="to",
        description="Include only records strictly before this timestamp (ISO 8601).",
    )
    cursor: Optional[str] = Field(
        default=None,
        description="Opaque pagination cursor from a previous response.",
    )
    limit: int = Field(
        default=50,
        ge=1,
        le=100,
        description="Page size. Default 50, max 100.",
    )

    model_config = {"populate_by_name": True}


# ---------------------------------------------------------------------------
# WO-031 response envelope schemas
# ---------------------------------------------------------------------------

class PaginationMeta(BaseModel):
    """Pagination metadata for WO-031 audit list responses."""

    cursor: Optional[str] = None
    has_more: bool
    total_estimate: int


class AuditLogListDataResponse(BaseModel):
    """Paginated audit log response following the data-envelope pattern (WO-031)."""

    data: list[AuditLogEntry]
    pagination: PaginationMeta


class AuditLogDataResponse(BaseModel):
    """Single audit record response following the data-envelope pattern (WO-031)."""

    data: AuditLogEntry


class AuditLogFilters(BaseModel):
    """Optional query-string filters for GET /api/v1/audit-logs (WO-031).

    All fields are optional — omitting them returns all records (paginated).
    """

    actor_id: Optional[uuid.UUID] = Field(
        default=None, description="Filter by actor UUID."
    )
    resource_type: Optional[str] = Field(
        default=None, description="Filter by resource type (e.g. 'users')."
    )
    resource_id: Optional[uuid.UUID] = Field(
        default=None, description="Filter by affected resource UUID."
    )
    action: Optional[str] = Field(
        default=None,
        description="Filter by action/event type (e.g. 'auth.login').",
    )
    date_from: Optional[datetime] = Field(
        default=None,
        description="Include records on or after this timestamp (ISO 8601, inclusive).",
    )
    date_to: Optional[datetime] = Field(
        default=None,
        description="Include records strictly before this timestamp (ISO 8601, exclusive).",
    )
    cursor: Optional[str] = Field(
        default=None, description="Opaque pagination cursor from a previous response."
    )
    limit: int = Field(default=50, ge=1, le=100, description="Page size (1–100). Default 50.")

    model_config = {"populate_by_name": True}
