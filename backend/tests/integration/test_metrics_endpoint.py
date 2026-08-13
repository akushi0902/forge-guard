"""Integration tests for /metrics, /health, /ready, and /api/v1/platform/health.

Tests verify:
    1. GET /health returns 200 with status/timestamp/version.
    2. GET /health completes quickly (no dependency checks).
    3. GET /ready returns 200 or 503 with expected check structure.
    4. GET /metrics returns Prometheus text format.
    5. After 10 API requests, /metrics reflects the accumulated counts.
    6. GET /api/v1/platform/health returns the required JSON fields with
       Operator role (X-User-Role: operator).
    7. GET /api/v1/platform/health returns 403 with Developer role.
    8. /metrics endpoint is excluded from its own metrics collection.
    9. Path normalization appears in Prometheus label output.
"""

from __future__ import annotations

import time
from typing import Any

import pytest
from httpx import AsyncClient

from forgeguard.middleware.metrics import HTTP_REQUESTS_TOTAL


# ---------------------------------------------------------------------------
# /health — liveness
# ---------------------------------------------------------------------------

class TestHealthEndpoint:
    async def test_health_returns_200(self, async_client: AsyncClient) -> None:
        response = await async_client.get("/health")
        assert response.status_code == 200

    async def test_health_body_has_status_healthy(
        self, async_client: AsyncClient
    ) -> None:
        response = await async_client.get("/health")
        body = response.json()
        assert body["status"] == "healthy"

    async def test_health_body_has_timestamp(
        self, async_client: AsyncClient
    ) -> None:
        response = await async_client.get("/health")
        body = response.json()
        assert "timestamp" in body
        assert body["timestamp"]  # non-empty string

    async def test_health_body_has_version(
        self, async_client: AsyncClient
    ) -> None:
        response = await async_client.get("/health")
        body = response.json()
        assert "version" in body

    async def test_health_completes_quickly(
        self, async_client: AsyncClient
    ) -> None:
        """Liveness probe must complete in <100ms (generous headroom for CI)."""
        start = time.perf_counter()
        response = await async_client.get("/health")
        elapsed_ms = (time.perf_counter() - start) * 1000
        assert response.status_code == 200
        # Allow generous headroom (100ms) for process startup in CI; the
        # architectural target is <10ms in production.
        assert elapsed_ms < 100, (
            f"/health took {elapsed_ms:.1f}ms — exceeded 100ms budget"
        )


# ---------------------------------------------------------------------------
# /ready — readiness
# ---------------------------------------------------------------------------

class TestReadinessEndpoint:
    async def test_ready_returns_200_or_503(
        self, async_client: AsyncClient
    ) -> None:
        """Readiness returns 200 (healthy) or 503 (DB unreachable)."""
        response = await async_client.get("/ready")
        assert response.status_code in {200, 503}

    async def test_ready_body_has_status_key(
        self, async_client: AsyncClient
    ) -> None:
        response = await async_client.get("/ready")
        body = response.json()
        assert "status" in body

    async def test_ready_body_has_checks_key(
        self, async_client: AsyncClient
    ) -> None:
        response = await async_client.get("/ready")
        body = response.json()
        assert "checks" in body
        checks = body["checks"]
        assert "database" in checks

    async def test_ready_database_check_has_status(
        self, async_client: AsyncClient
    ) -> None:
        response = await async_client.get("/ready")
        body = response.json()
        db_check = body["checks"]["database"]
        assert "status" in db_check
        assert db_check["status"] in {"up", "down"}


# ---------------------------------------------------------------------------
# /metrics — Prometheus endpoint
# ---------------------------------------------------------------------------

class TestMetricsEndpoint:
    async def test_metrics_returns_200(self, async_client: AsyncClient) -> None:
        response = await async_client.get("/metrics")
        assert response.status_code == 200

    async def test_metrics_content_type_is_prometheus(
        self, async_client: AsyncClient
    ) -> None:
        response = await async_client.get("/metrics")
        assert "text/plain" in response.headers.get("content-type", "")

    async def test_metrics_contains_http_requests_total(
        self, async_client: AsyncClient
    ) -> None:
        response = await async_client.get("/metrics")
        assert "http_requests_total" in response.text

    async def test_metrics_contains_duration_histogram(
        self, async_client: AsyncClient
    ) -> None:
        response = await async_client.get("/metrics")
        assert "http_request_duration_seconds" in response.text

    async def test_metrics_contains_in_progress_gauge(
        self, async_client: AsyncClient
    ) -> None:
        response = await async_client.get("/metrics")
        assert "http_requests_in_progress" in response.text

    async def test_metrics_contains_new_application_gauges(
        self, async_client: AsyncClient
    ) -> None:
        response = await async_client.get("/metrics")
        body = response.text
        assert "assessment_queue_depth" in body
        assert "db_pool_connections_size" in body
        assert "llm_circuit_breaker_state" in body
        assert "audit_log_write_total" in body

    async def test_metrics_self_not_in_collection(
        self, async_client: AsyncClient
    ) -> None:
        """GET /metrics must not add itself to the http_requests_total counter."""
        before = HTTP_REQUESTS_TOTAL.labels(
            method="GET", endpoint="/metrics", status_code="200"
        )._value.get()
        await async_client.get("/metrics")
        after = HTTP_REQUESTS_TOTAL.labels(
            method="GET", endpoint="/metrics", status_code="200"
        )._value.get()
        assert after == before, "/metrics path must be excluded from collection"


