"""Pydantic schemas for RBAC Administration API (WO-028).

These models define the request/response contracts for the admin RBAC endpoints
at /api/v1/admin/rbac/*.  All responses expose unmasked email addresses (admin
view) — callers must have rbac.manage permission.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel

from forgeguard.core.permissions import UserRole
from forgeguard.core.validation import ForgeGuardBaseModel


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------

class UserListItem(BaseModel):
    """A single user in the paginated list response."""

    id: uuid.UUID
    email: str
    name: str
    role: str
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class UserListResponse(BaseModel):
    """Paginated response for the user list endpoint."""

    users: list[UserListItem]
    next_cursor: Optional[str]
    total_count: int


class UserDetailResponse(BaseModel):
    """Detailed view of a single user including resolved permissions."""

    id: uuid.UUID
    email: str
    name: str
    role: str
    is_active: bool
    permissions: list[str]
    created_at: datetime
    updated_at: Optional[datetime]

    model_config = {"from_attributes": True}


class UserStatusResponse(BaseModel):
    """Compact user profile returned after a status change."""

    id: uuid.UUID
    email: str
    name: str
    role: str
    is_active: bool

    model_config = {"from_attributes": True}


class RoleItem(BaseModel):
    """A single role with its complete permission set."""

    name: str
    permissions: list[str]


class RoleListResponse(BaseModel):
    """All six ForgeGuard roles with their permission sets."""

    roles: list[RoleItem]


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------

class RoleChangeRequest(ForgeGuardBaseModel):
    """Request body for the role-change endpoint."""

    role: UserRole


class StatusChangeRequest(ForgeGuardBaseModel):
    """Request body for the status-change endpoint."""

    is_active: bool
