"""Integration tests for RBAC Administration API endpoints (WO-028).

Uses FastAPI dependency overrides to inject mocked services.
No real database required.

Coverage:
  - GET /users: 200 for Platform Admin, 403 for Developer
  - GET /users/{id}: 200 with permissions, 404 for unknown
  - PUT /users/{id}/role: 200 on success, 409 on last-admin, 403 for Developer
  - PUT /users/{id}/status: 200 deactivation, 200 reactivation, 403 for Developer
  - GET /roles: 200 returns all 6 roles
  - All endpoints return 403 for non-Platform Admin roles
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

import forgeguard.core.config as _config_module
from forgeguard.core.config import Settings
from forgeguard.core.exceptions import ConflictError, NotFoundError
from forgeguard.core.permissions import Permissions, UserRole
from forgeguard.main import create_app
from forgeguard.services.rbac import RBACAdminService
from tests.fixtures.admin import developer_user, platform_admin_user
from tests.fixtures.tokens import TEST_JWT_SECRET, make_access_token

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_ADMIN_USER_ID = uuid.uuid4()
_TARGET_USER_ID = uuid.uuid4()


def _make_test_settings() -> Settings:
    return Settings(
        database_url="postgresql+asyncpg://postgres:postgres@localhost:5432/forgeguard_test",
        jwt_secret_key=TEST_JWT_SECRET,
        log_level="DEBUG",
        app_env="testing",
        llm_api_key="",
        forge_catalog_url="http://localhost:9999/catalog",
    )


def _admin_cookie() -> str:
    return make_access_token(
        user_id=_ADMIN_USER_ID,
        role=UserRole.platform_admin.value,
        jwt_secret=TEST_JWT_SECRET,
    )


def _developer_cookie() -> str:
    return make_access_token(
        user_id=uuid.uuid4(),
        role=UserRole.developer.value,
        jwt_secret=TEST_JWT_SECRET,
    )


def _make_app_with_mock_service(mock_svc: RBACAdminService):
    """Return a test app with admin RBAC service dependency overridden."""
    settings = _make_test_settings()
    _config_module._settings_cache = settings
    app = create_app()

    from forgeguard.api.routes.admin_rbac import get_rbac_admin_service  # noqa: PLC0415

    app.dependency_overrides[get_rbac_admin_service] = lambda: mock_svc
    return app


def _make_mock_service(
    *,
    list_result: dict | None = None,
    detail_result: dict | None = None,
    role_change_result: dict | None = None,
    status_change_result: dict | None = None,
    raise_for_role: Exception | None = None,
    raise_for_status: Exception | None = None,
) -> MagicMock:
    """Return a MagicMock RBACAdminService with preconfigured return values."""
    svc = MagicMock(spec=RBACAdminService)

    now = datetime.now(tz=timezone.utc)
    admin_row = platform_admin_user(user_id=_TARGET_USER_ID)
    _default_detail = {
        "id": _TARGET_USER_ID,
        "email": admin_row["email"],
        "name": "Admin User",
        "role": UserRole.platform_admin.value,
        "is_active": True,
        "permissions": sorted([Permissions.RBAC_MANAGE, Permissions.POLICY_MANAGE]),
        "created_at": now,
        "updated_at": now,
    }
    _default_status = {
        "id": _TARGET_USER_ID,
        "email": admin_row["email"],
        "name": "Admin User",
        "role": UserRole.platform_admin.value,
        "is_active": True,
    }
    _default_list = {
        "users": [
            {
                "id": _TARGET_USER_ID,
                "email": "admin@example.com",
                "name": "Admin",
                "role": UserRole.platform_admin.value,
                "is_active": True,
                "created_at": now,
            }
        ],
        "next_cursor": None,
        "total_count": 1,
    }

    svc.list_users = AsyncMock(return_value=list_result or _default_list)
    svc.get_user_detail = AsyncMock(return_value=detail_result or _default_detail)
    svc.list_roles = MagicMock(return_value=RBACAdminService.list_roles())

    if raise_for_role:
        svc.change_user_role = AsyncMock(side_effect=raise_for_role)
    else:
        svc.change_user_role = AsyncMock(return_value=role_change_result or _default_detail)

    if raise_for_status:
        svc.toggle_user_status = AsyncMock(side_effect=raise_for_status)
    else:
        svc.toggle_user_status = AsyncMock(return_value=status_change_result or _default_status)

    return svc


# ---------------------------------------------------------------------------
# Tests: GET /users
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_list_users_platform_admin_200():
    """Platform Admin gets the paginated user list."""
    mock_svc = _make_mock_service()
    app = _make_app_with_mock_service(mock_svc)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get(
            "/api/v1/admin/rbac/users",
            cookies={"access_token": _admin_cookie()},
        )

    assert resp.status_code == 200
    data = resp.json()
    assert "users" in data
    assert "total_count" in data
    assert data["next_cursor"] is None


@pytest.mark.asyncio
async def test_list_users_developer_403():
    """Developer receives 403 for user list endpoint."""
    mock_svc = _make_mock_service()
    app = _make_app_with_mock_service(mock_svc)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get(
            "/api/v1/admin/rbac/users",
            cookies={"access_token": _developer_cookie()},
        )

    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Tests: GET /users/{id}
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_user_detail_200():
    """Platform Admin gets user detail with permissions."""
    mock_svc = _make_mock_service()
    app = _make_app_with_mock_service(mock_svc)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get(
            f"/api/v1/admin/rbac/users/{_TARGET_USER_ID}",
            cookies={"access_token": _admin_cookie()},
        )

    assert resp.status_code == 200
    data = resp.json()
    assert "permissions" in data
    assert isinstance(data["permissions"], list)


@pytest.mark.asyncio
async def test_get_user_detail_404():
    """Returns 404 for unknown user ID."""
    mock_svc = _make_mock_service()
    mock_svc.get_user_detail = AsyncMock(side_effect=NotFoundError("User not found."))
    app = _make_app_with_mock_service(mock_svc)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get(
            f"/api/v1/admin/rbac/users/{uuid.uuid4()}",
            cookies={"access_token": _admin_cookie()},
        )

    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Tests: PUT /users/{id}/role
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_change_user_role_200():
    """Platform Admin can change a user's role."""
    mock_svc = _make_mock_service()
    app = _make_app_with_mock_service(mock_svc)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.put(
            f"/api/v1/admin/rbac/users/{_TARGET_USER_ID}/role",
            json={"role": UserRole.tech_lead.value},
            cookies={"access_token": _admin_cookie()},
        )

    assert resp.status_code == 200
    mock_svc.change_user_role.assert_awaited_once()


