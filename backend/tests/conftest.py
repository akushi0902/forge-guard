"""Shared pytest fixtures for the ForgeGuard test suite.

Fixture groups:

  Application (no database required)
  ─────────────────────────────────────────────────────────────────
  test_settings   — Settings with safe test defaults (no real DB).
  app             — FastAPI application created with test_settings.
  async_client    — httpx.AsyncClient bound to app (legacy alias).
  test_client     — httpx.AsyncClient bound to app (WO-094 name).
  authenticated_client — factory fixture returning a pre-authenticated
                         AsyncClient for a given role.

  Database (requires Docker / testcontainers)
  ─────────────────────────────────────────────────────────────────
  postgres_container — session-scoped PostgreSQL testcontainer.
  db_url             — asyncpg DSN derived from the container.
  apply_migrations   — runs 'alembic upgrade head' once per session.
  db_engine          — session-scoped async SQLAlchemy engine.
  db_session         — function-scoped async session; rolls back after
                       each test for hermetic test isolation.

Configuration:
  pytest-asyncio is configured to ``asyncio_mode = auto`` in pyproject.toml,
  so all ``async def`` test functions run without the ``@pytest.mark.asyncio``
  decorator.
"""

from __future__ import annotations

import contextlib
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import AsyncGenerator, Callable

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from forgeguard.core.config import Settings

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

BACKEND_DIR = Path(__file__).resolve().parent.parent  # .../backend/


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _to_asyncpg_url(url: str) -> str:
    """Convert any postgresql:// variant to the asyncpg driver prefix."""
    for prefix in (
        "postgresql+psycopg2://",
        "postgresql+psycopg://",
        "postgresql://",
        "postgres://",
    ):
        if url.startswith(prefix):
            return "postgresql+asyncpg://" + url[len(prefix):]
    return url


