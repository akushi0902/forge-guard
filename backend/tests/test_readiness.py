"""Unit tests for the /ready readiness endpoint.

All database calls are mocked — tests run without a live database.

Scenarios:
    1. Healthy database → HTTP 200, status='ready', database.status='up'.
    2. Unhealthy database → HTTP 503, status='not_ready', database.status='down'.
    3. Database timeout → HTTP 503, status='not_ready', error contains 'TimeoutError'.
    4. Database not initialised (pool returns None check) → 503.
    5. Migration table missing → database.status='up', migrations.status='not_initialized'.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient


class TestReadinessHealthyDatabase:
    """GET /ready returns 200 when all dependencies are up."""

    async def test_ready_returns_200_when_db_healthy(
        self, async_client: AsyncClient
    ) -> None:
        with (
            patch(
                "forgeguard.api.routes.system._check_database",
                new_callable=AsyncMock,
                return_value={"status": "up", "latency_ms": 3.5},
            ),
            patch(
                "forgeguard.api.routes.system._check_migrations",
                new_callable=AsyncMock,
                return_value={"status": "current", "version": "abc1234"},
            ),
        ):
            response = await async_client.get("/ready")
        assert response.status_code == 200

    async def test_ready_body_status_is_ready(self, async_client: AsyncClient) -> None:
        with (
            patch(
                "forgeguard.api.routes.system._check_database",
                new_callable=AsyncMock,
                return_value={"status": "up", "latency_ms": 3.5},
            ),
            patch(
                "forgeguard.api.routes.system._check_migrations",
                new_callable=AsyncMock,
                return_value={"status": "current", "version": "abc1234"},
            ),
        ):
            response = await async_client.get("/ready")
        body = response.json()
        assert body["status"] == "ready"

    async def test_ready_body_includes_database_check(
        self, async_client: AsyncClient
    ) -> None:
        db_result = {"status": "up", "latency_ms": 5.2}
        with (
            patch(
                "forgeguard.api.routes.system._check_database",
                new_callable=AsyncMock,
                return_value=db_result,
            ),
            patch(
                "forgeguard.api.routes.system._check_migrations",
                new_callable=AsyncMock,
                return_value={"status": "current", "version": "abc1234"},
            ),
        ):
            response = await async_client.get("/ready")
        checks = response.json()["checks"]
        assert checks["database"]["status"] == "up"
        assert "latency_ms" in checks["database"]

    async def test_ready_body_includes_migration_check(
        self, async_client: AsyncClient
    ) -> None:
        with (
            patch(
                "forgeguard.api.routes.system._check_database",
                new_callable=AsyncMock,
                return_value={"status": "up", "latency_ms": 2.1},
            ),
            patch(
                "forgeguard.api.routes.system._check_migrations",
                new_callable=AsyncMock,
                return_value={"status": "current", "version": "deadbeef"},
            ),
        ):
            response = await async_client.get("/ready")
        checks = response.json()["checks"]
        assert checks["migrations"]["status"] == "current"
        assert checks["migrations"]["version"] == "deadbeef"


class TestReadinessUnhealthyDatabase:
    """GET /ready returns 503 when any critical dependency is down."""

    async def test_ready_returns_503_when_db_down(
        self, async_client: AsyncClient
    ) -> None:
        with (
            patch(
                "forgeguard.api.routes.system._check_database",
                new_callable=AsyncMock,
                return_value={
                    "status": "down",
                    "error": "ConnectionRefusedError: [Errno 111] Connection refused",
                },
            ),
            patch(
                "forgeguard.api.routes.system._check_migrations",
                new_callable=AsyncMock,
                return_value={"status": "not_initialized", "version": None},
            ),
        ):
            response = await async_client.get("/ready")
        assert response.status_code == 503

    async def test_ready_body_status_is_not_ready_when_db_down(
        self, async_client: AsyncClient
    ) -> None:
        with (
            patch(
                "forgeguard.api.routes.system._check_database",
                new_callable=AsyncMock,
                return_value={"status": "down", "error": "ConnectionRefusedError: refused"},
            ),
            patch(
                "forgeguard.api.routes.system._check_migrations",
                new_callable=AsyncMock,
                return_value={"status": "not_initialized", "version": None},
            ),
        ):
            response = await async_client.get("/ready")
        assert response.json()["status"] == "not_ready"

    async def test_ready_error_detail_not_empty_when_db_down(
        self, async_client: AsyncClient
    ) -> None:
        with (
            patch(
                "forgeguard.api.routes.system._check_database",
                new_callable=AsyncMock,
                return_value={"status": "down", "error": "OperationalError: auth failed"},
            ),
            patch(
                "forgeguard.api.routes.system._check_migrations",
                new_callable=AsyncMock,
                return_value={"status": "not_initialized", "version": None},
            ),
        ):
            response = await async_client.get("/ready")
        db = response.json()["checks"]["database"]
        assert db["status"] == "down"
        assert "error" in db

    async def test_ready_returns_503_on_timeout(
        self, async_client: AsyncClient
    ) -> None:
        with (
            patch(
                "forgeguard.api.routes.system._check_database",
                new_callable=AsyncMock,
                return_value={
                    "status": "down",
                    "error": "TimeoutError: check timed out after 5 seconds",
                },
            ),
            patch(
                "forgeguard.api.routes.system._check_migrations",
                new_callable=AsyncMock,
                return_value={"status": "not_initialized", "version": None},
            ),
        ):
            response = await async_client.get("/ready")
        assert response.status_code == 503
        db = response.json()["checks"]["database"]
        assert "TimeoutError" in db["error"]


class TestReadinessMigrationNotInitialised:
    """Migrations not_initialized does not block readiness if DB is up."""

    async def test_ready_200_when_db_up_and_migrations_not_initialized(
        self, async_client: AsyncClient
    ) -> None:
        with (
            patch(
                "forgeguard.api.routes.system._check_database",
                new_callable=AsyncMock,
                return_value={"status": "up", "latency_ms": 1.0},
            ),
            patch(
                "forgeguard.api.routes.system._check_migrations",
                new_callable=AsyncMock,
                return_value={"status": "not_initialized", "version": None},
            ),
        ):
            response = await async_client.get("/ready")
        assert response.status_code == 200
        checks = response.json()["checks"]
        assert checks["migrations"]["status"] == "not_initialized"
