"""AI Engine — LLM provider abstraction with circuit breaker and response cache.

Public API::

    from forgeguard.services.ai_engine import (
        AIEngineService,
        LLMProvider,
        LLMResponse,
        HealthStatus,
        CircuitState,
        ResponseSource,
        LLMConfig,
        CircuitBreaker,
        ResponseCache,
        CircuitOpenError,
        LLMTimeoutError,
        LLMProviderError,
    )

Downstream modules should depend only on ``AIEngineService`` and the types
exported here — never on concrete provider implementations.
"""

from .cache import ResponseCache
from .circuit_breaker import CircuitBreaker
from .errors import CircuitOpenError, LLMProviderError, LLMTimeoutError
from .models import (
    CircuitState,
    HealthStatus,
    LLMConfig,
    LLMResponse,
    ResponseSource,
)
from .provider import LLMProvider
from .service import AIEngineService

__all__ = [
    "AIEngineService",
    "LLMProvider",
    "LLMResponse",
    "HealthStatus",
    "CircuitState",
    "ResponseSource",
    "LLMConfig",
    "CircuitBreaker",
    "ResponseCache",
    "CircuitOpenError",
    "LLMTimeoutError",
    "LLMProviderError",
]