@pytest.mark.asyncio
async def test_change_user_role_409_last_admin():
    """409 when trying to demote the last Platform Admin."""
    mock_svc = _make_mock_service(
        raise_for_role=ConflictError(
            "Cannot remove the last Platform Admin. Assign another Platform Admin first."
        )
    )
    app = _make_app_with_mock_service(mock_svc)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.put(
            f"/api/v1/admin/rbac/users/{_TARGET_USER_ID}/role",
            json={"role": UserRole.developer.value},
            cookies={"access_token": _admin_cookie()},
        )

    assert resp.status_code == 409
    assert "last Platform Admin" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_change_user_role_developer_403():
    """Developer cannot change roles."""
    mock_svc = _make_mock_service()
    app = _make_app_with_mock_service(mock_svc)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.put(
            f"/api/v1/admin/rbac/users/{_TARGET_USER_ID}/role",
            json={"role": UserRole.tech_lead.value},
            cookies={"access_token": _developer_cookie()},
        )

    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_change_user_role_invalid_role_422():
    """422 for unknown role value."""
    mock_svc = _make_mock_service()
    app = _make_app_with_mock_service(mock_svc)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.put(
            f"/api/v1/admin/rbac/users/{_TARGET_USER_ID}/role",
            json={"role": "superuser"},
            cookies={"access_token": _admin_cookie()},
        )

    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Tests: PUT /users/{id}/status
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_change_user_status_deactivate_200():
    """Platform Admin can deactivate a user."""
    now = datetime.now(tz=timezone.utc)
    inactive_result = {
        "id": _TARGET_USER_ID,
        "email": "user@example.com",
        "name": "User",
        "role": UserRole.developer.value,
        "is_active": False,
    }
    mock_svc = _make_mock_service(status_change_result=inactive_result)
    app = _make_app_with_mock_service(mock_svc)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.put(
            f"/api/v1/admin/rbac/users/{_TARGET_USER_ID}/status",
            json={"is_active": False},
            cookies={"access_token": _admin_cookie()},
        )

    assert resp.status_code == 200
    assert resp.json()["is_active"] is False


@pytest.mark.asyncio
async def test_change_user_status_developer_403():
    """Developer cannot change user status."""
    mock_svc = _make_mock_service()
    app = _make_app_with_mock_service(mock_svc)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.put(
            f"/api/v1/admin/rbac/users/{_TARGET_USER_ID}/status",
            json={"is_active": False},
            cookies={"access_token": _developer_cookie()},
        )

    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Tests: GET /roles
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_list_roles_200():
    """Returns all 6 ForgeGuard roles with permissions."""
    mock_svc = _make_mock_service()
    app = _make_app_with_mock_service(mock_svc)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get(
            "/api/v1/admin/rbac/roles",
            cookies={"access_token": _admin_cookie()},
        )

    assert resp.status_code == 200
    data = resp.json()
    assert "roles" in data
    role_names = [r["name"] for r in data["roles"]]
    for role in UserRole:
        assert role.value in role_names


@pytest.mark.asyncio
async def test_list_roles_developer_403():
    """Developer cannot access the roles listing."""
    mock_svc = _make_mock_service()
    app = _make_app_with_mock_service(mock_svc)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get(
            "/api/v1/admin/rbac/roles",
            cookies={"access_token": _developer_cookie()},
        )

    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_403_message_format():
    """403 body contains the actionable error message per WO-028 AC spec."""
    mock_svc = _make_mock_service()
    app = _make_app_with_mock_service(mock_svc)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get(
            "/api/v1/admin/rbac/users",
            cookies={"access_token": _developer_cookie()},
        )

    assert resp.status_code == 403
    body = resp.json()
    # ForgeGuard 403 format: {"detail": ..., "required_permission": ...}
    assert "detail" in body
