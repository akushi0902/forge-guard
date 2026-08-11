"""Application configuration via Pydantic BaseSettings.

All settings are loaded from environment variables. Sensible defaults are
provided for local development. Production deployments must supply overrides
via environment variables or a .env file.

Environment variables (case-insensitive):
    DATABASE_URL       — PostgreSQL DSN (async driver)
    JWT_SECRET_KEY     — Secret key for signing JWT tokens
    LOG_LEVEL          — Python log level string (default: INFO)
    LLM_API_KEY        — API key for the LLM provider
    FORGE_CATALOG_URL  — Base URL of the Forge Catalog API
    APP_VERSION        — Application version string (default: 0.1.0)
"""

from __future__ import annotations

import logging

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    """Centralised runtime configuration for ForgeGuard.

    Pydantic will raise a ``ValidationError`` at startup if any required field
    is missing or has an incompatible type. The error message will identify the
    offending variable and expected type, giving operators an actionable signal.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ------------------------------------------------------------------ #
    # Database
    # ------------------------------------------------------------------ #
    database_url: str = Field(
        default="postgresql+asyncpg://postgres:postgres@localhost:5432/forgeguard_dev",
        description="Async PostgreSQL DSN (must use asyncpg driver prefix).",
    )

    # ------------------------------------------------------------------ #
    # Security
    # ------------------------------------------------------------------ #
    jwt_secret_key: str = Field(
        default="change-me-in-production-this-is-not-secure",
        description="HMAC secret used to sign JWT access tokens. Must be overridden in production.",
    )
    jwt_algorithm: str = Field(default="HS256", description="JWT signing algorithm.")
    access_token_expire_minutes: int = Field(
        default=15,
        description="Access token TTL in minutes.",
    )
    refresh_token_expire_days: int = Field(
        default=7,
        description="Refresh token TTL in days.",
    )

    # ------------------------------------------------------------------ #
    # LLM / AI
    # ------------------------------------------------------------------ #
    llm_api_key: str = Field(
        default="",
        description="API key for the configured LLM provider. Leave empty to disable AI features.",
    )

    # ------------------------------------------------------------------ #
    # Forge Platform Integration
    # ------------------------------------------------------------------ #
    forge_catalog_url: str = Field(
        default="https://forge.example.com/catalog",
        description="Base URL of the Forge Catalog API.",
    )

    # ------------------------------------------------------------------ #
    # Rate Limiting
    # ------------------------------------------------------------------ #
    rate_limit_general: int = Field(
        default=100,
        description="Max requests per window for general (non-auth) endpoints.",
    )
    rate_limit_auth: int = Field(
        default=10,
        description="Max requests per window for authentication endpoints.",
    )
    rate_limit_window_seconds: int = Field(
        default=60,
        description="Token bucket refill window in seconds.",
    )
    rate_limit_auth_paths: list[str] = Field(
        default=["/api/v1/auth/"],
        description=(
            "Path prefixes that trigger the stricter auth rate limit tier. "
            "Set via env as a JSON array: RATE_LIMIT_AUTH_PATHS='[\"/api/v1/auth/\"]'"
        ),
    )

    # ------------------------------------------------------------------ #
    # Observability
    # ------------------------------------------------------------------ #
    log_level: str = Field(
        default="INFO",
        description="Python logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL).",
    )

    # ------------------------------------------------------------------ #
    # Application metadata
    # ------------------------------------------------------------------ #
    app_version: str = Field(default="0.1.0", description="Application version string.")
    app_env: str = Field(
        default="development",
        description="Deployment environment (development, staging, production).",
    )

    # ------------------------------------------------------------------ #
    # Validators
    # ------------------------------------------------------------------ #
    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, value: str) -> str:
        """Ensure log_level is a recognised Python logging level."""
        normalised = value.upper()
        valid_levels = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        if normalised not in valid_levels:
            msg = f"LOG_LEVEL must be one of {valid_levels}, got {value!r}"
            raise ValueError(msg)
        return normalised

    @field_validator("database_url")
    @classmethod
    def validate_database_url(cls, value: str) -> str:
        """Ensure the database URL uses the asyncpg driver."""
        if not value.startswith("postgresql+asyncpg://"):
            # Allow plain postgresql:// at dev time but emit a warning.
            if value.startswith("postgresql://"):
                logger.warning(
                    "DATABASE_URL uses synchronous driver prefix 'postgresql://'. "
                    "ForgeGuard requires 'postgresql+asyncpg://'. Rewriting automatically.",
                )
                return value.replace("postgresql://", "postgresql+asyncpg://", 1)
            msg = (
                "DATABASE_URL must be a PostgreSQL DSN starting with "
                "'postgresql+asyncpg://' or 'postgresql://'. Got: %r"
            )
            raise ValueError(msg % value)
        return value


def get_settings() -> Settings:
    """Return a cached :class:`Settings` instance.

    The instance is created on first call and reused for all subsequent calls
    within the same process, so environment reads happen once at startup.
    """
    return _settings_cache


# Module-level singleton — created once when the module is first imported.
_settings_cache: Settings = Settings()
