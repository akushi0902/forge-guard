"""pytest fixtures for asyncpg-based repository integration tests.

Builds on the session-scoped postgres_container, db_url, and apply_migrations
fixtures from the top-level conftest.py to provide an asyncpg pool and helper
factories for creating test records.
"""

from __future__ import annotations

import json
import uuid
from typing import Any

import pytest
import pytest_asyncio


# ---------------------------------------------------------------------------
# asyncpg pool fixture
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture(scope="session")
async def asyncpg_pool(db_url: str, apply_migrations: None):
    """Session-scoped asyncpg connection pool connected to the testcontainer.

    The db_url from the top-level conftest is in ``postgresql+asyncpg://``
    format; we strip the ``+asyncpg`` prefix before passing to asyncpg.
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


# ---------------------------------------------------------------------------
# Cleanup helper
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture()
async def clean_tables(asyncpg_pool):
    """Truncate domain tables in FK-safe order after each test."""
    yield
    async with asyncpg_pool.acquire() as conn:
        await conn.execute("""
            TRUNCATE TABLE
                audit_logs,
                release_decisions,
                release_assessments,
                findings,
                assessment_scores,
                assessments,
                policy_rules,
                policies,
                services,
                refresh_tokens,
                role_permissions,
                permissions,
                roles,
                users
            RESTART IDENTITY CASCADE
        """)


# ---------------------------------------------------------------------------
# Record factories
# ---------------------------------------------------------------------------


async def _insert_user(pool, **overrides) -> dict[str, Any]:
    """Insert a minimal valid user and return the row as a dict."""
    import asyncpg  # noqa: PLC0415

    data: dict[str, Any] = {
        "email": f"test_{uuid.uuid4().hex[:8]}@example.com",
        "password_hash": "$2b$12$" + "A" * 53,
        "role": "developer",
        "is_active": True,
        "failed_login_attempts": 0,
    }
    data.update(overrides)
    cols = ", ".join(data.keys())
    placeholders = ", ".join(f"${i + 1}" for i in range(len(data)))
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            f"INSERT INTO users ({cols}) VALUES ({placeholders}) RETURNING *",
            *data.values(),
        )
    return dict(row)


async def _insert_service(pool, **overrides) -> dict[str, Any]:
    """Insert a minimal valid service and return the row as a dict."""
    data: dict[str, Any] = {
        "name": f"svc_{uuid.uuid4().hex[:8]}",
        "metadata": "{}",
        "is_demo": False,
    }
    data.update(overrides)
    cols = ", ".join(data.keys())
    placeholders = ", ".join(f"${i + 1}" for i in range(len(data)))
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            f"INSERT INTO services ({cols}) VALUES ({placeholders}) RETURNING *",
            *data.values(),
        )
    return dict(row)


async def _insert_policy(pool, created_by_id=None, **overrides) -> dict[str, Any]:
    """Insert a minimal valid policy and return the row as a dict."""
    data: dict[str, Any] = {
        "name": f"policy_{uuid.uuid4().hex[:8]}",
        "dimension": "code_quality",
        "is_active": True,
        "version": 1,
    }
    if created_by_id:
        data["created_by"] = created_by_id
    data.update(overrides)
    cols = ", ".join(data.keys())
    placeholders = ", ".join(f"${i + 1}" for i in range(len(data)))
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            f"INSERT INTO policies ({cols}) VALUES ({placeholders}) RETURNING *",
            *data.values(),
        )
    return dict(row)


async def _insert_policy_rule(pool, policy_id, **overrides) -> dict[str, Any]:
    data: dict[str, Any] = {
        "policy_id": policy_id,
        "name": f"rule_{uuid.uuid4().hex[:8]}",
        "rule_type": "threshold",
        "threshold_config": "{}",
        "severity": "medium",
        "weight": "1.0",
        "is_active": True,
    }
    data.update(overrides)
    cols = ", ".join(data.keys())
    placeholders = ", ".join(f"${i + 1}" for i in range(len(data)))
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            f"INSERT INTO policy_rules ({cols}) VALUES ({placeholders}) RETURNING *",
            *data.values(),
        )
    return dict(row)


async def _insert_assessment(pool, service_id, **overrides) -> dict[str, Any]:
    data: dict[str, Any] = {
        "service_id": service_id,
        "assessment_type": "health_check",
        "trigger_type": "manual",
        "status": "completed",
    }
    data.update(overrides)
    cols = ", ".join(data.keys())
    placeholders = ", ".join(f"${i + 1}" for i in range(len(data)))
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            f"INSERT INTO assessments ({cols}) VALUES ({placeholders}) RETURNING *",
            *data.values(),
        )
    return dict(row)


@pytest.fixture()
def insert_user(asyncpg_pool):
    async def _factory(**kwargs):
        return await _insert_user(asyncpg_pool, **kwargs)
    return _factory


@pytest.fixture()
def insert_service(asyncpg_pool):
    async def _factory(**kwargs):
        return await _insert_service(asyncpg_pool, **kwargs)
    return _factory


@pytest.fixture()
def insert_policy(asyncpg_pool):
    async def _factory(**kwargs):
        return await _insert_policy(asyncpg_pool, **kwargs)
    return _factory


@pytest.fixture()
def insert_policy_rule(asyncpg_pool):
    async def _factory(policy_id, **kwargs):
        return await _insert_policy_rule(asyncpg_pool, policy_id, **kwargs)
    return _factory


@pytest.fixture()
def insert_assessment(asyncpg_pool):
    async def _factory(service_id, **kwargs):
        return await _insert_assessment(asyncpg_pool, service_id, **kwargs)
    return _factory
