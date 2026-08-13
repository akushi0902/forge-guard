"""FastAPI dependency providers for service-layer modules.

Each ``Depends()`` provider in this module is the canonical injection point
for its corresponding service.  Route handlers must obtain service instances
exclusively through these providers — direct instantiation in route handlers
is prohibited to ensure testability and consistent lifecycle management.

Usage::

    from fastapi import Depends
    from forgeguard.core.dependencies import get_settings, get_ai_engine

    @router.post("/analyse")
    async def analyse(
        body: AnalyseRequest,
        ai: AIEngineService = Depends(get_ai_engine),
    ) -> dict:
        response = await ai.generate_completion(body.prompt)
        return {"content": response.content}
"""

from __future__ import annotations

from typing import Annotated

import asyncpg
from fastapi import Depends

from forgeguard.core.config import Settings, get_settings

# Re-export the settings dependency under a convenient alias.
SettingsDep = Annotated[Settings, Depends(get_settings)]


# ------------------------------------------------------------------
# AI Engine singleton
# ------------------------------------------------------------------

# Module-level singleton — created once on first call, reused thereafter.
_ai_engine_instance = None


def get_ai_engine():
    """Return the singleton :class:`~forgeguard.services.ai_engine.AIEngineService`.

    Reads all configuration from the cached ``Settings`` instance so no
    environment variable reads happen after the first call.  The singleton
    pattern avoids recreating the circuit breaker (which would reset its
    state) and the cache on every request.

    Returns:
        A fully configured :class:`~forgeguard.services.ai_engine.AIEngineService`.
    """
    global _ai_engine_instance
    if _ai_engine_instance is None:
        from forgeguard.services.ai_engine import AIEngineService, CircuitBreaker, ResponseCache
        from forgeguard.services.ai_engine.providers.openai_provider import OpenAIProvider

        settings = get_settings()
        provider = OpenAIProvider(
            base_url=settings.llm_base_url,
            api_key=settings.llm_api_key,
            model=settings.llm_model,
            temperature=settings.llm_temperature,
            max_tokens=settings.llm_max_tokens,
            timeout_seconds=settings.llm_timeout_seconds,
        )
        circuit_breaker = CircuitBreaker(
            failure_threshold=settings.circuit_breaker_failure_threshold,
            window_seconds=settings.circuit_breaker_window_seconds,
            recovery_timeout=settings.circuit_breaker_recovery_seconds,
        )
        cache = ResponseCache(
            max_size=settings.ai_cache_max_size,
            ttl_seconds=settings.ai_cache_ttl_seconds,
        )
        _ai_engine_instance = AIEngineService(provider, circuit_breaker, cache)
    return _ai_engine_instance


# ------------------------------------------------------------------
# Connection pool
# ------------------------------------------------------------------


async def get_pool() -> asyncpg.Pool:
    """Return the application-level asyncpg connection pool.

    The pool is initialised by the FastAPI lifespan handler; this provider
    simply surfaces it for injection via Depends().
    """
    from forgeguard.data.database import get_pool as _get_pool  # noqa: PLC0415

    return await _get_pool()


# ------------------------------------------------------------------
# Repository factories
# ------------------------------------------------------------------


async def get_user_repository(
    pool: asyncpg.Pool = Depends(get_pool),
):
    from forgeguard.data.repositories.users import UserRepository  # noqa: PLC0415

    return UserRepository(pool)


async def get_service_repository(
    pool: asyncpg.Pool = Depends(get_pool),
):
    from forgeguard.data.repositories.services import ServiceRepository  # noqa: PLC0415

    return ServiceRepository(pool)


async def get_policy_repository(
    pool: asyncpg.Pool = Depends(get_pool),
):
    from forgeguard.data.repositories.policies import PolicyRepository  # noqa: PLC0415

    return PolicyRepository(pool)


async def get_finding_repository(
    pool: asyncpg.Pool = Depends(get_pool),
):
    from forgeguard.data.repositories.findings import FindingRepository  # noqa: PLC0415

    return FindingRepository(pool)


