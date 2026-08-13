"""Schema-level tests for the Identity and Access domain tables.

All tests in this module require a live PostgreSQL instance.  They are
automatically skipped when the database is unreachable so that the standard
unit-test suite can run without infrastructure dependencies.

The tests exercise:
    1. Table creation via SQLAlchemy metadata (not Alembic).
    2. CHECK constraint enforcement on users.role.
    3. UNIQUE constraint enforcement on users.email.
    4. NOT NULL enforcement on required columns.
    5. FK CASCADE: deleting a User removes its RefreshTokens.
    6. Composite PK on role_permissions prevents duplicate grants.
    7. Soft-delete column exists and accepts NULL / non-NULL values.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from forgeguard.core.config import get_settings
from forgeguard.data.models import Base, Permission, RefreshToken, Role, RolePermission, User


# ---------------------------------------------------------------------------
# Module-level fixtures — database availability check
# ---------------------------------------------------------------------------

def _is_db_available() -> bool:
    """Return True if a test PostgreSQL instance is reachable."""
    import asyncio

    async def _check() -> bool:
        engine = create_async_engine(get_settings().database_url, pool_pre_ping=True)
        try:
            async with engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
            return True
        except (OperationalError, Exception):
            return False
        finally:
            await engine.dispose()

    try:
        return asyncio.get_event_loop().run_until_complete(_check())
    except Exception:
        return False


_DB_AVAILABLE = _is_db_available()
pytestmark = pytest.mark.skipif(not _DB_AVAILABLE, reason="PostgreSQL not available")


# ---------------------------------------------------------------------------
# Test-scoped engine + session fixtures
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture(scope="module")
async def db_engine():
    """Create a fresh engine, build all tables, yield, then drop them."""
    engine = create_async_engine(get_settings().database_url, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture()
async def session(db_engine):
    """Yield an AsyncSession that is rolled back after each test."""
    factory = async_sessionmaker(db_engine, expire_on_commit=False)
    async with factory() as sess:
        async with sess.begin():
            yield sess
            await sess.rollback()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_user(**kwargs) -> User:
    defaults = {
        "id": uuid.uuid4(),
        "email": f"test-{uuid.uuid4().hex[:8]}@example.com",
        "password_hash": "$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8y7.xXj4pF.mY0gLXWc",
        "role": "developer",
        "is_active": True,
        "failed_login_attempts": 0,
    }
    defaults.update(kwargs)
    return User(**defaults)


def _make_role(name: str | None = None) -> Role:
    return Role(id=uuid.uuid4(), name=name or f"role-{uuid.uuid4().hex[:8]}")


def _make_permission(name: str | None = None) -> Permission:
    return Permission(id=uuid.uuid4(), name=name or f"perm-{uuid.uuid4().hex[:8]}")


# ---------------------------------------------------------------------------
# Users table — basic CRUD
# ---------------------------------------------------------------------------

class TestUserInsert:
    async def test_insert_valid_user(self, session: AsyncSession) -> None:
        user = _make_user()
        session.add(user)
        await session.flush()
        result = await session.get(User, user.id)
        assert result is not None
        assert result.email == user.email

    async def test_user_defaults_applied(self, session: AsyncSession) -> None:
        user = _make_user()
        session.add(user)
        await session.flush()
        result = await session.get(User, user.id)
        assert result is not None
        assert result.is_active is True
        assert result.failed_login_attempts == 0
        assert result.deleted_at is None
        assert result.locked_until is None


# ---------------------------------------------------------------------------
# Users table — constraint violations
# ---------------------------------------------------------------------------

class TestUserConstraints:
    async def test_duplicate_email_raises_integrity_error(
        self, session: AsyncSession
    ) -> None:
        email = f"dup-{uuid.uuid4().hex[:6]}@example.com"
        user_a = _make_user(email=email)
        user_b = _make_user(email=email)
        session.add(user_a)
        await session.flush()
        session.add(user_b)
        with pytest.raises(IntegrityError, match="uq_users_email|unique"):
            await session.flush()

    async def test_invalid_role_raises_check_violation(
        self, session: AsyncSession
    ) -> None:
        user = _make_user(role="not_a_real_role")
        session.add(user)
        with pytest.raises(IntegrityError, match="ck_users_valid_role|check"):
            await session.flush()

    async def test_all_valid_roles_accepted(self, session: AsyncSession) -> None:
        valid_roles = (
            "developer",
            "tech_lead",
            "security_reviewer",
            "platform_admin",
            "engineering_manager",
            "operator",
        )
        for role in valid_roles:
            user = _make_user(role=role)
            session.add(user)
        await session.flush()

    async def test_null_password_hash_rejected(self, session: AsyncSession) -> None:
        user = _make_user()
        user.password_hash = None  # type: ignore[assignment]
        session.add(user)
        with pytest.raises(IntegrityError):
            await session.flush()


# ---------------------------------------------------------------------------
# Soft-delete semantics
# ---------------------------------------------------------------------------

class TestUserSoftDelete:
    async def test_deleted_at_accepts_timestamp(self, session: AsyncSession) -> None:
        user = _make_user(deleted_at=datetime(2026, 1, 1, tzinfo=timezone.utc))
        session.add(user)
        await session.flush()
        result = await session.get(User, user.id)
        assert result is not None
        assert result.deleted_at is not None

    async def test_deleted_at_is_null_by_default(self, session: AsyncSession) -> None:
        user = _make_user()
        session.add(user)
        await session.flush()
        result = await session.get(User, user.id)
        assert result is not None
        assert result.deleted_at is None


# ---------------------------------------------------------------------------
# RefreshToken — FK CASCADE
# ---------------------------------------------------------------------------

class TestRefreshTokenCascade:
    async def test_delete_user_cascades_to_refresh_tokens(
        self, session: AsyncSession
    ) -> None:
        user = _make_user()
        session.add(user)
        await session.flush()

        token = RefreshToken(
            id=uuid.uuid4(),
            user_id=user.id,
            token_hash="a" * 64,
            expires_at=datetime(2027, 1, 1, tzinfo=timezone.utc),
        )
        session.add(token)
        await session.flush()

        # Deleting the user must cascade to refresh_tokens
        await session.delete(user)
        await session.flush()

        result = await session.get(RefreshToken, token.id)
        assert result is None, "RefreshToken was not deleted on User cascade"


# ---------------------------------------------------------------------------
# RolePermission — composite PK
# ---------------------------------------------------------------------------

class TestRolePermissionCompositePK:
    async def test_duplicate_grant_raises_integrity_error(
        self, session: AsyncSession
    ) -> None:
        role = _make_role()
        perm = _make_permission()
        session.add_all([role, perm])
        await session.flush()

        rp1 = RolePermission(role_id=role.id, permission_id=perm.id)
        rp2 = RolePermission(role_id=role.id, permission_id=perm.id)
        session.add(rp1)
        await session.flush()
        session.add(rp2)
        with pytest.raises(IntegrityError, match="pk_role_permissions|unique|duplicate"):
            await session.flush()

    async def test_same_permission_different_roles_allowed(
        self, session: AsyncSession
    ) -> None:
        perm = _make_permission()
        role_a = _make_role()
        role_b = _make_role()
        session.add_all([perm, role_a, role_b])
        await session.flush()

        session.add(RolePermission(role_id=role_a.id, permission_id=perm.id))
        session.add(RolePermission(role_id=role_b.id, permission_id=perm.id))
        await session.flush()
