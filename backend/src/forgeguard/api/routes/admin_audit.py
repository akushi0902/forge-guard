"""Audit Log administration endpoint (WO-029).

Routes:
    GET /api/v1/admin/audit-logs — paginated, filtered audit log query

Access:
    Platform Admin (rbac.manage) and Security Reviewer (release.block) only.
    Enforced by the RBAC middleware via route_permissions.py AND by the
    in-route ``_require_audit_access`` dependency for defence-in-depth.
"""

from __future__ import annotations

import base64
import uuid
from typing import Annotated, Optional

import structlog
from fastapi import APIRouter, Depends, Query, Request

from forgeguard.api.dependencies.auth import CurrentUser, CurrentUserDep
from forgeguard.api.schemas.audit import AuditLogEntry, AuditLogListResponse
from forgeguard.core.permissions import Permissions
from forgeguard.data.repositories.audit_logs import AuditLogRepository
from forgeguard.services.rbac import RBACService

logger = structlog.get_logger(__name__)

router = APIRouter(
    prefix="/api/v1/admin/audit-logs",
    tags=["admin", "audit"],
)

_rbac = RBACService()

_AUDIT_PERMISSIONS = {Permissions.RBAC_MANAGE, Permissions.RELEASE_BLOCK}


async def _require_audit_access(current_user: CurrentUserDep) -> CurrentUser:
    """Enforce that the caller holds rbac.manage OR release.block."""
    from forgeguard.core.exceptions import PermissionDeniedError  # noqa: PLC0415

    for perm in _AUDIT_PERMISSIONS:
        try:
            _rbac.check_permission(current_user.role, perm)
            return current_user
        except Exception:
            continue
    raise PermissionDeniedError(
        "Audit log access requires 'rbac.manage' or 'release.block' permission.",
        required_permission=Permissions.RBAC_MANAGE,
    )


AuditAccessDep = Annotated[CurrentUser, Depends(_require_audit_access)]


async def _get_audit_repo(request: Request) -> AuditLogRepository:
    from forgeguard.data.database import get_pool  # noqa: PLC0415

    pool = await get_pool()
    return AuditLogRepository(pool)


AuditRepoDep = Annotated[AuditLogRepository, Depends(_get_audit_repo)]


def _encode_cursor(created_at, record_id: uuid.UUID) -> str:
    raw = f"{created_at.isoformat()}|{record_id}"
    return base64.b64encode(raw.encode()).decode()


@router.get(
    "",
    response_model=AuditLogListResponse,
    summary="Query audit logs (Platform Admin / Security Reviewer only)",
)
async def list_audit_logs(
    current_user: AuditAccessDep,
    repo: AuditRepoDep,
    event_type: Optional[str] = Query(
        default=None,
        description="Filter by action/event type (e.g. 'auth.login').",
    ),
    actor_id: Optional[uuid.UUID] = Query(
        default=None,
        description="Filter by actor UUID.",
    ),
    resource_type: Optional[str] = Query(
        default=None,
        description="Filter by resource type.",
    ),
    from_date: Optional[str] = Query(
        default=None,
        alias="from",
        description="ISO 8601 start datetime (inclusive).",
    ),
    to_date: Optional[str] = Query(
        default=None,
        alias="to",
        description="ISO 8601 end datetime (exclusive).",
    ),
    cursor: Optional[str] = Query(
        default=None,
        description="Opaque pagination cursor.",
    ),
    limit: int = Query(
        default=50,
        ge=1,
        le=100,
        description="Page size (max 100).",
    ),
) -> AuditLogListResponse:
    """Return a paginated, filtered list of audit log records.

    All query parameters are optional.  Omitting them returns all records,
    newest first.  The ``next_cursor`` field is ``null`` when there are no
    more pages.
    """
    from datetime import datetime, timezone  # noqa: PLC0415

    after_dt: datetime | None = None
    before_dt: datetime | None = None

    if from_date:
        try:
            after_dt = datetime.fromisoformat(from_date)
            if after_dt.tzinfo is None:
                after_dt = after_dt.replace(tzinfo=timezone.utc)
        except ValueError:
            pass

    if to_date:
        try:
            before_dt = datetime.fromisoformat(to_date)
            if before_dt.tzinfo is None:
                before_dt = before_dt.replace(tzinfo=timezone.utc)
        except ValueError:
            pass

    # Fetch limit+1 rows to detect whether a next page exists.
    rows = await repo.query_page(
        actor_id=actor_id,
        resource_type=resource_type,
        action=event_type,
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
        next_cursor = _encode_cursor(last["created_at"], last["id"])

    # Total count for the filter set (without cursor, for UI display).
    total_count = await repo.count_query(
        actor_id=actor_id,
        resource_type=resource_type,
        action=event_type,
        after=after_dt,
        before=before_dt,
    )

    entries = [AuditLogEntry.model_validate(r) for r in page]
    return AuditLogListResponse(
        audit_logs=entries,
        next_cursor=next_cursor,
        total_count=total_count,
    )
