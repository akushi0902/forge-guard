"""OpenAI-compatible LLM provider adapter.

Communicates with any OpenAI-compatible endpoint (OpenAI, Azure OpenAI,
local vLLM, etc.) via HTTPS using httpx.AsyncClient.

API key handling:
    The API key is read from the constructor argument (which should always
    come from an environment variable via ``Settings``).  It is injected as
    an HTTP header and is NEVER logged, cached, or included in error messages.

Retry logic:
    A single automatic retry is attempted on HTTP 429 (rate limit), honouring
    the ``Retry-After`` response header.  All other errors propagate immediately
    so the circuit breaker can record them.
"""

from __future__ import annotations

import asyncio
import time

import httpx
import structlog

from ..errors import LLMProviderError, LLMTimeoutError
from ..models import CircuitState, HealthStatus, LLMResponse, ResponseSource
from ..provider import LLMProvider

logger = structlog.get_logger(__name__)


class OpenAIProvider(LLMProvider):
    """Adapter for OpenAI-compatible chat completions APIs.

    Args:
        base_url:        Base URL of the completions endpoint (no trailing slash).
        api_key:         Bearer token.  Must come from env var — never hardcode.
        model:           Model identifier (e.g. ``gpt-4o-mini``).
        temperature:     Sampling temperature (0.0–2.0).
        max_tokens:      Maximum tokens to generate.
        timeout_seconds: Request timeout in seconds.
    """

    def __init__(
        self,
        base_url: str = "https://api.openai.com/v1",
        api_key: str = "",
        model: str = "gpt-4o-mini",
        temperature: float = 0.7,
        max_tokens: int = 2048,
        timeout_seconds: int = 30,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._model = model
        self._temperature = temperature
        self._max_tokens = max_tokens
        self._timeout = timeout_seconds

    # ------------------------------------------------------------------
    # LLMProvider interface
    # ------------------------------------------------------------------

    async def generate_completion(
        self,
        prompt: str,
        params: dict | None = None,
    ) -> LLMResponse:
        payload = self._build_payload(prompt, params)
        return await self._call_with_retry(payload)

    async def generate_structured_output(
        self,
        prompt: str,
        schema: dict,
        params: dict | None = None,
    ) -> LLMResponse:
        payload = self._build_payload(prompt, params)
        payload["response_format"] = {"type": "json_object"}
        return await self._call_with_retry(payload)

    async def health_check(self) -> HealthStatus:
        return HealthStatus(
            circuit_state=CircuitState.CLOSED,
            cache_hit_ratio=0.0,
            avg_latency_ms=0.0,
            error_rate_pct=0.0,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_payload(self, prompt: str, params: dict | None) -> dict:
        overrides = params or {}
        return {
            "model": self._model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": overrides.get("temperature", self._temperature),
            "max_tokens": overrides.get("max_tokens", self._max_tokens),
        }

    def _make_client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
            },
            timeout=httpx.Timeout(float(self._timeout)),
        )

    async def _call_with_retry(self, payload: dict, max_retries: int = 1) -> LLMResponse:
        url = f"{self._base_url}/chat/completions"
        start = time.monotonic()

        async with self._make_client() as client:
            for attempt in range(max_retries + 1):
                try:
                    response = await client.post(url, json=payload)
                except httpx.TimeoutException as exc:
                    raise LLMTimeoutError(url, self._timeout) from exc

                if response.status_code == 429 and attempt < max_retries:
                    retry_after = int(response.headers.get("Retry-After", "1"))
                    logger.info(
                        "llm_rate_limited",
                        module="ai_engine",
                        operation="generate",
                        retry_after_seconds=retry_after,
                    )
                    await asyncio.sleep(retry_after)
                    continue

                if response.status_code >= 400:
                    raise LLMProviderError(
                        response.status_code,
                        f"LLM provider returned HTTP {response.status_code}",
                    )

                try:
                    data = response.json()
                except Exception as exc:
                    raise LLMProviderError(200, "LLM returned malformed JSON response") from exc

                latency_ms = int((time.monotonic() - start) * 1000)

                choices = data.get("choices") or []
                if not choices:
                    raise LLMProviderError(200, "LLM response contained no choices")

                content: str = choices[0].get("message", {}).get("content") or ""
                usage: dict = data.get("usage") or {}
                model: str = data.get("model", self._model)

                logger.debug(
                    "llm_response_received",
                    module="ai_engine",
                    operation="generate",
                    model=model,
                    latency_ms=latency_ms,
                    total_tokens=usage.get("total_tokens"),
                )

                return LLMResponse(
                    content=content,
                    confidence_score=1.0,
                    source=ResponseSource.AI_GENERATED,
                    latency_ms=latency_ms,
                    model=model,
                    token_usage=usage,
                )

        raise LLMProviderError(-1, "Max retries exceeded without a successful response")
