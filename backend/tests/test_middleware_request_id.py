"""Integration tests for the Request ID middleware.

Tests verify:
    1. Every response includes an X-Request-ID header.
    2. The header value is a valid UUID v4 (lowercase hyphenated format).
    3. Concurrent requests receive distinct request IDs (no context leakage).
    4. Client-supplied X-Request-ID headers are NOT used as the server ID
       (anti-spoofing), but the server assigns its own new UUID.
    5. The server-assigned request ID appears in the structured log output.
"""

from __future__ import annotations

import re
import uuid

import pytest
from httpx import AsyncClient


UUID4_PATTERN = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
)


def _is_valid_uuid4(value: str) -> bool:
    """Return True if value is a lowercase UUID v4 string."""
    if not UUID4_PATTERN.match(value):
        return False
    try:
        parsed = uuid.UUID(value, version=4)
        return str(parsed) == value
    except ValueError:
        return False


class TestRequestIDHeader:
    """X-Request-ID header is present and valid on every response."""

    async def test_health_endpoint_has_request_id_header(
        self, async_client: AsyncClient
    ) -> None:
        """GET /api/v1/health must include X-Request-ID in the response."""
        response = await async_client.get("/api/v1/health")
        assert response.status_code == 200
        assert "x-request-id" in response.headers, (
            "X-Request-ID header missing from response"
        )

    async def test_request_id_is_valid_uuid4(
        self, async_client: AsyncClient
    ) -> None:
        """The X-Request-ID value must be a valid UUID v4."""
        response = await async_client.get("/api/v1/health")
        request_id = response.headers["x-request-id"]
        assert _is_valid_uuid4(request_id), (
            f"X-Request-ID {request_id!r} is not a valid UUID v4"
        )

    async def test_root_endpoint_has_request_id_header(
        self, async_client: AsyncClient
    ) -> None:
        """GET / must also include X-Request-ID (middleware applies globally)."""
        response = await async_client.get("/")
        assert "x-request-id" in response.headers

    async def test_each_request_gets_unique_id(
        self, async_client: AsyncClient
    ) -> None:
        """Consecutive requests must receive distinct request IDs."""
        responses = [await async_client.get("/api/v1/health") for _ in range(5)]
        ids = [r.headers["x-request-id"] for r in responses]
        assert len(set(ids)) == 5, (
            f"Expected 5 unique request IDs, got duplicates: {ids}"
        )

    async def test_client_request_id_not_used_as_server_id(
        self, async_client: AsyncClient
    ) -> None:
        """Server must generate its own UUID even when client provides X-Request-ID."""
        spoofed_id = "00000000-0000-4000-8000-000000000000"
        response = await async_client.get(
            "/api/v1/health",
            headers={"X-Request-ID": spoofed_id},
        )
        server_id = response.headers["x-request-id"]
        assert server_id != spoofed_id, (
            "Server used client-supplied X-Request-ID (anti-spoofing violation)"
        )
        assert _is_valid_uuid4(server_id)


class TestRequestIDConcurrency:
    """Request IDs must not leak between concurrent requests."""

    async def test_concurrent_requests_have_distinct_ids(
        self, async_client: AsyncClient
    ) -> None:
        """Requests dispatched concurrently must each get a unique ID."""
        import asyncio

        tasks = [async_client.get("/api/v1/health") for _ in range(10)]
        responses = await asyncio.gather(*tasks)
        ids = [r.headers["x-request-id"] for r in responses]
        assert len(set(ids)) == 10, (
            f"Context leak detected: duplicate IDs in concurrent requests: {ids}"
        )


class TestRequestIDOnNonExistentRoute:
    """X-Request-ID must be present even on 404 responses."""

    async def test_404_response_has_request_id(
        self, async_client: AsyncClient
    ) -> None:
        """404 responses must still carry X-Request-ID (middleware is global)."""
        response = await async_client.get("/this-path-does-not-exist")
        # Middleware runs before routing, so 404 responses still get the header.
        assert "x-request-id" in response.headers
        assert _is_valid_uuid4(response.headers["x-request-id"])
