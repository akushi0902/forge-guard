"""Unit tests for AIEngineService using MockLLMProvider.

Covers:
    1. Successful completion call flow (cache miss → provider → cache set).
    2. Second identical call served from cache (source=AI_GENERATED_CACHED).
    3. Circuit breaker integration — provider failures open the circuit.
    4. CircuitOpenError propagated to caller when circuit is open.
    5. Cache is checked before circuit breaker — cached responses served even
       when circuit would be open.
    6. health_check returns accurate metrics after a sequence of calls.
    7. generate_structured_output uses a different cache key than generate_completion.
    8. Error count tracked correctly.
"""

from __future__ import annotations

import pytest

from forgeguard.services.ai_engine.cache import ResponseCache
from forgeguard.services.ai_engine.circuit_breaker import CircuitBreaker
from forgeguard.services.ai_engine.errors import CircuitOpenError, LLMProviderError
from forgeguard.services.ai_engine.models import CircuitState, LLMResponse, ResponseSource
from forgeguard.services.ai_engine.service import AIEngineService

from .conftest import MockLLMProvider


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_service(
    fail_times: int = 0,
    cb_threshold: int = 5,
    cache_ttl: int = 3600,
) -> tuple[AIEngineService, MockLLMProvider]:
    provider = MockLLMProvider(fail_times=fail_times)
    cb = CircuitBreaker(
        failure_threshold=cb_threshold,
        window_seconds=60,
        recovery_timeout=30,
    )
    cache = ResponseCache(ttl_seconds=cache_ttl)
    service = AIEngineService(provider, cb, cache)
    return service, provider


# ---------------------------------------------------------------------------
# Successful call flow
# ---------------------------------------------------------------------------

class TestSuccessfulCallFlow:
    async def test_generate_completion_returns_response(self) -> None:
        service, _ = _make_service()
        resp = await service.generate_completion("Test prompt")
        assert isinstance(resp, LLMResponse)
        assert resp.content

    async def test_first_call_is_ai_generated(self) -> None:
        service, _ = _make_service()
        resp = await service.generate_completion("Test prompt")
        assert resp.source == ResponseSource.AI_GENERATED

    async def test_second_call_served_from_cache(self) -> None:
        service, provider = _make_service()
        await service.generate_completion("Repeated prompt")
        resp2 = await service.generate_completion("Repeated prompt")
        assert resp2.source == ResponseSource.AI_GENERATED_CACHED
        # Provider should have been called only once.
        assert provider.call_count == 1

    async def test_different_prompts_call_provider_each_time(self) -> None:
        service, provider = _make_service()
        await service.generate_completion("Prompt A")
        await service.generate_completion("Prompt B")
        assert provider.call_count == 2

    async def test_params_affect_cache_key(self) -> None:
        service, provider = _make_service()
        await service.generate_completion("Prompt", params={"temperature": 0.5})
        await service.generate_completion("Prompt", params={"temperature": 0.9})
        assert provider.call_count == 2


# ---------------------------------------------------------------------------
# Circuit breaker integration
# ---------------------------------------------------------------------------

class TestCircuitBreakerIntegration:
    async def test_failures_open_circuit(self) -> None:
        service, _ = _make_service(fail_times=999, cb_threshold=5)
        for _ in range(5):
            with pytest.raises(LLMProviderError):
                await service.generate_completion(f"prompt_{_}")
        assert service._cb.state == CircuitState.OPEN

    async def test_circuit_open_error_propagated(self) -> None:
        service, _ = _make_service(fail_times=999, cb_threshold=3)
        for _ in range(3):
            with pytest.raises(LLMProviderError):
                await service.generate_completion(f"unique_{_}")
        with pytest.raises(CircuitOpenError):
            await service.generate_completion("new prompt")

    async def test_cache_hit_bypasses_open_circuit(self) -> None:
        service, _ = _make_service(fail_times=999, cb_threshold=3)
        # First call — provider not yet failing.
        provider = MockLLMProvider(fail_times=0)
        service._provider = provider
        cached_prompt = "cached prompt"
        first_resp = await service.generate_completion(cached_prompt)
        assert first_resp.source == ResponseSource.AI_GENERATED

        # Open the circuit by switching to a failing provider and exhausting threshold.
        service._provider = MockLLMProvider(fail_times=999)
        for _ in range(3):
            with pytest.raises((LLMProviderError, Exception)):
                await service.generate_completion(f"fail_{_}")

        assert service._cb.state == CircuitState.OPEN

        # Cached prompt still served even with open circuit.
        resp = await service.generate_completion(cached_prompt)
        assert resp.source == ResponseSource.AI_GENERATED_CACHED