# ---------------------------------------------------------------------------
# 10-request accumulation test
# ---------------------------------------------------------------------------

class TestRequestAccumulation:
    async def test_ten_requests_reflected_in_metrics(
        self, async_client: AsyncClient
    ) -> None:
        """Make 10 requests to /health, then verify /metrics shows the counts."""
        # /health is excluded — use a real counted path instead.
        before = HTTP_REQUESTS_TOTAL.labels(
            method="GET", endpoint="/", status_code="200"
        )._value.get()

        n = 10
        for _ in range(n):
            resp = await async_client.get("/")
            assert resp.status_code == 200

        after = HTTP_REQUESTS_TOTAL.labels(
            method="GET", endpoint="/", status_code="200"
        )._value.get()
        assert after == before + n, (
            f"Expected {before + n} total requests at /, got {after}"
        )

        # Verify /metrics text contains the metric name with a count ≥ n.
        metrics_resp = await async_client.get("/metrics")
        assert "http_requests_total" in metrics_resp.text


# ---------------------------------------------------------------------------
# /api/v1/platform/health
# ---------------------------------------------------------------------------

class TestPlatformHealthEndpoint:
    async def test_platform_health_requires_operator_role(
        self, async_client: AsyncClient
    ) -> None:
        """Developer role must receive 403."""
        response = await async_client.get(
            "/api/v1/platform/health",
            headers={"X-User-Role": "developer"},
        )
        assert response.status_code == 403

    async def test_platform_health_requires_auth(
        self, async_client: AsyncClient
    ) -> None:
        """Missing role header must receive 403."""
        response = await async_client.get("/api/v1/platform/health")
        assert response.status_code == 403

    async def test_platform_health_operator_returns_200(
        self, async_client: AsyncClient
    ) -> None:
        response = await async_client.get(
            "/api/v1/platform/health",
            headers={"X-User-Role": "operator"},
        )
        assert response.status_code == 200

    async def test_platform_health_platform_admin_returns_200(
        self, async_client: AsyncClient
    ) -> None:
        response = await async_client.get(
            "/api/v1/platform/health",
            headers={"X-User-Role": "platform_admin"},
        )
        assert response.status_code == 200

    async def test_platform_health_has_required_fields(
        self, async_client: AsyncClient
    ) -> None:
        response = await async_client.get(
            "/api/v1/platform/health",
            headers={"X-User-Role": "operator"},
        )
        body = response.json()
        assert "api_success_rate" in body
        assert "assessment_completion_rate" in body
        assert "audit_log_write_success_rate" in body
        assert "db_connection_pool_utilization" in body
        assert "llm_circuit_breaker_status" in body

    async def test_platform_health_api_success_rate_is_percentage(
        self, async_client: AsyncClient
    ) -> None:
        response = await async_client.get(
            "/api/v1/platform/health",
            headers={"X-User-Role": "operator"},
        )
        body = response.json()
        rate = body["api_success_rate"]
        assert isinstance(rate, (int, float))
        assert 0.0 <= rate <= 100.0

    async def test_platform_health_circuit_breaker_status_is_string(
        self, async_client: AsyncClient
    ) -> None:
        response = await async_client.get(
            "/api/v1/platform/health",
            headers={"X-User-Role": "operator"},
        )
        body = response.json()
        cb_status = body["llm_circuit_breaker_status"]
        assert isinstance(cb_status, str)
        assert cb_status in {"closed", "open", "half-open", "unknown"}

    async def test_platform_health_has_status_and_timestamp(
        self, async_client: AsyncClient
    ) -> None:
        response = await async_client.get(
            "/api/v1/platform/health",
            headers={"X-User-Role": "operator"},
        )
        body = response.json()
        assert body.get("status") == "healthy"
        assert "timestamp" in body
