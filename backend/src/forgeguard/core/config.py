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
    field_encryption_key: str = Field(
        default="",
        description=(
            "Base64url-encoded 32-byte key for AES-256-GCM field-level PII encryption. "
            "Generate with: python -c \"import os,base64; print(base64.urlsafe_b64encode(os.urandom(32)).decode())\". "
            "Required when field-level encryption features are used; leave empty to disable. "
            "Must decode to exactly 32 bytes."
        ),
    )
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
    llm_base_url: str = Field(
        default="https://api.openai.com/v1",
        description="Base URL for the LLM provider API (OpenAI-compatible endpoint).",
    )
    llm_model: str = Field(
        default="gpt-4o-mini",
        description="LLM model identifier to use for completions.",
    )
    llm_timeout_seconds: int = Field(
        default=30,
        description="HTTP timeout in seconds for LLM provider requests.",
    )
    llm_temperature: float = Field(
        default=0.7,
        description="Sampling temperature for LLM completions (0.0–2.0).",
    )
    llm_max_tokens: int = Field(
        default=2048,
        description="Maximum number of tokens to generate per LLM completion.",
    )

    # ------------------------------------------------------------------ #
    # Circuit Breaker
    # ------------------------------------------------------------------ #
    circuit_breaker_failure_threshold: int = Field(
        default=5,
        description="Number of failures in the window that opens the circuit breaker.",
    )
    circuit_breaker_window_seconds: int = Field(
        default=60,
        description="Rolling window (seconds) in which failures are counted.",
    )
    circuit_breaker_recovery_seconds: int = Field(
        default=30,
        description="Seconds to wait in OPEN state before transitioning to HALF_OPEN.",
    )

    # ------------------------------------------------------------------ #
    # AI Template Fallback
    # ------------------------------------------------------------------ #
    template_default_confidence: float = Field(
        default=0.7,
        description=(
            "Default confidence score (0.0–1.0) assigned to template-generated AI responses. "
            "Set via TEMPLATE_DEFAULT_CONFIDENCE env var. Generic fallback templates always "
            "use 0.5 regardless of this setting."
        ),
    )

    # ------------------------------------------------------------------ #
    # AI Response Cache
    # ------------------------------------------------------------------ #
    ai_cache_ttl_seconds: int = Field(
        default=3600,
        description="TTL in seconds for cached LLM responses (default: 1 hour).",
    )
    ai_cache_max_size: int = Field(
        default=1000,
        description="Maximum number of LLM responses to hold in the in-memory cache.",
    )

    # ------------------------------------------------------------------ #
    # Forge Platform Integration
    # ------------------------------------------------------------------ #
    forge_catalog_url: str = Field(
        default="https://forge.example.com/catalog",
        description="Base URL of the Forge Catalog API.",
    )

    # ------------------------------------------------------------------ #
    # CORS
    # ------------------------------------------------------------------ #
    cors_allowed_origins: str = Field(
        default="http://localhost:3000",
        description=(
            "Comma-separated list of allowed CORS origins. "
            "Must NOT contain '*' — wildcard is incompatible with allow_credentials=True. "
            "Example: 'https://app.example.com,https://staging.example.com'"
        ),
    )
    cors_allow_methods: list[str] = Field(
        default=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        description="Allowed HTTP methods for CORS pre-flight and simple requests.",
    )
    cors_allow_headers: list[str] = Field(
        default=["Content-Type", "Authorization", "X-Request-ID"],
        description="Allowed request headers for CORS.",
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
    @field_validator("cors_allowed_origins")
    @classmethod
    def validate_cors_origins(cls, value: str) -> str:
        """Prevent the wildcard+credentials misconfiguration at startup."""
        origins = [o.strip() for o in value.split(",") if o.strip()]
        if not origins:
            logger.warning(
                "CORS_ALLOWED_ORIGINS is empty; defaulting to http://localhost:3000"
            )
            return "http://localhost:3000"
        if "*" in origins:
            raise ValueError(
                "CORS_ALLOWED_ORIGINS must not contain '*' when allow_credentials=True. "
                "Specify explicit origins such as 'https://app.example.com'. "
                "Wildcard origins are a common misconfiguration that exposes the API "
                "to cross-origin credential theft."
            )
        # Normalise: strip trailing slashes and whitespace.
        return ",".join(o.strip().rstrip("/") for o in origins)

    @property
    def cors_origins_list(self) -> list[str]:
        """Return CORS allowed origins as a parsed list."""
        return [o.strip() for o in self.cors_allowed_origins.split(",") if o.strip()]

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
