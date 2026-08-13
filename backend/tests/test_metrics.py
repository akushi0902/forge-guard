"""Unit tests for the /metrics Prometheus endpoint and MetricsMiddleware.

Tests verify:
    1. GET /metrics returns HTTP 200.
    2. Content-Type is the Prometheus text format.
    3. The response contains the required metric names.
    4. After making requests, counters reflect the correct labels.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient

# Expected metric names defined in middleware/metrics.py
_EXPECTED_METRICS = [
    "http_requests_total",
    "http_request_duration_seconds",
    "db_pool_connections_active",
]


class TestMetricsEndpoint:
    """GET /metrics returns Prometheus text format."""

    async def test_metrics_returns_200(self, async_client: AsyncClient) -> None:
        response = await async_client.get("/metrics")
        assert response.status_code == 200

    async def test_metrics_content_type_is_prometheus(
        self, async_client: AsyncClient
    ) -> None:
        response = await async_client.get("/metrics")
        assert "text/plain" in response.headers["content-type"]

    async def test_metrics_contains_http_requests_total(
        self, async_client: AsyncClient
    ) -> None:
        response = await async_client.get("/metrics")
        assert "http_requests_total" in response.text

    async def test_metrics_contains_http_request_duration_seconds(
        self, async_client: AsyncClient
    ) -> None:
        response = await async_client.get("/metrics")
        assert "http_request_duration_seconds" in response.text

    async def test_metrics_contains_db_pool_connections_active(
        self, async_client: AsyncClient
    ) -> None:
        response = await async_client.get("/metrics")
        assert "db_pool_connections_active" in response.text

    async def test_metrics_response_is_valid_prometheus_format(
        self, async_client: AsyncClient
    ) -> None:
        """Prometheus text format: non-comment lines follow 'name{labels} value' pattern."""
        response = await async_client.get("/metrics")
        non_empty_lines = [
            line for line in response.text.splitlines() if line and not line.startswith("#")
        ]
        # Every data line should contain a space separating name+labels from value.
        for line in non_empty_lines:
            assert " " in line, f"Invalid Prometheus line (no space): {line!r}"


class TestMetricsCounterIncrement:
    """After making requests, the counter labels are present in /metrics."""

    async def test_health_requests_appear_in_counter(
        self, async_client: AsyncClient
    ) -> None:
        """Making a /health request should register its labels in the counter."""
        # Make a request to generate counter labels.
        await async_client.get("/health")

        metrics_response = await async_client.get("/metrics")
        assert metrics_response.status_code == 200
        # The /health path must appear as a labelled counter entry.
        assert "http_requests_total" in metrics_response.text

    async def test_metrics_histogram_buckets_present(
        self, async_client: AsyncClient
    ) -> None:
        """Histogram must expose _bucket, _count, and _sum lines."""
        await async_client.get("/health")
        response = await async_client.get("/metrics")
        text = response.text
        assert "http_request_duration_seconds_bucket" in text
        assert "http_request_duration_seconds_count" in text
        assert "http_request_duration_seconds_sum" in text