async def get_score_repository(
    pool: asyncpg.Pool = Depends(get_pool),
):
    from forgeguard.data.repositories.scores import ScoreRepository  # noqa: PLC0415

    return ScoreRepository(pool)


async def get_decision_repository(
    pool: asyncpg.Pool = Depends(get_pool),
):
    from forgeguard.data.repositories.decisions import DecisionRepository  # noqa: PLC0415

    return DecisionRepository(pool)


async def get_audit_log_repository(
    pool: asyncpg.Pool = Depends(get_pool),
):
    from forgeguard.data.repositories.audit_logs import AuditLogRepository  # noqa: PLC0415

    return AuditLogRepository(pool)


async def get_refresh_token_repository(
    pool: asyncpg.Pool = Depends(get_pool),
):
    from forgeguard.data.repositories.refresh_tokens import RefreshTokenRepository  # noqa: PLC0415

    return RefreshTokenRepository(pool)


async def get_demo_transaction_repository(
    pool: asyncpg.Pool = Depends(get_pool),
):
    from forgeguard.data.repositories.demo_repository import DemoTransactionRepository  # noqa: PLC0415

    return DemoTransactionRepository(pool)


async def get_demo_app_service(
    repo=Depends(get_demo_transaction_repository),
):
    from forgeguard.services.demo_app import DemoAppService  # noqa: PLC0415

    return DemoAppService(repo)


async def get_data_subject_service(
    pool: asyncpg.Pool = Depends(get_pool),
):
    from forgeguard.data.repositories.audit_logs import AuditLogRepository  # noqa: PLC0415
    from forgeguard.services.audit import AuditService  # noqa: PLC0415
    from forgeguard.services.data_subject import DataSubjectService  # noqa: PLC0415

    audit_service = AuditService(AuditLogRepository(pool))
    return DataSubjectService(pool, audit_service)


# ------------------------------------------------------------------
# Release Guardian service factories
# ------------------------------------------------------------------


async def get_release_assessment_repo(
    pool: asyncpg.Pool = Depends(get_pool),
):
    from forgeguard.data.repositories.release_assessment_repository import (  # noqa: PLC0415
        ReleaseAssessmentRepository,
    )

    return ReleaseAssessmentRepository(pool)


async def get_assessment_score_repo(
    pool: asyncpg.Pool = Depends(get_pool),
):
    from forgeguard.data.repositories.assessment_score_repository import (  # noqa: PLC0415
        AssessmentScoreRepository,
    )

    return AssessmentScoreRepository(pool)


def get_forge_catalog_adapter():
    """Return a :class:`~forgeguard.services.forge_catalog.ForgeCatalogHttpAdapter`.

    Constructs a new adapter per request (stateless except for the shared
    module-level TTL cache inside ForgeCatalogHttpClient).  The API key is
    read from Settings and is NEVER logged or exposed in error responses.

    Returns:
        A fully configured :class:`~forgeguard.services.forge_catalog.ForgeCatalogHttpAdapter`.
    """
    from forgeguard.services.forge_catalog import ForgeCatalogHttpAdapter  # noqa: PLC0415
    from forgeguard.services.forge_catalog_client import ForgeCatalogHttpClient  # noqa: PLC0415

    settings = get_settings()
    client = ForgeCatalogHttpClient(
        base_url=settings.forge_catalog_url,
        api_key=settings.forge_catalog_api_key,
    )
    return ForgeCatalogHttpAdapter(client=client)


__all__ = [
    "SettingsDep",
    "get_settings",
    "get_ai_engine",
    "get_pool",
    "get_user_repository",
    "get_service_repository",
    "get_policy_repository",
    "get_finding_repository",
    "get_score_repository",
    "get_decision_repository",
    "get_audit_log_repository",
    "get_refresh_token_repository",
    "get_demo_transaction_repository",
    "get_demo_app_service",
    "get_data_subject_service",
    "get_release_assessment_repo",
    "get_assessment_score_repo",
    "get_forge_catalog_adapter",
]
