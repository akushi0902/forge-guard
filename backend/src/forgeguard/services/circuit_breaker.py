"""Demo evaluation circuit breaker module (WO-056).

Provides a pre-configured :class:`CircuitBreaker` instance for wrapping LLM
calls in the demo evaluation pipeline.  Uses the canonical AI engine circuit
breaker implementation with the parameters specified in WO-056:
    - failure_threshold: 5 failures in 60 seconds opens the circuit
    - recovery_timeout:  30 seconds in OPEN before transitioning to HALF_OPEN

Usage::

    from forgeguard.services.circuit_breaker import create_demo_circuit_breaker
    from forgeguard.services.ai_engine.errors import CircuitOpenError

    cb = create_demo_circuit_breaker()
    try:
        result = await cb.call(ai_engine.generate_completion(prompt))
    except CircuitOpenError:
        result = template_fallback()
"""

from __future__ import annotations

from forgeguard.services.ai_engine.circuit_breaker import CircuitBreaker
from forgeguard.services.ai_engine.errors import CircuitOpenError

__all__ = ["CircuitBreaker", "CircuitOpenError", "create_demo_circuit_breaker"]

_FAILURE_THRESHOLD = 5
_WINDOW_SECONDS = 60
_RECOVERY_TIMEOUT = 30


def create_demo_circuit_breaker() -> CircuitBreaker:
    """Return a CircuitBreaker configured for the demo evaluation pipeline."""
    return CircuitBreaker(
        failure_threshold=_FAILURE_THRESHOLD,
        window_seconds=_WINDOW_SECONDS,
        recovery_timeout=_RECOVERY_TIMEOUT,
    )
