"""Alembic environment configuration for ForgeGuard.

This module bridges Alembic with SQLAlchemy's async engine and the application
settings sourced from ``forgeguard.core.config``.  Migration scripts run via
``alembic upgrade head`` or ``alembic current`` will use the DATABASE_URL
defined in the environment (or .env file) automatically.
"""

from __future__ import annotations

import asyncio
import logging
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

# ---------------------------------------------------------------------------
# Alembic Config object, which provides access to values within alembic.ini.
# ---------------------------------------------------------------------------
config = context.config

# Interpret the config file for Python logging.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

logger = logging.getLogger("alembic.env")

# ---------------------------------------------------------------------------
# SQLAlchemy naming conventions
# Applied to the MetaData so that auto-generated constraint names are
# predictable and deterministic across databases.
# ---------------------------------------------------------------------------
NAMING_CONVENTION: dict[str, str] = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

# ---------------------------------------------------------------------------
# MetaData — populated from the ORM model registry.
# ---------------------------------------------------------------------------
try:
    from forgeguard.data.models import Base  # noqa: PLC0415

    target_metadata = Base.metadata
except Exception:
    logger.warning(
        "Could not import Base from forgeguard.data.models; "
        "autogenerate will not detect model changes. "
        "Ensure PYTHONPATH includes src/ and dependencies are installed.",
    )
    target_metadata = None

# ---------------------------------------------------------------------------
# Dynamic DATABASE_URL from application settings
# ---------------------------------------------------------------------------
def _get_database_url() -> str:
    """Read DATABASE_URL from ForgeGuard settings.

    Falls back gracefully if the application settings cannot be imported
    (e.g. during bootstrapping before dependencies are installed).
    """
    try:
        from forgeguard.core.config import get_settings  # noqa: PLC0415

        return get_settings().database_url
    except Exception:
        logger.warning(
            "Could not load ForgeGuard settings; falling back to alembic.ini DATABASE_URL. "
            "Ensure PYTHONPATH includes the src/ directory and dependencies are installed.",
        )
        url = config.get_main_option("sqlalchemy.url")
        if url is None:
            msg = "No DATABASE_URL available from settings or alembic.ini."
            raise RuntimeError(msg)
        return url


# ---------------------------------------------------------------------------
# Offline migration mode
# ---------------------------------------------------------------------------
def run_migrations_offline() -> None:
    """Run migrations without a live database connection.

    Emits the migration SQL to stdout rather than executing it. Useful for
    review-and-apply workflows in CI/CD pipelines.
    """
    url = _get_database_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        naming_convention=NAMING_CONVENTION,
    )

    with context.begin_transaction():
        context.run_migrations()


# ---------------------------------------------------------------------------
# Online migration mode (async)
# ---------------------------------------------------------------------------
def do_run_migrations(connection: Connection) -> None:
    """Execute migrations within the provided synchronous connection context."""
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        naming_convention=NAMING_CONVENTION,
        compare_type=True,
        transaction_per_migration=True,
    )

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Create an async engine and run migrations against it.

    The engine is disposed immediately after the migration completes so that
    connection pool resources are not leaked.
    """
    url = _get_database_url()

    configuration = config.get_section(config.config_ini_section) or {}
    configuration["sqlalchemy.url"] = url

    connectable = async_engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """Entry point for online (connected) migrations."""
    asyncio.run(run_async_migrations())


# ---------------------------------------------------------------------------
# Main dispatch
# ---------------------------------------------------------------------------
if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
