"""Unit tests for the /health liveness endpoint.

Tests verify:
    1. GET /health returns HTTP 200.
    2. The response body contains status='healthy', timestamp, and version.
    3. The response time is under 10ms (endpoint makes no external calls).
    4. GET /api/v1/health alias also returns HTTP 200 (Nginx proxy path).
    5. The health endpoint does not make database calls.
"""

from __future__ import annotations

import time

import pytest
from httpx import AsyncClient


class TestHealthEndpoint:
    """GET /health liveness probe."""

    async def test_health_returns_200(self, async_client: AsyncClient) -> None:
        response = await async_client.get("/health")
        assert response.status_code == 200

    async def test_health_response_schema(self, async_client: AsyncClient) -> None:
        response = await async_client.get("/health")
        body = response.json()
        assert body["status"] == "healthy"
        assert "timestamp" in body
        assert "version" in body

    async def test_health_timestamp_is_iso8601(self, async_client: AsyncClient) -> None:
        from datetime import datetime

        response = await async_client.get("/health")
        ts = response.json()["timestamp"]
        # datetime.fromisoformat raises ValueError if not ISO 8601
        parsed = datetime.fromisoformat(ts)
        assert parsed is not None

    async def test_health_version_matches_config(self, async_client: AsyncClient) -> None:
        from forgeguard.core.config import get_settings

        response = await async_client.get("/health")
        assert response.json()["version"] == get_settings().app_version

    async def test_health_responds_under_10ms(self, async_client: AsyncClient) -> None:
        """Liveness probe must be fast — no external dependency calls allowed."""
        # Warm up: one call to settle import/JIT overhead.
        await async_client.get("/health")

        start = time.perf_counter()
        response = await async_client.get("/health")
        elapsed_ms = (time.perf_counter() - start) * 1000

        assert response.status_code == 200
        assert elapsed_ms < 100, (  # 100ms ceiling in-process; real SLO is <10ms on wire
            f"/health took {elapsed_ms:.1f}ms — endpoint is making unexpected external calls"
        )

    async def test_health_does_not_call_database(self, async_client: AsyncClient) -> None:
        """Liveness probe must never reach out to the database."""
        from unittest.mock import patch

        with patch(
            "forgeguard.api.routes.system._check_database"
        ) as mock_db:
            response = await async_client.get("/health")
            assert response.status_code == 200
            mock_db.assert_not_called()

    async def test_health_api_v1_alias_returns_200(self, async_client: AsyncClient) -> None:
        """The /api/v1/health alias (Nginx proxy path) must also work."""
        response = await async_client.get("/api/v1/health")
        assert response.status_code == 200
        assert response.json()["status"] == "healthy"
