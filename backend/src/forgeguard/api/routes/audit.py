"""Audit Log Query API endpoints (WO-031).

Routes:
    GET /api/v1/audit-logs           — paginated, filtered list
    GET /api/v1/audit-logs/export    — streaming JSON export with Content-Disposition
    GET /api/v1/audit-logs/{id}      — single record by UUID

Access:
    Platform Admin only (audit.view permission).
    Enforced by the RBAC middleware via route_permissions.py AND by the
    in-route ``_require_audit_view`` dependency for defence-in-depth.

Response format follows the standard envelope:
    {data: [...], pagination: {cursor, has_more, total_estimate}}
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Annotated, AsyncGenerator, Optional

import structlog
from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import StreamingResponse

from forgeguard.api.dependencies.auth import CurrentUser, CurrentUserDep
from forgeguard.api.schemas.audit import (
    AuditLogDataResponse,
    AuditLogEntry,
    AuditLogListDataResponse,
    PaginationMeta,
)
from forgeguard.core.exceptions import ForbiddenError, NotFoundError
from forgeguard.core.permissions import Permissions, has_permission
from forgeguard.data.repositories.audit_logs import AuditLogRepository
from forgeguard.utils.pagination import decode_cursor, encode_cursor

logger = structlog.get_logger(__name__)

router = APIRouter(
    prefix="/api/v1/audit-logs",
    tags=["audit"],
)


# ---------------------------------------------------------------------------
# Dependencies
# ---------------------------------------------------------------------------

async def _require_audit_view(current_user: CurrentUserDep) -> CurrentUser:
    """Enforce that the caller has audit.view permission (Platform Admin only)."""
    if not has_permission(current_user.role, Permissions.AUDIT_VIEW):
        raise ForbiddenError(
            "This action requires the audit.view permission assigned to the "
            "Platform Admin role. Contact your Platform Admin for access.",
            required_permission=Permissions.AUDIT_VIEW,
            contact_role="Platform Admin",
        )
    return current_user


AuditViewDep = Annotated[CurrentUser, Depends(_require_audit_view)]


async def _get_audit_repo(request: Request) -> AuditLogRepository:
    from forgeguard.data.database import get_pool  # noqa: PLC0415

    pool = await get_pool()
    return AuditLogRepository(pool)


AuditRepoDep = Annotated[AuditLogRepository, Depends(_get_audit_repo)]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        return None


def _json_default(obj):
    if isinstance(obj, (datetime,)):
        return obj.isoformat()
    if isinstance(obj, uuid.UUID):
        return str(obj)
    raise TypeError(f"Object of type {type(obj)} is not JSON serializable")


async def _stream_json_array(
    records: AsyncGenerator,
) -> AsyncGenerator[str, None]:
    """Yield a JSON array of audit records, one record per chunk."""
    yield "["
    first = True
    async for record in records:
        prefix = "" if first else ","
        first = False
        yield prefix + json.dumps(record, default=_json_default)
    yield "]"


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get(
    "/export",
    summary="Export audit logs as downloadable JSON (Platform Admin only)",
    response_class=StreamingResponse,
)
async def export_audit_logs(
    current_user: AuditViewDep,
    repo: AuditRepoDep,
    actor_id: Optional[uuid.UUID] = Query(default=None, description="Filter by actor UUID."),
    resource_type: Optional[str] = Query(default=None, description="Filter by resource type."),
    resource_id: Optional[uuid.UUID] = Query(default=None, description="Filter by resource UUID."),
    action: Optional[str] = Query(default=None, description="Filter by action/event type."),
    date_from: Optional[str] = Query(default=None, alias="date_from", description="ISO 8601 start (inclusive)."),
    date_to: Optional[str] = Query(default=None, alias="date_to", description="ISO 8601 end (exclusive)."),
) -> StreamingResponse:
    """Stream all matching audit records as a downloadable JSON file.

    Handles result sets up to 100,000+ records without loading everything
    into memory by using cursor-based batch fetching under the hood.
    """
    logger.info(
        "audit.export.started",
        actor_id=str(actor_id) if actor_id else None,
        resource_type=resource_type,
        action=action,
        by=str(current_user.user_id),
    )

    after_dt = _parse_datetime(date_from)
    before_dt = _parse_datetime(date_to)
    timestamp = datetime.now(tz=timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    records_gen = repo.stream_records(
        actor_id=actor_id,
        resource_type=resource_type,
        resource_id=resource_id,
        action=action,
        after=after_dt,
        before=before_dt,
    )

    return StreamingResponse(
        _stream_json_array(records_gen),
        media_type="application/json",
        headers={
            "Content-Disposition": f'attachment; filename="audit-export-{timestamp}.json"',
        },
    )


@router.get(
    "/{audit_id}",
    response_model=AuditLogDataResponse,
    summary="Get a single audit record by UUID (Platform Admin only)",
)
async def get_audit_log(
    audit_id: uuid.UUID,
    current_user: AuditViewDep,
    repo: AuditRepoDep,
) -> AuditLogDataResponse:
    """Return a single audit record by its UUID including before_state and after_state."""
    logger.info(
        "audit.get_by_id",
        audit_id=str(audit_id),
        by=str(current_user.user_id),
    )
    row = await repo.get_by_id(audit_id)
    if row is None:
        raise NotFoundError(f"Audit record {audit_id!r} was not found.")
    return AuditLogDataResponse(data=AuditLogEntry.model_validate(row))


@router.get(
    "",
    response_model=AuditLogListDataResponse,
    summary="List audit logs with filtering and pagination (Platform Admin only)",
)
async def list_audit_logs(
    current_user: AuditViewDep,
    repo: AuditRepoDep,
    actor_id: Optional[uuid.UUID] = Query(default=None, description="Filter by actor UUID."),
    resource_type: Optional[str] = Query(default=None, description="Filter by resource type."),
    resource_id: Optional[uuid.UUID] = Query(default=None, description="Filter by resource UUID."),
    action: Optional[str] = Query(default=None, description="Filter by action/event type."),
    date_from: Optional[str] = Query(default=None, alias="date_from", description="ISO 8601 start (inclusive)."),
    date_to: Optional[str] = Query(default=None, alias="date_to", description="ISO 8601 end (exclusive)."),
    cursor: Optional[str] = Query(default=None, description="Opaque pagination cursor."),
    limit: int = Query(default=50, ge=1, le=100, description="Page size (max 100)."),
) -> AuditLogListDataResponse:
    """Return a paginated, filtered list of audit records.

    All query parameters are optional.  Results are ordered newest-first.
    The ``pagination.cursor`` field is ``null`` when there are no more pages.
    The ``pagination.total_estimate`` is the count matching the current filters
    (excluding cursor offset) for display purposes.

    Date filters enable PostgreSQL partition pruning for sub-500ms performance
    on large datasets.
    """
    logger.info(
        "audit.list.query",
        actor_id=str(actor_id) if actor_id else None,
        resource_type=resource_type,
        resource_id=str(resource_id) if resource_id else None,
        action=action,
        limit=limit,
        has_cursor=cursor is not None,
        by=str(current_user.user_id),
    )

    after_dt = _parse_datetime(date_from)
    before_dt = _parse_datetime(date_to)

    # Decode cursor to validate it early (before hitting the DB).
    if cursor is not None:
        decode_cursor(cursor)  # raises BadRequestError on invalid cursor

    # Fetch limit+1 rows to determine has_more without a separate COUNT.
    rows = await repo.query_with_filters(
        actor_id=actor_id,
        resource_type=resource_type,
        resource_id=resource_id,
        action=action,
        after=after_dt,
        before=before_dt,
        cursor=cursor,
        limit=limit + 1,
    )

    has_more = len(rows) > limit
    page = rows[:limit]

    next_cursor: str | None = None
    if has_more and page:
        last = page[-1]
        next_cursor = encode_cursor(last["created_at"], last["id"])

    # Total estimate for the filter set (without cursor, for UI display).
    total_estimate = await repo.count_query(
        actor_id=actor_id,
        resource_type=resource_type,
        resource_id=resource_id,
        action=action,
        after=after_dt,
        before=before_dt,
    )

    entries = [AuditLogEntry.model_validate(r) for r in page]
    return AuditLogListDataResponse(
        data=entries,
        pagination=PaginationMeta(
            cursor=next_cursor,
            has_more=has_more,
            total_estimate=total_estimate,
        ),
    )
