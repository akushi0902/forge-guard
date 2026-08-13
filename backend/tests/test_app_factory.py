"""Tests for the ForgeGuard application factory.

Validates that:
    1. ``create_app()`` returns a properly configured FastAPI instance.
    2. The root health endpoint responds with HTTP 200.
    3. The FastAPI instance carries the expected metadata (title, version,
       API docs URL) confirming the factory configuration is applied.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from httpx import AsyncClient


class TestCreateApp:
    """Unit tests for the create_app() factory function."""

    def test_returns_fastapi_instance(self, app: FastAPI) -> None:
        """create_app() must return a FastAPI instance."""
        assert isinstance(app, FastAPI), (
            f"Expected FastAPI instance, got {type(app).__name__!r}"
        )

    def test_app_title(self, app: FastAPI) -> None:
        """The app title must be 'ForgeGuard'."""
        assert app.title == "ForgeGuard"

    def test_app_version_set(self, app: FastAPI) -> None:
        """The app version must be a non-empty string."""
        assert isinstance(app.version, str)
        assert len(app.version) > 0

    def test_openapi_url_uses_api_prefix(self, app: FastAPI) -> None:
        """The OpenAPI schema URL must be under /api/v1/."""
        assert app.openapi_url is not None
        assert app.openapi_url.startswith("/api/v1/"), (
            f"Expected OpenAPI URL under /api/v1/, got {app.openapi_url!r}"
        )

    def test_docs_url_uses_api_prefix(self, app: FastAPI) -> None:
        """The Swagger UI URL must be under /api/v1/."""
        assert app.docs_url is not None
        assert app.docs_url.startswith("/api/v1/"), (
            f"Expected docs URL under /api/v1/, got {app.docs_url!r}"
        )


class TestRootHealthEndpoint:
    """Integration tests for the root health endpoint."""

    @pytest.mark.asyncio
    async def test_root_returns_200(self, async_client: AsyncClient) -> None:
        """GET / must return HTTP 200."""
        response = await async_client.get("/")
        assert response.status_code == 200, (
            f"Expected 200, got {response.status_code}. Body: {response.text}"
        )

    @pytest.mark.asyncio
    async def test_root_returns_json(self, async_client: AsyncClient) -> None:
        """GET / must return a JSON body."""
        response = await async_client.get("/")
        assert response.headers["content-type"].startswith("application/json"), (
            f"Expected JSON content-type, got {response.headers['content-type']!r}"
        )

    @pytest.mark.asyncio
    async def test_root_body_contains_status_ok(self, async_client: AsyncClient) -> None:
        """GET / response body must contain status='ok'."""
        response = await async_client.get("/")
        body = response.json()
        assert body.get("status") == "ok", f"Expected status='ok', got body: {body}"

    @pytest.mark.asyncio
    async def test_root_body_contains_service_name(self, async_client: AsyncClient) -> None:
        """GET / response body must identify the service."""
        response = await async_client.get("/")
        body = response.json()
        assert body.get("service") == "forgeguard", (
            f"Expected service='forgeguard', got body: {body}"
        )

    @pytest.mark.asyncio
    async def test_root_body_contains_version(self, async_client: AsyncClient) -> None:
        """GET / response body must include a version string."""
        response = await async_client.get("/")
        body = response.json()
        assert "version" in body, f"'version' key missing from body: {body}"
        assert isinstance(body["version"], str) and len(body["version"]) > 0
