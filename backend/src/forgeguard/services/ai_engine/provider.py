"""Abstract LLM provider interface.

All concrete LLM adapters (OpenAI, Anthropic, local models, etc.) must
implement :class:`LLMProvider`.  Business logic never imports a concrete
provider directly — it depends only on this interface, enabling provider
swapping without touching domain code.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from .models import HealthStatus, LLMResponse


class LLMProvider(ABC):
    """Abstract base class for all LLM provider adapters.

    Implementing classes must be safe for concurrent async use — i.e. all
    state that changes across calls must be protected with appropriate
    concurrency primitives.
    """

    @abstractmethod
    async def generate_completion(
        self,
        prompt: str,
        params: dict | None = None,
    ) -> LLMResponse:
        """Generate a free-form text completion for the given prompt.

        Args:
            prompt:  The full prompt text to send to the model.
            params:  Optional per-call overrides (e.g. temperature, max_tokens).

        Returns:
            An :class:`~forgeguard.services.ai_engine.models.LLMResponse`
            with the model's output and metadata.

        Raises:
            LLMTimeoutError:   The provider did not respond within the timeout.
            LLMProviderError:  The provider returned an error response.
        """

    @abstractmethod
    async def generate_structured_output(
        self,
        prompt: str,
        schema: dict,
        params: dict | None = None,
    ) -> LLMResponse:
        """Generate a JSON-structured response conforming to the given schema.

        Args:
            prompt:  The full prompt text.
            schema:  JSON Schema dict describing the expected output structure.
            params:  Optional per-call parameter overrides.

        Returns:
            An :class:`~forgeguard.services.ai_engine.models.LLMResponse`
            whose ``content`` is a JSON string matching ``schema``.

        Raises:
            LLMTimeoutError:   The provider did not respond within the timeout.
            LLMProviderError:  The provider returned an error response.
        """

    @abstractmethod
    async def health_check(self) -> HealthStatus:
        """Return the provider's self-assessed health status.

        This is a lightweight check (no actual LLM call) used by the
        operator monitoring dashboard.
        """
