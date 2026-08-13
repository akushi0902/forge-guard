"""Typed exceptions for the AI Engine module.

Callers catch these to implement fallback strategies (e.g. template generation
when the circuit is open, retry logic for timeouts).

Design notes:
    - No LLM API key or provider configuration is ever included in error
      messages or attributes — only sanitized metadata (status codes, endpoints).
    - ``CircuitOpenError`` is the primary signal for callers to fall back to
      template-based responses without waiting for an LLM.
"""

from __future__ import annotations


class CircuitOpenError(Exception):
    """Raised when the circuit breaker is in the OPEN or HALF_OPEN (busy) state.

    Callers should treat this as a soft failure and fall back to templates.
    """

    def __init__(self, state: str, message: str = "Circuit breaker is open — LLM call rejected") -> None:
        self.state = state
        super().__init__(message)


class LLMTimeoutError(Exception):
    """Raised when an LLM HTTP request exceeds the configured timeout."""

    def __init__(self, endpoint: str, timeout_seconds: int) -> None:
        self.endpoint = endpoint
        self.timeout_seconds = timeout_seconds
        super().__init__(
            f"LLM request timed out after {timeout_seconds}s (endpoint: {endpoint})"
        )


class LLMProviderError(Exception):
    """Raised for non-timeout LLM failures (4xx/5xx responses, malformed JSON).

    The ``status_code`` is included for routing logic (e.g. 429 vs 500),
    but the message is sanitized and never contains credentials.
    """

    def __init__(self, status_code: int, message: str) -> None:
        self.status_code = status_code
        super().__init__(message)
