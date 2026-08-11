"""AIEngineService — the public interface for all AI-powered features.

Composes:
    LLMProvider      — abstract adapter (OpenAI, local, mock)
    CircuitBreaker   — fail-fast protection against flaky LLM
    ResponseCache    — TTL-based in-memory deduplication

Call path for ``generate_completion(prompt, params)``:
    1. Check cache → hit: return immediately with source=AI_GENERATED_CACHED
    2. Check circuit breaker → OPEN: raise CircuitOpenError (caller falls back)
    3. Execute provider call through circuit breaker
    4. On success: store in cache, return with source=AI_GENERATED
    5. On failure: circuit breaker records it, exception propagates

Usage::

    service = AIEngineService(provider, circuit_breaker, cache)
    try:
        resp = await service.generate_completion("Summarise this PR…")
    except CircuitOpenError:
        resp = template_response()
"""

from __future__ import annotations

import time
from collections import deque

import structlog

from .cache import ResponseCache
from .circuit_breaker import CircuitBreaker
from .errors import CircuitOpenError
from .models import HealthStatus, LLMResponse
from .provider import LLMProvider

logger = structlog.get_logger(__name__)

# Rolling window for latency tracking (last 300 data points ≈ last ~5 min at 1 rps).
_LATENCY_WINDOW = 300


class AIEngineService:
    """Facade that composes the LLM provider, circuit breaker, and cache.

    This is the single dependency downstream modules (Release Guardian,
    Policy Guardian, Remediation) should inject — never the provider directly.

    Args:
        provider:         Concrete :class:`~.provider.LLMProvider` implementation.
        circuit_breaker:  :class:`~.circuit_breaker.CircuitBreaker` instance.
        cache:            :class:`~.cache.ResponseCache` instance.
    """

    def __init__(
        self,
        provider: LLMProvider,
        circuit_breaker: CircuitBreaker,
        cache: ResponseCache,
    ) -> None:
        self._provider = provider
        self._cb = circuit_breaker
        self._cache = cache
        self._recent_latencies: deque[float] = deque(maxlen=_LATENCY_WINDOW)
        self._request_count: int = 0
        self._error_count: int = 0

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    async def generate_completion(
        self,
        prompt: str,
        params: dict | None = None,
    ) -> LLMResponse:
        """Generate a completion, using the cache and circuit breaker.

        Args:
            prompt: Full prompt text.
            params: Optional per-request parameter overrides.

        Returns:
            :class:`~.models.LLMResponse` (source reflects cache/live origin).

        Raises:
            CircuitOpenError: Circuit is open; caller should use templates.
            LLMTimeoutError:  Provider timed out.
            LLMProviderError: Provider returned an error.
        """
        self._request_count += 1

        cached = self._cache.get(prompt, params)
        if cached is not None:
            logger.debug(
                "llm_cache_hit",
                module="ai_engine",
                operation="generate_completion",
            )
            return cached

        start = time.monotonic()
        try:
            response = await self._cb.call(
                self._provider.generate_completion(prompt, params)
            )
        except CircuitOpenError:
            self._error_count += 1
            logger.warning(
                "llm_circuit_open",
                module="ai_engine",
                operation="generate_completion",
                circuit_state=self._cb.state.value,
            )
            raise
        except Exception:
            self._error_count += 1
            raise

        latency_ms = (time.monotonic() - start) * 1000
        self._recent_latencies.append(latency_ms)
        self._cache.set(prompt, params, response)
        return response

    async def generate_structured_output(
        self,
        prompt: str,
        schema: dict,
        params: dict | None = None,
    ) -> LLMResponse:
        """Generate a structured (JSON) completion, using the cache and circuit breaker.

        The cache key includes a repr of ``schema`` so the same prompt with
        different schemas results in distinct cache entries.
        """
        self._request_count += 1

        cache_params = {**(params or {}), "__schema_hash__": _dict_key(schema)}
        cached = self._cache.get(prompt, cache_params)
        if cached is not None:
            logger.debug(
                "llm_cache_hit",
                module="ai_engine",
                operation="generate_structured_output",
            )
            return cached

        start = time.monotonic()
        try:
            response = await self._cb.call(
                self._provider.generate_structured_output(prompt, schema, params)
            )
        except CircuitOpenError:
            self._error_count += 1
            raise
        except Exception:
            self._error_count += 1
            raise

        latency_ms = (time.monotonic() - start) * 1000
        self._recent_latencies.append(latency_ms)
        self._cache.set(prompt, cache_params, response)
        return response

    async def health_check(self) -> HealthStatus:
        """Return aggregated health metrics for the monitoring dashboard."""
        avg_latency = (
            sum(self._recent_latencies) / len(self._recent_latencies)
            if self._recent_latencies
            else 0.0
        )
        error_rate = (
            (self._error_count / self._request_count) * 100.0
            if self._request_count > 0
            else 0.0
        )
        return HealthStatus(
            circuit_state=self._cb.state,
            cache_hit_ratio=self._cache.hit_ratio,
            avg_latency_ms=avg_latency,
            error_rate_pct=error_rate,
        )


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _dict_key(d: dict) -> str:
    """Stable string representation of a dict for use as a cache key component."""
    import json
    return json.dumps(d, sort_keys=True)
