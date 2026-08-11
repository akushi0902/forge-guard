"""Shared pytest fixtures for the ForgeGuard test suite.

Fixtures:
    test_settings   — Settings instance with safe test defaults (test DB URL,
                      dummy JWT secret, DEBUG log level).
    app             — FastAPI application instance created with test_settings.
    async_client    — httpx.AsyncClient bound to the test app, usable with
                      ``async for`` or ``await`` in async tests.

Configuration:
    pytest-asyncio is configured to ``asyncio_mode = auto`` in pyproject.toml,
    so all ``async def`` test functions run automatically without the
    ``@pytest.mark.asyncio`` decorator.
"""

from __future__ import annotations

from typing import AsyncGenerator

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from forgeguard.core.config import Settings


@pytest.fixture(scope="session")
def test_settings() -> Settings:
    """Return a Settings instance suitable for tests.

    Overrides:
        - ``database_url``: points to a dedicated test database so tests
          never touch the development or production database.
        - ``jwt_secret_key``: a fixed, short secret — safe for test
          environments only.
        - ``log_level``: DEBUG to maximise visibility during test runs.
        - ``app_env``: "testing" so the application knows not to use
          production-only features.
    """
    return Settings(
        database_url="postgresql+asyncpg://postgres:postgres@localhost:5432/forgeguard_test",
        jwt_secret_key="test-jwt-secret-key-not-for-production",
        log_level="DEBUG",
        app_env="testing",
        llm_api_key="",
        forge_catalog_url="http://localhost:9999/catalog",
    )


@pytest.fixture(scope="session")
def app(test_settings: Settings) -> FastAPI:
    """Create a FastAPI application instance configured for testing.

    The ``forgeguard.core.config._settings_cache`` is replaced with
    ``test_settings`` for the duration of the test session so that
    ``get_settings()`` returns the test configuration everywhere — including
    inside middleware and route handlers.
    """
    import forgeguard.core.config as config_module  # noqa: PLC0415

    # Patch the module-level cache so the factory picks up test settings.
    original = config_module._settings_cache
    config_module._settings_cache = test_settings

    from forgeguard.main import create_app  # noqa: PLC0415

    application = create_app()

    # Restore original cache after the session to avoid cross-session pollution.
    config_module._settings_cache = original
    return application


@pytest_asyncio.fixture()
async def async_client(app: FastAPI) -> AsyncGenerator[AsyncClient, None]:
    """Yield an httpx.AsyncClient configured to talk directly to the test app.

    The client bypasses the network layer entirely — requests are dispatched
    directly to the ASGI app via ``httpx.ASGITransport``, making tests fast
    and hermetic.
    """
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        yield client