def _make_test_jwt(role: str, settings: Settings) -> str:
    """Create a signed JWT suitable for test authentication headers."""
    import jwt  # PyJWT — already in runtime deps

    now = datetime.now(tz=timezone.utc)
    payload = {
        "sub": str(uuid.uuid4()),
        "role": role,
        "iat": now,
        "exp": now + timedelta(minutes=15),
        "jti": str(uuid.uuid4()),
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


# ---------------------------------------------------------------------------
# Application fixtures (no database required)
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def test_settings() -> Settings:
    """Settings instance with safe test defaults.

    The database URL points to a local test database; it is intentionally a
    placeholder because most unit tests do not hit a real database.  Tests
    that need a live database should use the ``db_session`` fixture instead,
    which derives its URL from the testcontainers ``postgres_container``.
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
    """FastAPI application configured for the test session.

    Patches the module-level settings cache so ``get_settings()`` returns
    ``test_settings`` everywhere — including inside middleware and route
    handlers — for the duration of the session.
    """
    import forgeguard.core.config as config_module  # noqa: PLC0415

    original = config_module._settings_cache
    config_module._settings_cache = test_settings

    from forgeguard.main import create_app  # noqa: PLC0415

    application = create_app()

    config_module._settings_cache = original
    return application


@pytest_asyncio.fixture()
async def async_client(app: FastAPI) -> AsyncGenerator[AsyncClient, None]:
    """Unauthenticated httpx.AsyncClient bound to the test app (legacy name)."""
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        yield client


@pytest_asyncio.fixture()
async def test_client(app: FastAPI) -> AsyncGenerator[AsyncClient, None]:
    """Unauthenticated httpx.AsyncClient bound to the test app.

    Uses ASGITransport so requests bypass the network layer entirely.
    """
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        yield client


@pytest_asyncio.fixture()
async def authenticated_client(
    app: FastAPI,
    test_settings: Settings,
) -> AsyncGenerator[Callable[[str], AsyncClient], None]:
    """Factory fixture that returns an authenticated AsyncClient for a given role.

    Usage in tests::

        async def test_protected(authenticated_client):
            client = await authenticated_client("tech_lead")
            response = await client.get("/api/v1/services")
            assert response.status_code != 401

    All clients created by the factory are closed automatically after the test.
    """
    created: list[AsyncClient] = []

    async def _factory(role: str = "developer") -> AsyncClient:
        token = _make_test_jwt(role, test_settings)
        client = AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://testserver",
            headers={"Authorization": f"Bearer {token}"},
        )
        await client.__aenter__()
        created.append(client)
        return client

    yield _factory

    for c in created:
        with contextlib.suppress(Exception):
            await c.__aexit__(None, None, None)


# ---------------------------------------------------------------------------
# Database fixtures (require Docker / testcontainers)
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def postgres_container():
    """Start a PostgreSQL 16 testcontainer for the entire test session.

    Skips automatically if:
    - testcontainers is not installed (``pip install testcontainers[postgres]``)
    - Docker daemon is not running or unreachable

    The container uses a random host port to avoid conflicts when multiple
    test suites run in parallel in CI.
    """
    try:
        from testcontainers.postgres import PostgresContainer  # noqa: PLC0415
    except ImportError:
        pytest.skip(
            "testcontainers not installed — run: pip install 'testcontainers[postgres]>=4.0'"
        )

    container = PostgresContainer(image="postgres:16-alpine", dbname="forgeguard_test")
    try:
        container.start()
    except Exception as exc:
        pytest.skip(
            f"Could not start PostgreSQL testcontainer. "
            f"Is Docker running?  Error: {exc}"
        )

    yield container

    container.stop()


@pytest.fixture(scope="session")
def db_url(postgres_container) -> str:  # type: ignore[override]
    """Return the asyncpg DSN for the running testcontainer."""
    raw = postgres_container.get_connection_url()
    return _to_asyncpg_url(raw)


@pytest.fixture(scope="session")
def apply_migrations(db_url: str) -> None:
    """Run 'alembic upgrade head' against the testcontainer database.

    Patches ``forgeguard.core.config._settings_cache`` to the testcontainer
    URL so that ``alembic/env.py`` picks up the correct database.  The patch
    is reverted immediately after the migration finishes.

    Raises immediately (fails fast) if Alembic cannot apply migrations — a
    silent partial migration would cause confusing test failures downstream.
    """
    import forgeguard.core.config as _config  # noqa: PLC0415
    from alembic import command  # noqa: PLC0415
    from alembic.config import Config  # noqa: PLC0415

    migration_settings = Settings(
        database_url=db_url,
        jwt_secret_key="test-jwt-secret-for-migrations",
        log_level="WARNING",
        app_env="testing",
        llm_api_key="",
        forge_catalog_url="http://localhost:9999/catalog",
    )

    prev = _config._settings_cache
    _config._settings_cache = migration_settings
    try:
        alembic_cfg = Config(str(BACKEND_DIR / "alembic.ini"))
        # Override script_location to an absolute path so pytest CWD doesn't matter.
        alembic_cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
        command.upgrade(alembic_cfg, "head")
    finally:
        _config._settings_cache = prev


@pytest.fixture(scope="session")
def db_engine(db_url: str, apply_migrations: None):  # type: ignore[override]
    """Session-scoped async SQLAlchemy engine connected to the testcontainer.

    Uses NullPool so each connection is closed immediately after use;
    no idle connections persist between tests.
    """
    engine = create_async_engine(db_url, echo=False, poolclass=NullPool)
    yield engine
    # NullPool: no pool to drain.  Sync dispose closes any remaining handles.
    engine.sync_engine.dispose()


@pytest_asyncio.fixture()
async def db_session(db_engine) -> AsyncGenerator[AsyncSession, None]:
    """Function-scoped async database session with automatic rollback.

    Each test gets a fresh transaction.  The session is rolled back after the
    test completes — successful or not — preventing test pollution without
    requiring explicit teardown in test code.

    The session can be used directly with SQLAlchemy ORM operations::

        async def test_insert(db_session):
            db_session.add(UserFactory.build())
            await db_session.flush()
            result = await db_session.execute(select(User))
            assert result.scalars().first() is not None
    """
    async with db_engine.connect() as conn:
        await conn.begin()
        session = AsyncSession(bind=conn, expire_on_commit=False)
        try:
            yield session
        finally:
            await session.close()
            await conn.rollback()