# ---------------------------------------------------------------------------
# Error tracking
# ---------------------------------------------------------------------------

class TestErrorTracking:
    async def test_error_count_incremented_on_failure(self) -> None:
        service, _ = _make_service(fail_times=3, cb_threshold=10)
        for _ in range(3):
            with pytest.raises(LLMProviderError):
                await service.generate_completion(f"fail_{_}")
        assert service._error_count == 3

    async def test_request_count_incremented_on_all_calls(self) -> None:
        service, _ = _make_service(fail_times=2, cb_threshold=10)
        for _ in range(4):
            try:
                await service.generate_completion(f"p_{_}")
            except LLMProviderError:
                pass
        assert service._request_count == 4

    async def test_circuit_open_error_counts_as_error(self) -> None:
        service, _ = _make_service(fail_times=999, cb_threshold=1)
        with pytest.raises(LLMProviderError):
            await service.generate_completion("p1")
        with pytest.raises(CircuitOpenError):
            await service.generate_completion("p2")
        assert service._error_count == 2


# ---------------------------------------------------------------------------
# health_check
# ---------------------------------------------------------------------------

class TestHealthCheck:
    async def test_health_check_returns_health_status(self) -> None:
        service, _ = _make_service()
        status = await service.health_check()
        assert status.circuit_state == CircuitState.CLOSED
        assert status.cache_hit_ratio == 0.0
        assert status.avg_latency_ms >= 0.0
        assert status.error_rate_pct == 0.0

    async def test_health_check_reflects_open_circuit(self) -> None:
        service, _ = _make_service(fail_times=999, cb_threshold=3)
        for _ in range(3):
            with pytest.raises(LLMProviderError):
                await service.generate_completion(f"fail_{_}")
        status = await service.health_check()
        assert status.circuit_state == CircuitState.OPEN

    async def test_health_check_cache_hit_ratio_after_hits(self) -> None:
        service, _ = _make_service()
        await service.generate_completion("repeated")
        await service.generate_completion("repeated")  # cache hit
        status = await service.health_check()
        assert status.cache_hit_ratio > 0.0

    async def test_health_check_error_rate(self) -> None:
        service, _ = _make_service(fail_times=1, cb_threshold=10)
        with pytest.raises(LLMProviderError):
            await service.generate_completion("fail")
        await service.generate_completion("success")
        status = await service.health_check()
        # 1 error out of 2 total requests (cache miss + provider call) = 50%
        assert status.error_rate_pct == pytest.approx(50.0)


# ---------------------------------------------------------------------------
# generate_structured_output
# ---------------------------------------------------------------------------

class TestGenerateStructuredOutput:
    async def test_structured_output_returns_response(self) -> None:
        service, _ = _make_service()
        schema = {"type": "object", "properties": {"risk": {"type": "string"}}}
        resp = await service.generate_structured_output("Analyse this PR", schema)
        assert isinstance(resp, LLMResponse)

    async def test_structured_output_cached_separately(self) -> None:
        service, provider = _make_service()
        schema = {"type": "object"}
        await service.generate_completion("same prompt")
        await service.generate_structured_output("same prompt", schema)
        # Both hit the provider since they have different cache keys.
        assert provider.call_count == 2

    async def test_structured_output_second_call_from_cache(self) -> None:
        service, provider = _make_service()
        schema = {"type": "object"}
        await service.generate_structured_output("prompt", schema)
        resp2 = await service.generate_structured_output("prompt", schema)
        assert resp2.source == ResponseSource.AI_GENERATED_CACHED
        assert provider.call_count == 1
