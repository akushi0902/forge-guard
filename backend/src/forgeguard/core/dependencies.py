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


__all__ = [
    "SettingsDep",
    "get_settings",
    "get_ai_engine",
]
