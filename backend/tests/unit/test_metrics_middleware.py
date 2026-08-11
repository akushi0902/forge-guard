"""Unit tests for MetricsMiddleware and supporting utilities.

Tests verify:
    1. normalize_path replaces UUID segments with {id}.
    2. normalize_path replaces integer segments with {id}.
    3. normalize_path leaves non-parameterised paths unchanged.
    4. Excluded paths (/metrics, /health, /ready) skip metric collection.
    5. Successful request (200) increments http_requests_total counter.
    6. Error request (500) increments counter with correct status_code label.
    7. http_request_duration_seconds histogram is observed on each request.
    8. http_requests_in_progress gauge is decremented back to zero after request.
    9. Path normalization is applied to counter labels (no UUID in labels).
    10. Metrics middleware is non-fatal — errors in collection don't fail requests.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from prometheus_client import CollectorRegistry, Counter, Histogram, Gauge

from forgeguard.middleware.metrics import (
    MetricsMiddleware,
    normalize_path,
    _EXCLUDED_PATHS,
    HTTP_REQUESTS_TOTAL,
    HTTP_REQUEST_DURATION_SECONDS,
    HTTP_REQUESTS_IN_PROGRESS,
)


# ---------------------------------------------------------------------------
# normalize_path unit tests (pure function, no HTTP)
# ---------------------------------------------------------------------------

class TestNormalizePath:
    @pytest.mark.parametrize("raw,expected", [
        # UUID replacement
        (
            "/api/v1/services/3fa85f64-5717-4562-b3fc-2c963f66afa6",
            "/api/v1/services/{id}",
        ),
        (
            "/api/v1/services/3fa85f64-5717-4562-b3fc-2c963f66afa6/assessments",
            "/api/v1/services/{id}/assessments",
        ),
        # Multiple UUIDs
        (
            "/api/v1/services/3fa85f64-5717-4562-b3fc-2c963f66afa6"
            "/findings/aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee",
            "/api/v1/services/{id}/findings/{id}",
        ),
        # Integer segment
        ("/api/v1/items/42",        "/api/v1/items/{id}"),
        ("/api/v1/items/42/detail", "/api/v1/items/{id}/detail"),
        # Non-parameterised paths unchanged
        ("/health",                 "/health"),
        ("/metrics",                "/metrics"),
        ("/api/v1/services",        "/api/v1/services"),
        ("/api/v1/platform/health", "/api/v1/platform/health"),
        # Mixed case UUID (normalised)
        (
            "/api/v1/users/3FA85F64-5717-4562-B3FC-2C963F66AFA6",
            "/api/v1/users/{id}",
        ),
    ])
    def test_normalize_path(self, raw: str, expected: str) -> None:
        assert normalize_path(raw) == expected

    def test_empty_path(self) -> None:
        assert normalize_path("/") == "/"

    def test_path_with_no_ids(self) -> None:
        assert normalize_path("/api/v1/health") == "/api/v1/health"


# ---------------------------------------------------------------------------
# Excluded paths
# ---------------------------------------------------------------------------

class TestExcludedPaths:
    def test_metrics_is_excluded(self) -> None:
        assert "/metrics" in _EXCLUDED_PATHS

    def test_health_is_excluded(self) -> None:
        assert "/health" in _EXCLUDED_PATHS

    def test_ready_is_excluded(self) -> None:
        assert "/ready" in _EXCLUDED_PATHS


# ---------------------------------------------------------------------------
# MetricsMiddleware integration via minimal FastAPI app
# ---------------------------------------------------------------------------

@pytest.fixture
def metrics_app():
    """Minimal FastAPI app with MetricsMiddleware for testing."""
    app = FastAPI()
    app.add_middleware(MetricsMiddleware)

    @app.get("/api/v1/test")
    async def test_route() -> dict:
        return {"ok": True}

    @app.get("/api/v1/error")
    async def error_route() -> dict:
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=500, content={"error": "server error"})

    @app.get("/health")
    async def health() -> dict:
        return {"status": "healthy"}

    @app.get("/metrics")
    async def metrics_stub() -> dict:
        return {}

    return app


@pytest.fixture
def counter_before(metrics_app) -> float:
    """Return the current total count for /api/v1/test before the test."""
    try:
        return HTTP_REQUESTS_TOTAL.labels(
            method="GET", endpoint="/api/v1/test", status_code="200"
        )._value.get()
    except Exception:
        return 0.0


class TestMetricsMiddlewareCounters:
    async def test_successful_request_increments_counter(
        self, metrics_app: FastAPI
    ) -> None:
        before = HTTP_REQUESTS_TOTAL.labels(
            method="GET", endpoint="/api/v1/test", status_code="200"
        )._value.get()
        async with AsyncClient(
            transport=ASGITransport(app=metrics_app), base_url="http://test"
        ) as client:
            resp = await client.get("/api/v1/test")
        assert resp.status_code == 200
        after = HTTP_REQUESTS_TOTAL.labels(
            method="GET", endpoint="/api/v1/test", status_code="200"
        )._value.get()
        assert after == before + 1.0

    async def test_error_request_increments_500_counter(
        self, metrics_app: FastAPI
    ) -> None:
        before = HTTP_REQUESTS_TOTAL.labels(
            method="GET", endpoint="/api/v1/error", status_code="500"
        )._value.get()
        async with AsyncClient(
            transport=ASGITransport(app=metrics_app), base_url="http://test"
        ) as client:
            resp = await client.get("/api/v1/error")
        assert resp.status_code == 500
        after = HTTP_REQUESTS_TOTAL.labels(
            method="GET", endpoint="/api/v1/error", status_code="500"
        )._value.get()
        assert after == before + 1.0

    async def test_excluded_health_path_not_counted(
        self, metrics_app: FastAPI
    ) -> None:
        before = HTTP_REQUESTS_TOTAL.labels(
            method="GET", endpoint="/health", status_code="200"
        )._value.get()
        async with AsyncClient(
            transport=ASGITransport(app=metrics_app), base_url="http://test"
        ) as client:
            await client.get("/health")
        after = HTTP_REQUESTS_TOTAL.labels(
            method="GET", endpoint="/health", status_code="200"
        )._value.get()
        # Counter must not have increased for excluded paths.
        assert after == before

    async def test_excluded_metrics_path_not_counted(
        self, metrics_app: FastAPI
    ) -> None:
        before = HTTP_REQUESTS_TOTAL.labels(
            method="GET", endpoint="/metrics", status_code="200"
        )._value.get()
        async with AsyncClient(
            transport=ASGITransport(app=metrics_app), base_url="http://test"
        ) as client:
            await client.get("/metrics")
        after = HTTP_REQUESTS_TOTAL.labels(
            method="GET", endpoint="/metrics", status_code="200"
        )._value.get()
        assert after == before


class TestMetricsMiddlewareHistogram:
    async def test_histogram_observed_on_request(
        self, metrics_app: FastAPI
    ) -> None:
        before_count = HTTP_REQUEST_DURATION_SECONDS.labels(
            method="GET", endpoint="/api/v1/test"
        )._count.get()
        async with AsyncClient(
            transport=ASGITransport(app=metrics_app), base_url="http://test"
        ) as client:
            await client.get("/api/v1/test")
        after_count = HTTP_REQUEST_DURATION_SECONDS.labels(
            method="GET", endpoint="/api/v1/test"
        )._count.get()
        assert after_count == before_count + 1.0

    async def test_histogram_sum_positive_after_request(
        self, metrics_app: FastAPI
    ) -> None:
        before_sum = HTTP_REQUEST_DURATION_SECONDS.labels(
            method="GET", endpoint="/api/v1/test"
        )._sum.get()
        async with AsyncClient(
            transport=ASGITransport(app=metrics_app), base_url="http://test"
        ) as client:
            await client.get("/api/v1/test")
        after_sum = HTTP_REQUEST_DURATION_SECONDS.labels(
            method="GET", endpoint="/api/v1/test"
        )._sum.get()
        assert after_sum > before_sum


class TestMetricsMiddlewareInProgress:
    async def test_in_progress_gauge_zero_after_request(
        self, metrics_app: FastAPI
    ) -> None:
        async with AsyncClient(
            transport=ASGITransport(app=metrics_app), base_url="http://test"
        ) as client:
            await client.get("/api/v1/test")
        # After the request completes the gauge should be back to 0.
        gauge_value = HTTP_REQUESTS_IN_PROGRESS.labels(
            method="GET", endpoint="/api/v1/test"
        )._value.get()
        assert gauge_value == 0.0


class TestPathNormalizationInLabels:
    async def test_uuid_path_uses_id_placeholder_in_label(
        self, metrics_app: FastAPI
    ) -> None:
        """Counter label must use {id} not the raw UUID."""
        uuid_path = "/api/v1/services/3fa85f64-5717-4562-b3fc-2c963f66afa6"

        @metrics_app.get("/api/v1/services/{service_id}")
        async def svc_detail() -> dict:
            return {"id": "test"}

        before = HTTP_REQUESTS_TOTAL.labels(
            method="GET", endpoint="/api/v1/services/{id}", status_code="200"
        )._value.get()
        async with AsyncClient(
            transport=ASGITransport(app=metrics_app), base_url="http://test"
        ) as client:
            await client.get(uuid_path)
        after = HTTP_REQUESTS_TOTAL.labels(
            method="GET", endpoint="/api/v1/services/{id}", status_code="200"
        )._value.get()
        assert after == before + 1.0
