"""RBAC Administration API endpoints (WO-028).

All endpoints require the ``rbac.manage`` permission (Platform Admin only).
Every role change and status change produces an immutable audit record.

Routes:
    GET  /api/v1/admin/rbac/users               — paginated user list
    GET  /api/v1/admin/rbac/users/{user_id}     — single user with permissions
    PUT  /api/v1/admin/rbac/users/{user_id}/role   — change user role
    PUT  /api/v1/admin/rbac/users/{user_id}/status — activate/deactivate user
    GET  /api/v1/admin/rbac/roles               — all roles with permissions
"""

from __future__ import annotations

import uuid
from typing import Annotated, Optional

import structlog
from fastapi import APIRouter, Depends, Query, Request

from forgeguard.api.dependencies.auth import CurrentUser, CurrentUserDep
from forgeguard.api.schemas.admin import (
    RoleChangeRequest,
    RoleListResponse,
    StatusChangeRequest,
    UserDetailResponse,
    UserListResponse,
    UserStatusResponse,
)
from forgeguard.core.permissions import Permissions, UserRole
from forgeguard.data.repositories.refresh_tokens import RefreshTokenRepository
from forgeguard.data.repositories.users import UserRepository
from forgeguard.services.audit import AuditService
from forgeguard.services.rbac import RBACAdminService, RBACService

logger = structlog.get_logger(__name__)

router = APIRouter(
    prefix="/api/v1/admin/rbac",
    tags=["admin", "rbac"],
)

_rbac = RBACService()


async def _require_rbac_manage(current_user: CurrentUserDep) -> CurrentUser:
    """Enforce rbac.manage permission and return the authenticated user."""
    _rbac.check_permission(current_user.role, Permissions.RBAC_MANAGE)
    return current_user


RBACManageDep = Annotated[CurrentUser, Depends(_require_rbac_manage)]


# ---------------------------------------------------------------------------
# Service dependency factory
# ---------------------------------------------------------------------------

async def get_rbac_admin_service(request: Request) -> RBACAdminService:
    """Construct RBACAdminService from the request-time asyncpg pool."""
    from forgeguard.data.database import get_pool  # noqa: PLC0415
    from forgeguard.data.repositories.audit_logs import AuditLogRepository  # noqa: PLC0415

    pool = await get_pool()
    user_repo = UserRepository(pool)
    token_repo = RefreshTokenRepository(pool)
    audit_repo = AuditLogRepository(pool)
    audit_svc = AuditService(audit_repo)
    return RBACAdminService(user_repo, token_repo, audit_svc)


RBACAdminServiceDep = Annotated[RBACAdminService, Depends(get_rbac_admin_service)]


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get(
    "/users",
    response_model=UserListResponse,
    summary="List all users (Platform Admin only)",
)
async def list_users(
    current_user: RBACManageDep,
    service: RBACAdminServiceDep,
    cursor: Optional[str] = Query(default=None, description="Opaque pagination cursor."),
    limit: int = Query(default=50, ge=1, le=100, description="Page size (max 100)."),
) -> UserListResponse:
    """Return a paginated list of all users with id, email, name, role, is_active, created_at."""
    result = await service.list_users(cursor=cursor, limit=limit)
    return UserListResponse(**result)


@router.get(
    "/users/{user_id}",
    response_model=UserDetailResponse,
    summary="Get a single user with resolved permissions (Platform Admin only)",
)
async def get_user_detail(
    user_id: uuid.UUID,
    current_user: RBACManageDep,
    service: RBACAdminServiceDep,
) -> UserDetailResponse:
    """Return a user's profile including the complete list of permissions their role grants."""
    detail = await service.get_user_detail(user_id)
    return UserDetailResponse(**detail)


@router.put(
    "/users/{user_id}/role",
    response_model=UserDetailResponse,
    summary="Change a user's role (Platform Admin only)",
)
async def change_user_role(
    user_id: uuid.UUID,
    body: RoleChangeRequest,
    current_user: RBACManageDep,
    service: RBACAdminServiceDep,
    request: Request,
) -> UserDetailResponse:
    """Update the user's role and return the updated profile.

    Idempotent: if the new role equals the current role, returns the unchanged
    user with no audit record written.

    Raises 409 if this would remove the last Platform Admin.
    """
    correlation_id = getattr(request.state, "correlation_id", None)
    new_role: str = body.role.value if hasattr(body.role, "value") else str(body.role)
    result = await service.change_user_role(
        admin_id=current_user.user_id,
        admin_role=current_user.role,
        user_id=user_id,
        new_role=new_role,
        correlation_id=str(correlation_id) if correlation_id else None,
    )
    return UserDetailResponse(**result)


@router.put(
    "/users/{user_id}/status",
    response_model=UserStatusResponse,
    summary="Activate or deactivate a user (Platform Admin only)",
)
async def change_user_status(
    user_id: uuid.UUID,
    body: StatusChangeRequest,
    current_user: RBACManageDep,
    service: RBACAdminServiceDep,
    request: Request,
) -> UserStatusResponse:
    """Set the user's ``is_active`` flag.

    On deactivation, all refresh tokens for the user are immediately revoked.
    Idempotent: if the user's status already matches ``is_active``, returns the
    unchanged user with no audit record written.
    """
    correlation_id = getattr(request.state, "correlation_id", None)
    result = await service.toggle_user_status(
        admin_id=current_user.user_id,
        admin_role=current_user.role,
        user_id=user_id,
        is_active=body.is_active,
        correlation_id=str(correlation_id) if correlation_id else None,
    )
    return UserStatusResponse(**result)


@router.get(
    "/roles",
    response_model=RoleListResponse,
    summary="List all roles with permissions (Platform Admin only)",
)
async def list_roles(
    current_user: RBACManageDep,
) -> RoleListResponse:
    """Return all six ForgeGuard roles with their complete permission sets."""
    roles = RBACAdminService.list_roles()
    return RoleListResponse(roles=roles)
