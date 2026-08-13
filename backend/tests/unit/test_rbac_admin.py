"""Unit tests for RBAC Administration service (WO-028).

Coverage:
  - change_user_role: updates role, generates audit record
  - change_user_role: no-op (idempotent) when role unchanged
  - change_user_role: rejects demotion of last Platform Admin (409)
  - change_user_role: 404 for non-existent user
  - toggle_user_status: deactivates user and revokes tokens
  - toggle_user_status: reactivates user (no token revocation)
  - toggle_user_status: idempotent on repeated call
  - toggle_user_status: 404 for non-existent user
  - list_users: returns paginated result
  - get_user_detail: resolves permissions for role
  - get_user_detail: 404 for non-existent user
  - list_roles: static, returns all 6 roles with permissions
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from forgeguard.core.exceptions import ConflictError, NotFoundError
from forgeguard.core.permissions import Permissions, UserRole, get_permissions
from forgeguard.services.rbac import RBACAdminService
from tests.fixtures.admin import (
    developer_user,
    platform_admin_user,
    tech_lead_user,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_service(
    *,
    user_rows: dict | None = None,
    count_by_role: int = 2,
    count_all: int = 5,
    revoked_count: int = 2,
) -> tuple[RBACAdminService, MagicMock, MagicMock, MagicMock]:
    """Return (service, mock_user_repo, mock_token_repo, mock_audit)."""
    user_repo = AsyncMock()
    token_repo = AsyncMock()
    audit_svc = AsyncMock()

    user_repo.count_by_role.return_value = count_by_role
    user_repo.count_all.return_value = count_all
    user_repo.list_all.return_value = []
    token_repo.revoke_all_for_user.return_value = revoked_count
    audit_svc.log_event.return_value = {"id": uuid.uuid4()}

    if user_rows is not None:
        user_repo.get_by_id.return_value = user_rows.get("get")
        user_repo.update_role.return_value = user_rows.get("update_role")
        user_repo.update_status.return_value = user_rows.get("update_status")

    svc = RBACAdminService(user_repo, token_repo, audit_svc)
    return svc, user_repo, token_repo, audit_svc


_ADMIN_ID = uuid.uuid4()
_USER_ID = uuid.uuid4()


# ---------------------------------------------------------------------------
# change_user_role
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_change_user_role_success():
    """Role change persists and emits an audit record."""
    old_row = developer_user(user_id=_USER_ID)
    new_row = {**old_row, "role": UserRole.tech_lead.value}

    svc, user_repo, _, audit_svc = _make_service(
        user_rows={"get": old_row, "update_role": new_row},
    )

    result = await svc.change_user_role(
        admin_id=_ADMIN_ID,
        admin_role=UserRole.platform_admin.value,
        user_id=_USER_ID,
        new_role=UserRole.tech_lead.value,
    )

    assert result["role"] == UserRole.tech_lead.value
    assert set(result["permissions"]) == set(get_permissions(UserRole.tech_lead.value))
    user_repo.update_role.assert_awaited_once_with(_USER_ID, UserRole.tech_lead.value)
    audit_svc.log_event.assert_awaited_once()
    call_kwargs = audit_svc.log_event.call_args.kwargs
    assert call_kwargs["action"] == "role_change"
    assert call_kwargs["before_state"] == {"role": UserRole.developer.value}
    assert call_kwargs["after_state"] == {"role": UserRole.tech_lead.value}


@pytest.mark.asyncio
async def test_change_user_role_idempotent():
    """No update or audit when new role equals current role."""
    old_row = developer_user(user_id=_USER_ID)
    svc, user_repo, _, audit_svc = _make_service(
        user_rows={"get": old_row},
    )

    result = await svc.change_user_role(
        admin_id=_ADMIN_ID,
        admin_role=UserRole.platform_admin.value,
        user_id=_USER_ID,
        new_role=UserRole.developer.value,
    )

    assert result["role"] == UserRole.developer.value
    user_repo.update_role.assert_not_awaited()
    audit_svc.log_event.assert_not_awaited()


@pytest.mark.asyncio
async def test_change_user_role_last_admin_protection():
    """Demoting the last Platform Admin raises ConflictError."""
    admin_row = platform_admin_user(user_id=_USER_ID)
    svc, user_repo, _, _ = _make_service(
        user_rows={"get": admin_row},
        count_by_role=1,  # Only one platform_admin
    )

    with pytest.raises(ConflictError, match="last Platform Admin"):
        await svc.change_user_role(
            admin_id=_ADMIN_ID,
            admin_role=UserRole.platform_admin.value,
            user_id=_USER_ID,
            new_role=UserRole.developer.value,
        )

    user_repo.update_role.assert_not_awaited()


@pytest.mark.asyncio
async def test_change_user_role_allows_demotion_when_multiple_admins():
    """Demotion succeeds if there are >= 2 Platform Admins."""
    admin_row = platform_admin_user(user_id=_USER_ID)
    new_row = {**admin_row, "role": UserRole.developer.value}
    svc, user_repo, _, _ = _make_service(
        user_rows={"get": admin_row, "update_role": new_row},
        count_by_role=2,
    )

    result = await svc.change_user_role(
        admin_id=_ADMIN_ID,
        admin_role=UserRole.platform_admin.value,
        user_id=_USER_ID,
        new_role=UserRole.developer.value,
    )

    assert result["role"] == UserRole.developer.value
    user_repo.update_role.assert_awaited_once()


@pytest.mark.asyncio
async def test_change_user_role_not_found():
    """Raises NotFoundError when user does not exist."""
    svc, _, _, _ = _make_service(user_rows={"get": None})

    with pytest.raises(NotFoundError):
        await svc.change_user_role(
            admin_id=_ADMIN_ID,
            admin_role=UserRole.platform_admin.value,
            user_id=uuid.uuid4(),
            new_role=UserRole.tech_lead.value,
        )


# ---------------------------------------------------------------------------
# toggle_user_status
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_toggle_user_status_deactivate():
    """Deactivation revokes tokens and emits audit record."""
    active_row = developer_user(user_id=_USER_ID)
    inactive_row = {**active_row, "is_active": False}
    svc, _, token_repo, audit_svc = _make_service(
        user_rows={"get": active_row, "update_status": inactive_row},
        revoked_count=3,
    )

    result = await svc.toggle_user_status(
        admin_id=_ADMIN_ID,
        admin_role=UserRole.platform_admin.value,
        user_id=_USER_ID,
        is_active=False,
    )

    assert result["is_active"] is False
    token_repo.revoke_all_for_user.assert_awaited_once()
    audit_svc.log_event.assert_awaited_once()
    call_kwargs = audit_svc.log_event.call_args.kwargs
    assert call_kwargs["action"] == "status_change"
    assert call_kwargs["before_state"] == {"is_active": True}
    assert call_kwargs["after_state"] == {"is_active": False}


@pytest.mark.asyncio
async def test_toggle_user_status_reactivate():
    """Reactivation skips token revocation."""
    inactive_row = {**developer_user(user_id=_USER_ID), "is_active": False}
    active_row = {**inactive_row, "is_active": True}
    svc, _, token_repo, audit_svc = _make_service(
        user_rows={"get": inactive_row, "update_status": active_row},
    )

    result = await svc.toggle_user_status(
        admin_id=_ADMIN_ID,
        admin_role=UserRole.platform_admin.value,
        user_id=_USER_ID,
        is_active=True,
    )

    assert result["is_active"] is True
    token_repo.revoke_all_for_user.assert_not_awaited()
    audit_svc.log_event.assert_awaited_once()


@pytest.mark.asyncio
async def test_toggle_user_status_idempotent():
    """No audit record when status is already the requested value."""
    active_row = developer_user(user_id=_USER_ID)
    svc, _, token_repo, audit_svc = _make_service(
        user_rows={"get": active_row, "update_status": active_row},
    )

    result = await svc.toggle_user_status(
        admin_id=_ADMIN_ID,
        admin_role=UserRole.platform_admin.value,
        user_id=_USER_ID,
        is_active=True,
    )

    assert result["is_active"] is True
    token_repo.revoke_all_for_user.assert_not_awaited()
    audit_svc.log_event.assert_not_awaited()


@pytest.mark.asyncio
async def test_toggle_user_status_not_found():
    """Raises NotFoundError when user does not exist."""
    svc, _, _, _ = _make_service(user_rows={"get": None})

    with pytest.raises(NotFoundError):
        await svc.toggle_user_status(
            admin_id=_ADMIN_ID,
            admin_role=UserRole.platform_admin.value,
            user_id=uuid.uuid4(),
            is_active=False,
        )


# ---------------------------------------------------------------------------
# list_users
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_list_users_returns_pagination():
    """list_users returns users, next_cursor, and total_count."""
    rows = [developer_user(), tech_lead_user()]
    svc, user_repo, _, _ = _make_service(count_all=10)
    user_repo.list_all.return_value = rows

    result = await svc.list_users(limit=50)

    assert len(result["users"]) == 2
    assert result["total_count"] == 10
    assert result["next_cursor"] is None  # only 2 rows, limit 50


@pytest.mark.asyncio
async def test_list_users_cursor_when_more_results():
    """next_cursor is set when the result set is exactly limit+1."""
    rows = [developer_user() for _ in range(4)]
    svc, user_repo, _, _ = _make_service(count_all=20)
    # Requesting limit=3 — service fetches limit+1=4 rows to detect has_more.
    user_repo.list_all.return_value = rows

    result = await svc.list_users(limit=3)

    assert len(result["users"]) == 3
    assert result["next_cursor"] is not None  # 4 rows > limit=3


# ---------------------------------------------------------------------------
# get_user_detail
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_user_detail_resolves_permissions():
    """Permissions are resolved from the user's role."""
    row = platform_admin_user(user_id=_USER_ID)
    svc, user_repo, _, _ = _make_service(user_rows={"get": row})

    detail = await svc.get_user_detail(_USER_ID)

    assert detail["role"] == UserRole.platform_admin.value
    assert Permissions.RBAC_MANAGE in detail["permissions"]
    assert Permissions.POLICY_MANAGE in detail["permissions"]


@pytest.mark.asyncio
async def test_get_user_detail_not_found():
    """Raises NotFoundError for unknown user."""
    svc, _, _, _ = _make_service(user_rows={"get": None})

    with pytest.raises(NotFoundError):
        await svc.get_user_detail(uuid.uuid4())


# ---------------------------------------------------------------------------
# list_roles (static)
# ---------------------------------------------------------------------------

def test_list_roles_returns_all_six():
    """list_roles returns exactly 6 role entries."""
    roles = RBACAdminService.list_roles()
    role_names = [r["name"] for r in roles]
    assert len(roles) == 6
    for role in UserRole:
        assert role.value in role_names


def test_list_roles_platform_admin_has_all_permissions():
    """Platform Admin has all 10 permissions."""
    roles = RBACAdminService.list_roles()
    admin = next(r for r in roles if r["name"] == UserRole.platform_admin.value)
    for perm in vars(Permissions).values():
        if isinstance(perm, str) and not perm.startswith("_"):
            assert perm in admin["permissions"]
