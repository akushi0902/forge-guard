"""Integration tests for OpenAIProvider using mocked httpx.AsyncClient.

All tests mock the HTTP transport via unittest.mock — no real LLM is contacted.
Scenarios covered:
    1. Successful completion response.
    2. Successful structured output (JSON mode).
    3. HTTP 429 rate limit with Retry-After header.
    4. HTTP 500 server error raises LLMProviderError.
    5. Timeout raises LLMTimeoutError.
    6. Malformed JSON body raises LLMProviderError.
    7. Empty choices list raises LLMProviderError.
    8. API key is never logged or included in error messages.
    9. End-to-end through AIEngineService — circuit breaker activates on 5 failures.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from forgeguard.services.ai_engine.cache import ResponseCache
from forgeguard.services.ai_engine.circuit_breaker import CircuitBreaker
from forgeguard.services.ai_engine.errors import (
    CircuitOpenError,
    LLMProviderError,
    LLMTimeoutError,
)
from forgeguard.services.ai_engine.models import CircuitState, ResponseSource
from forgeguard.services.ai_engine.providers.openai_provider import OpenAIProvider
from forgeguard.services.ai_engine.service import AIEngineService


# ---------------------------------------------------------------------------
# Mock HTTP response factory
# ---------------------------------------------------------------------------

def _make_openai_response(
    content: str = "Test response",
    model: str = "gpt-4o-mini",
    status_code: int = 200,
) -> MagicMock:
    mock_resp = MagicMock()
    mock_resp.status_code = status_code
    mock_resp.json.return_value = {
        "model": model,
        "choices": [{"message": {"content": content}}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30},
    }
    mock_resp.headers = {}
    return mock_resp


def _make_error_response(status_code: int, headers: dict | None = None) -> MagicMock:
    mock_resp = MagicMock()
    mock_resp.status_code = status_code
    mock_resp.headers = headers or {}
    return mock_resp


def _patch_client(mock_response) -> tuple:
    """Returns a context manager patch targeting OpenAIProvider._make_client."""
    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    mock_client.post = AsyncMock(return_value=mock_response)
    return mock_client


# ---------------------------------------------------------------------------
# Successful responses
# ---------------------------------------------------------------------------

class TestSuccessfulResponses:
    async def test_generate_completion_success(self) -> None:
        provider = OpenAIProvider(base_url="http://mock", api_key="sk-test")
        mock_client = _patch_client(_make_openai_response("Hello from LLM"))

        with patch.object(provider, "_make_client", return_value=mock_client):
            resp = await provider.generate_completion("Say hello")

        assert resp.content == "Hello from LLM"
        assert resp.source == ResponseSource.AI_GENERATED
        assert resp.model == "gpt-4o-mini"
        assert resp.token_usage["total_tokens"] == 30
        assert resp.confidence_score == 1.0
        assert resp.latency_ms >= 0

    async def test_generate_structured_output_success(self) -> None:
        provider = OpenAIProvider(base_url="http://mock", api_key="sk-test")
        structured_resp = _make_openai_response('{"risk": "high"}')
        mock_client = _patch_client(structured_resp)

        schema = {"type": "object", "properties": {"risk": {"type": "string"}}}
        with patch.object(provider, "_make_client", return_value=mock_client):
            resp = await provider.generate_structured_output("Analyse", schema)

        assert '{"risk": "high"}' in resp.content
        assert resp.source == ResponseSource.AI_GENERATED

    async def test_payload_includes_json_object_format_for_structured(self) -> None:
        provider = OpenAIProvider(base_url="http://mock", api_key="sk-test")
        captured_payload: list[dict] = []

        async def capturing_post(url, json):
            captured_payload.append(json)
            return _make_openai_response()

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.post = capturing_post

        schema = {"type": "object"}
        with patch.object(provider, "_make_client", return_value=mock_client):
            await provider.generate_structured_output("prompt", schema)

        assert captured_payload[0].get("response_format") == {"type": "json_object"}


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------

class TestErrorHandling:
    async def test_http_500_raises_llm_provider_error(self) -> None:
        provider = OpenAIProvider(base_url="http://mock", api_key="sk-test")
        mock_client = _patch_client(_make_error_response(500))

        with patch.object(provider, "_make_client", return_value=mock_client):
            with pytest.raises(LLMProviderError) as exc_info:
                await provider.generate_completion("prompt")
        assert exc_info.value.status_code == 500
        assert "500" in str(exc_info.value)

    async def test_http_404_raises_llm_provider_error(self) -> None:
        provider = OpenAIProvider(base_url="http://mock", api_key="sk-test")
        mock_client = _patch_client(_make_error_response(404))

        with patch.object(provider, "_make_client", return_value=mock_client):
            with pytest.raises(LLMProviderError) as exc_info:
                await provider.generate_completion("prompt")
        assert exc_info.value.status_code == 404

    async def test_timeout_raises_llm_timeout_error(self) -> None:
        provider = OpenAIProvider(base_url="http://mock", api_key="sk-test", timeout_seconds=10)

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.post = AsyncMock(side_effect=httpx.TimeoutException("timed out"))

        with patch.object(provider, "_make_client", return_value=mock_client):
            with pytest.raises(LLMTimeoutError) as exc_info:
                await provider.generate_completion("prompt")
        assert exc_info.value.timeout_seconds == 10

    async def test_malformed_json_raises_llm_provider_error(self) -> None:
        provider = OpenAIProvider(base_url="http://mock", api_key="sk-test")

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.side_effect = ValueError("invalid json")
        mock_resp.headers = {}
        mock_client = _patch_client(mock_resp)

        with patch.object(provider, "_make_client", return_value=mock_client):
            with pytest.raises(LLMProviderError) as exc_info:
                await provider.generate_completion("prompt")
        assert exc_info.value.status_code == 200
        assert "json" in str(exc_info.value).lower()

    async def test_empty_choices_raises_llm_provider_error(self) -> None:
        provider = OpenAIProvider(base_url="http://mock", api_key="sk-test")

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"model": "gpt-4o-mini", "choices": [], "usage": {}}
        mock_resp.headers = {}
        mock_client = _patch_client(mock_resp)

        with patch.object(provider, "_make_client", return_value=mock_client):
            with pytest.raises(LLMProviderError):
                await provider.generate_completion("prompt")


# ---------------------------------------------------------------------------
# 429 retry logic
# ---------------------------------------------------------------------------

class TestRateLimitRetry:
    async def test_429_retried_once(self) -> None:
        provider = OpenAIProvider(base_url="http://mock", api_key="sk-test")

        rate_limit_resp = _make_error_response(429, headers={"Retry-After": "0"})
        success_resp = _make_openai_response("After retry")

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        # First call returns 429, second returns 200.
        mock_client.post = AsyncMock(side_effect=[rate_limit_resp, success_resp])

        with patch.object(provider, "_make_client", return_value=mock_client):
            with patch("forgeguard.services.ai_engine.providers.openai_provider.asyncio.sleep") as mock_sleep:
                resp = await provider.generate_completion("prompt")

        assert resp.content == "After retry"
        mock_sleep.assert_called_once_with(0)

    async def test_429_no_second_retry(self) -> None:
        """After one retry, a second 429 should raise LLMProviderError."""
        provider = OpenAIProvider(base_url="http://mock", api_key="sk-test")

        rate_limit_resp = _make_error_response(429, headers={"Retry-After": "0"})

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.post = AsyncMock(return_value=rate_limit_resp)

        with patch.object(provider, "_make_client", return_value=mock_client):
            with patch("forgeguard.services.ai_engine.providers.openai_provider.asyncio.sleep"):
                with pytest.raises(LLMProviderError) as exc_info:
                    await provider.generate_completion("prompt")
        assert exc_info.value.status_code == 429


# ---------------------------------------------------------------------------
# API key security
# ---------------------------------------------------------------------------

class TestAPIKeySecurity:
    async def test_api_key_not_in_error_message(self) -> None:
        secret_key = "sk-super-secret-key-do-not-expose"
        provider = OpenAIProvider(base_url="http://mock", api_key=secret_key)
        mock_client = _patch_client(_make_error_response(500))

        with patch.object(provider, "_make_client", return_value=mock_client):
            with pytest.raises(LLMProviderError) as exc_info:
                await provider.generate_completion("prompt")
        assert secret_key not in str(exc_info.value)

    async def test_api_key_not_in_timeout_error(self) -> None:
        secret_key = "sk-super-secret-key-do-not-expose"
        provider = OpenAIProvider(base_url="http://mock", api_key=secret_key)

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.post = AsyncMock(side_effect=httpx.TimeoutException("timed out"))

        with patch.object(provider, "_make_client", return_value=mock_client):
            with pytest.raises(LLMTimeoutError) as exc_info:
                await provider.generate_completion("prompt")
        assert secret_key not in str(exc_info.value)


# ---------------------------------------------------------------------------
# End-to-end through AIEngineService
# ---------------------------------------------------------------------------

class TestEndToEndWithService:
    def _make_service_with_provider(self, provider: OpenAIProvider) -> AIEngineService:
        cb = CircuitBreaker(failure_threshold=5, window_seconds=60, recovery_timeout=30)
        cache = ResponseCache(ttl_seconds=3600)
        return AIEngineService(provider, cb, cache)

    async def test_success_end_to_end(self) -> None:
        provider = OpenAIProvider(base_url="http://mock", api_key="sk-test")
        mock_client = _patch_client(_make_openai_response("Full pipeline response"))

        with patch.object(provider, "_make_client", return_value=mock_client):
            service = self._make_service_with_provider(provider)
            resp = await service.generate_completion("Full pipeline prompt")

        assert resp.content == "Full pipeline response"
        assert resp.source == ResponseSource.AI_GENERATED

    async def test_five_failures_open_circuit(self) -> None:
        provider = OpenAIProvider(base_url="http://mock", api_key="sk-test")
        error_resp = _make_error_response(500)

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.post = AsyncMock(return_value=error_resp)

        service = self._make_service_with_provider(provider)

        with patch.object(provider, "_make_client", return_value=mock_client):
            for i in range(5):
                with pytest.raises(LLMProviderError):
                    await service.generate_completion(f"unique_prompt_{i}")

        assert service._cb.state == CircuitState.OPEN

        with pytest.raises(CircuitOpenError):
            await service.generate_completion("another prompt")

    async def test_health_check_after_failures(self) -> None:
        provider = OpenAIProvider(base_url="http://mock", api_key="sk-test")
        error_resp = _make_error_response(500)

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.post = AsyncMock(return_value=error_resp)

        service = self._make_service_with_provider(provider)
        with patch.object(provider, "_make_client", return_value=mock_client):
            for i in range(3):
                with pytest.raises(LLMProviderError):
                    await service.generate_completion(f"unique_{i}")

        status = await service.health_check()
        assert status.error_rate_pct > 0.0
