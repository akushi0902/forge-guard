"""Policy Guardian CRUD REST API endpoints (WO-035).

Routes:
    GET    /api/v1/policies                          — list with cursor pagination
    POST   /api/v1/policies                          — create policy
    PUT    /api/v1/policies/{id}                     — update policy
    POST   /api/v1/policies/{id}/rules               — create rule under policy
    PUT    /api/v1/policies/{id}/rules/{rule_id}     — update rule
    PATCH  /api/v1/policies/{id}/rules/{rule_id}/toggle — toggle rule is_active

Only Platform Admin (policy.manage permission) may mutate; SERVICE_VIEW required
for reads.  RBAC is enforced by route_permissions.py middleware and the
_require_policy_manage Depends() guard on mutation handlers.
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Annotated, Any, Optional

import asyncpg
import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import JSONResponse

from forgeguard.api.dependencies.audit import get_audit_service
from forgeguard.api.dependencies.auth import CurrentUser, CurrentUserDep
from forgeguard.api.schemas.audit import AuditLogEntry, AuditLogListResponse
from forgeguard.api.schemas.policy import (
    PolicyCreate,
    PolicyListResponse,
    PolicyResponse,
    PolicyRuleCreate,
    PolicyRuleResponse,
    PolicyRuleUpdate,
    PolicyUpdate,
)
from forgeguard.core.dependencies import get_pool
from forgeguard.core.permissions import Permissions, has_permission
from forgeguard.data.repositories.audit_logs import AuditLogRepository
from forgeguard.data.repositories.policies import PolicyRepository
from forgeguard.services.audit import AuditService
from forgeguard.services.policy_guardian import PolicyGuardianService

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/api/v1/policies", tags=["policies"])

_FORBIDDEN_MSG = (
    "This action requires the policy.manage permission assigned to the "
    "Platform Admin role. Contact your Platform Admin for access."
)


# ---------------------------------------------------------------------------
# Dependency providers
# ---------------------------------------------------------------------------


async def get_policy_repo(pool: asyncpg.Pool = Depends(get_pool)) -> PolicyRepository:
    return PolicyRepository(pool)


async def get_policy_guardian_service(
    repo: PolicyRepository = Depends(get_policy_repo),
    audit_svc: AuditService = Depends(get_audit_service),
) -> PolicyGuardianService:
    return PolicyGuardianService(repo, audit_svc)


async def get_audit_repo(pool: asyncpg.Pool = Depends(get_pool)) -> AuditLogRepository:
    return AuditLogRepository(pool)


async def _require_policy_manage(current_user: CurrentUserDep) -> CurrentUser:
    """Enforce policy.manage permission and return the authenticated user."""
    if not has_permission(current_user.role, Permissions.POLICY_MANAGE):
        raise HTTPException(
            status_code=403,
            detail={
                "error": {
                    "code": "forbidden",
                    "message": _FORBIDDEN_MSG,
                    "details": None,
                }
            },
        )
    return current_user


PolicyManageDep = Annotated[CurrentUser, Depends(_require_policy_manage)]


async def _require_audit_trail_access(current_user: CurrentUserDep) -> CurrentUser:
    """Enforce audit.view OR policy.manage permission for the audit trail endpoint.

    Platform Admin and Engineering Manager can read the audit trail.
    """
    if has_permission(current_user.role, Permissions.AUDIT_VIEW) or has_permission(
        current_user.role, Permissions.POLICY_MANAGE
    ):
        return current_user
    raise HTTPException(
        status_code=403,
        detail={
            "error": {
                "code": "forbidden",
                "message": (
                    "Audit trail access requires audit.view or policy.manage permission "
                    "(Platform Admin or Engineering Manager role)."
                ),
                "details": None,
            }
        },
    )


AuditTrailDep = Annotated[CurrentUser, Depends(_require_audit_trail_access)]


# ---------------------------------------------------------------------------
# Serialization helpers
# ---------------------------------------------------------------------------


def _policy_response(row: dict[str, Any], rule_count: int | None = None) -> PolicyResponse:
    return PolicyResponse(
        id=row["id"],
        name=row["name"],
        dimension=row["dimension"],
        description=row.get("description"),
        is_active=row["is_active"],
        version=row["version"],
        created_by=row.get("created_by"),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        rule_count=rule_count if rule_count is not None else row.get("rule_count"),
    )


def _rule_response(row: dict[str, Any]) -> PolicyRuleResponse:
    weight = row["weight"]
    if not isinstance(weight, Decimal):
        weight = Decimal(str(weight))
    return PolicyRuleResponse(
        id=row["id"],
        policy_id=row["policy_id"],
        name=row["name"],
        rule_type=row["rule_type"],
        threshold_config=row.get("threshold_config"),
        severity=row["severity"],
        weight=weight,
        is_active=row["is_active"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get(
    "",
    response_model=PolicyListResponse,
    summary="List policies with cursor-based pagination",
)
async def list_policies(
    cursor: Optional[str] = Query(default=None),
    limit: int = Query(default=50, ge=1, le=100),
    svc: PolicyGuardianService = Depends(get_policy_guardian_service),
) -> PolicyListResponse:
    result = await svc.list_policies(cursor=cursor, limit=limit)
    items = [_policy_response(row) for row in result["items"]]
    return PolicyListResponse(
        items=items,
        next_cursor=result["next_cursor"],
        total_count=result["total_count"],
    )


@router.post(
    "",
    status_code=201,
    summary="Create a new policy",
)
async def create_policy(
    body: PolicyCreate,
    request: Request,
    current_user: PolicyManageDep,
    svc: PolicyGuardianService = Depends(get_policy_guardian_service),
) -> JSONResponse:
    try:
        created = await svc.create_policy(
            body.model_dump(),
            actor_id=str(current_user.user_id),
            actor_role=current_user.role,
        )
    except Exception as exc:
        if "duplicate" in str(exc).lower() or "unique" in str(exc).lower():
            raise HTTPException(
                status_code=409,
                detail={
                    "error": {
                        "code": "conflict",
                        "message": "A policy with this name already exists in the given dimension.",
                        "details": None,
                    }
                },
            )
        raise
    return JSONResponse(
        status_code=201,
        content=_policy_response(created).model_dump(mode="json"),
    )


@router.put(
    "/{policy_id}",
    summary="Update an existing policy",
)
async def update_policy(
    policy_id: uuid.UUID,
    body: PolicyUpdate,
    request: Request,
    current_user: PolicyManageDep,
    svc: PolicyGuardianService = Depends(get_policy_guardian_service),
) -> PolicyResponse:
    try:
        updated = await svc.update_policy(
            policy_id,
            body.model_dump(exclude_none=True),
            actor_id=str(current_user.user_id),
            actor_role=current_user.role,
            expected_version=body.expected_version,
        )
    except ValueError as exc:
        if "version mismatch" in str(exc).lower():
            raise HTTPException(
                status_code=409,
                detail={
                    "error": {
                        "code": "version_mismatch",
                        "message": str(exc),
                        "details": None,
                    }
                },
            )
        raise HTTPException(status_code=400, detail={"error": {"code": "bad_request", "message": str(exc), "details": None}})

    if updated is None:
        raise HTTPException(
            status_code=404,
            detail={"error": {"code": "not_found", "message": f"Policy {policy_id} not found", "details": None}},
        )
    return _policy_response(updated)


@router.post(
    "/{policy_id}/rules",
    status_code=201,
    summary="Create a rule under a policy",
)
async def create_rule(
    policy_id: uuid.UUID,
    body: PolicyRuleCreate,
    request: Request,
    current_user: PolicyManageDep,
    svc: PolicyGuardianService = Depends(get_policy_guardian_service),
) -> JSONResponse:
    data = body.model_dump()
    # Decimal is not JSON-serializable by default; convert to float for storage
    data["weight"] = float(data["weight"])

    created = await svc.create_rule(
        policy_id,
        data,
        actor_id=str(current_user.user_id),
        actor_role=current_user.role,
    )
    if created is None:
        raise HTTPException(
            status_code=404,
            detail={"error": {"code": "not_found", "message": f"Policy {policy_id} not found", "details": None}},
        )
    return JSONResponse(
        status_code=201,
        content=_rule_response(created).model_dump(mode="json"),
    )


@router.put(
    "/{policy_id}/rules/{rule_id}",
    summary="Update an existing rule",
)
async def update_rule(
    policy_id: uuid.UUID,
    rule_id: uuid.UUID,
    body: PolicyRuleUpdate,
    request: Request,
    current_user: PolicyManageDep,
    svc: PolicyGuardianService = Depends(get_policy_guardian_service),
) -> PolicyRuleResponse:
    data = body.model_dump(exclude_none=True)
    if "weight" in data and isinstance(data["weight"], Decimal):
        data["weight"] = float(data["weight"])

    updated = await svc.update_rule(
        policy_id,
        rule_id,
        data,
        actor_id=str(current_user.user_id),
        actor_role=current_user.role,
    )
    if updated is None:
        raise HTTPException(
            status_code=404,
            detail={"error": {"code": "not_found", "message": f"Rule {rule_id} not found under policy {policy_id}", "details": None}},
        )
    return _rule_response(updated)


@router.patch(
    "/{policy_id}/rules/{rule_id}/toggle",
    summary="Toggle the is_active flag on a rule",
)
async def toggle_rule(
    policy_id: uuid.UUID,
    rule_id: uuid.UUID,
    request: Request,
    current_user: PolicyManageDep,
    svc: PolicyGuardianService = Depends(get_policy_guardian_service),
) -> PolicyRuleResponse:
    updated = await svc.toggle_rule(
        policy_id,
        rule_id,
        actor_id=str(current_user.user_id),
        actor_role=current_user.role,
    )
    if updated is None:
        raise HTTPException(
            status_code=404,
            detail={"error": {"code": "not_found", "message": f"Rule {rule_id} not found under policy {policy_id}", "details": None}},
        )
    return _rule_response(updated)


@router.get(
    "/{policy_id}/audit-trail",
    response_model=AuditLogListResponse,
    summary="Get paginated audit trail for a specific policy",
)
async def get_policy_audit_trail(
    policy_id: uuid.UUID,
    current_user: AuditTrailDep,
    audit_repo: AuditLogRepository = Depends(get_audit_repo),
    cursor: Optional[str] = Query(default=None, description="Pagination cursor (opaque base64 token)."),
    limit: int = Query(default=50, ge=1, le=200, description="Maximum records per page."),
) -> AuditLogListResponse:
    """Return paginated audit history for a policy.

    Returns all audit records where ``resource_type = 'policy'`` AND
    ``resource_id = policy_id``, ordered newest-first.  Accessible by
    Platform Admin (policy.manage) and Engineering Manager (audit.view).
    """
    rows = await audit_repo.list_by_resource(
        "policy",
        policy_id,
        cursor=cursor,
        limit=limit + 1,
    )

    has_more = len(rows) > limit
    page = rows[:limit]

    next_cursor: Optional[str] = None
    if has_more and page:
        import base64  # noqa: PLC0415
        last = page[-1]
        raw = f"{last['created_at'].isoformat()}|{last['id']}"
        next_cursor = base64.b64encode(raw.encode()).decode()

    entries = [AuditLogEntry(**r) for r in page]
    total = await audit_repo.count_query(resource_type="policy", resource_id=policy_id)
    return AuditLogListResponse(audit_logs=entries, next_cursor=next_cursor, total_count=total)
