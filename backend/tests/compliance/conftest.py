"""pytest fixtures for compliance integration tests.

Provides an asyncpg connection pool and helpers for the compliance test suite.
Tests in this directory require Docker (PostgreSQL testcontainer).
"""

from __future__ import annotations

import pytest
import pytest_asyncio


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
