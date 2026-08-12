"""pytest fixtures for compliance integration tests.

Provides an asyncpg connection pool and helpers for the compliance test suite.

The ``rbac_client`` fixture provides a cookie-authenticated AsyncClient for
RBAC enforcement tests (WO-098).  It uses the JWT cookie mechanism that the
``AuthenticationMiddleware`` actually reads (``access_token`` cookie), rather
than the Authorization header used by the older ``authenticated_client``
fixture.  No database is required for RBAC unit tests.

Tests that interact with the database require Docker (PostgreSQL testcontainer).
"""

from __future__ import annotations

import contextlib
import uuid
from datetime import datetime, timedelta, timezone
from typing import AsyncGenerator, Callable

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from forgeguard.core.config import Settings


@pytest_asyncio.fixture(scope="session")
async def asyncpg_pool(db_url: str, apply_migrations: None):
    """Session-scoped asyncpg connection pool connected to the testcontainer.

    Mirrors the equivalent fixture in tests/data/conftest.py so compliance
    tests can run independently without depending on data conftest scope.
    """
    try:
        import asyncpg  # noqa: PLC0415
    except ImportError:
        pytest.skip("asyncpg not installed")

    dsn = db_url
    if dsn.startswith("postgresql+asyncpg://"):
        dsn = "postgresql://" + dsn[len("postgresql+asyncpg://"):]

    pool = await asyncpg.create_pool(
        dsn=dsn,
        min_size=1,
        max_size=5,
        command_timeout=30,
    )
    yield pool
    await pool.close()


@pytest_asyncio.fixture()
async def audit_clean(asyncpg_pool):
    """Truncate audit_logs before and after each compliance test.

    Uses TRUNCATE (not DELETE) so the immutability trigger is not invoked.
    """
    async with asyncpg_pool.acquire() as conn:
        await conn.execute("TRUNCATE TABLE audit_logs")
    yield
    async with asyncpg_pool.acquire() as conn:
        await conn.execute("TRUNCATE TABLE audit_logs")


@pytest.fixture()
def audit_service(asyncpg_pool):
    """Return an AuditService backed by the testcontainer pool."""
    from forgeguard.data.repositories.audit_logs import AuditLogRepository  # noqa: PLC0415
    from forgeguard.services.audit import AuditService  # noqa: PLC0415

    repo = AuditLogRepository(pool=asyncpg_pool)
    return AuditService(audit_repo=repo)


# ---------------------------------------------------------------------------
# RBAC test fixtures (WO-098) — no database required
# ---------------------------------------------------------------------------

def _make_rbac_jwt(role: str, settings: Settings, *, expires_delta: timedelta | None = None) -> str:
    """Create a signed JWT stored in the ``access_token`` cookie.

    The ``AuthenticationMiddleware`` reads from the cookie (not the
    ``Authorization`` header), so tests must inject this way.
    """
    import jwt  # PyJWT  # noqa: PLC0415

    if expires_delta is None:
        expires_delta = timedelta(minutes=15)
    now = datetime.now(tz=timezone.utc)
    payload = {
        "sub": str(uuid.uuid4()),
        "role": role,
        "iat": now,
        "exp": now + expires_delta,
        "jti": str(uuid.uuid4()),
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm="HS256")


@pytest_asyncio.fixture()
async def rbac_client(
    app: FastAPI,
    test_settings: Settings,
) -> AsyncGenerator[Callable[[str], AsyncClient], None]:
    """Factory fixture returning a cookie-authenticated AsyncClient for a given role.

    Uses the ``access_token`` httpOnly cookie that
    ``AuthenticationMiddleware`` actually reads.  No database required.

    Usage::

        async def test_admin_access(rbac_client):
            client = await rbac_client("platform_admin")
            response = await client.get("/api/v1/admin/rbac/users")
            assert response.status_code != 403

    All clients are closed automatically after the test.
    """
    created: list[AsyncClient] = []

    async def _factory(role: str = "developer") -> AsyncClient:
        token = _make_rbac_jwt(role, test_settings)
        client = AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://testserver",
            cookies={"access_token": token},
        )
        await client.__aenter__()
        created.append(client)
        return client

    yield _factory

    for c in created:
        with contextlib.suppress(Exception):
            await c.__aexit__(None, None, None)
