"""Shared fixtures for AI Engine tests.

All fixtures are self-contained — no external LLM is required.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from forgeguard.services.ai_engine.errors import LLMProviderError
from forgeguard.services.ai_engine.models import (
    CircuitState,
    HealthStatus,
    LLMResponse,
    ResponseSource,
)
from forgeguard.services.ai_engine.provider import LLMProvider


# ---------------------------------------------------------------------------
# Mock LLM provider
# ---------------------------------------------------------------------------

class MockLLMProvider(LLMProvider):
    """Configurable mock LLMProvider for unit tests.

    Args:
        responses:   List of LLMResponse objects to return in order.
                     When exhausted the last response is repeated.
        fail_times:  Number of initial calls that should raise LLMProviderError.
        fail_error:  Exception to raise when failing; defaults to LLMProviderError.
        delay:       Optional asyncio.sleep before each call (seconds).
    """

    def __init__(
        self,
        responses: list[LLMResponse] | None = None,
        fail_times: int = 0,
        fail_error: Exception | None = None,
        delay: float = 0.0,
    ) -> None:
        default_response = LLMResponse(
            content="Mock LLM response",
            confidence_score=0.9,
            source=ResponseSource.AI_GENERATED,
            latency_ms=50,
            model="mock-model",
            token_usage={"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30},
        )
        self._responses = responses or [default_response]
        self._fail_times = fail_times
        self._fail_error = fail_error or LLMProviderError(500, "Mock provider failure")
        self._delay = delay
        self._call_count = 0

    @property
    def call_count(self) -> int:
        return self._call_count

    async def generate_completion(
        self,
        prompt: str,
        params: dict | None = None,
    ) -> LLMResponse:
        if self._delay:
            await asyncio.sleep(self._delay)
        self._call_count += 1
        if self._call_count <= self._fail_times:
            raise self._fail_error
        idx = min(self._call_count - self._fail_times - 1, len(self._responses) - 1)
        return self._responses[idx]

    async def generate_structured_output(
        self,
        prompt: str,
        schema: dict,
        params: dict | None = None,
    ) -> LLMResponse:
        return await self.generate_completion(prompt, params)

    async def health_check(self) -> HealthStatus:
        return HealthStatus(
            circuit_state=CircuitState.CLOSED,
            cache_hit_ratio=0.0,
            avg_latency_ms=50.0,
            error_rate_pct=0.0,
        )


# ---------------------------------------------------------------------------
# Sample LLM responses (fixtures)
# ---------------------------------------------------------------------------

SAMPLE_RESPONSE = LLMResponse(
    content="This PR introduces a high-risk change to the payment processing module.",
    confidence_score=0.87,
    source=ResponseSource.AI_GENERATED,
    latency_ms=312,
    model="gpt-4o-mini",
    token_usage={"prompt_tokens": 150, "completion_tokens": 45, "total_tokens": 195},
)

SAMPLE_STRUCTURED_RESPONSE = LLMResponse(
    content='{"risk_level": "high", "summary": "Payment module change", "confidence": 0.87}',
    confidence_score=0.87,
    source=ResponseSource.AI_GENERATED,
    latency_ms=280,
    model="gpt-4o-mini",
    token_usage={"prompt_tokens": 180, "completion_tokens": 30, "total_tokens": 210},
)


# ---------------------------------------------------------------------------
# Pytest fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def mock_provider() -> MockLLMProvider:
    return MockLLMProvider()


@pytest.fixture()
def failing_provider() -> MockLLMProvider:
    return MockLLMProvider(fail_times=999)


@pytest.fixture()
def sample_response() -> LLMResponse:
    return SAMPLE_RESPONSE


@pytest.fixture()
def sample_prompt() -> str:
    return "Analyse the risk level of this pull request."
