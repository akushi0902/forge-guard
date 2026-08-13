"""Circuit breaker implementation for LLM provider calls.

State machine:

    CLOSED  ──(≥ threshold failures in window)──► OPEN
    OPEN    ──(recovery_timeout elapsed)────────► HALF_OPEN
    HALF_OPEN ──(probe succeeds)─────────────────► CLOSED
    HALF_OPEN ──(probe fails)────────────────────► OPEN

The circuit breaker is concurrency-safe: asyncio.Lock protects all state
mutations.  Only one probe request is allowed through during HALF_OPEN;
other concurrent requests receive CircuitOpenError immediately.

Usage::

    cb = CircuitBreaker(failure_threshold=5, window_seconds=60, recovery_timeout=30)
    try:
        result = await cb.call(provider.generate_completion(prompt))
    except CircuitOpenError:
        return fallback_template_response()
"""

from __future__ import annotations

import asyncio
import time
from collections import deque
from typing import Any, Coroutine, TypeVar

import structlog

from .errors import CircuitOpenError
from .models import CircuitState

logger = structlog.get_logger(__name__)

_T = TypeVar("_T")


class CircuitBreaker:
    """Async circuit breaker that wraps coroutine calls.

    Args:
        failure_threshold:  Number of failures in the window that opens the circuit.
        window_seconds:     Rolling window in which failures are counted.
        recovery_timeout:   Seconds to wait in OPEN before transitioning to HALF_OPEN.
    """

    def __init__(
        self,
        failure_threshold: int = 5,
        window_seconds: int = 60,
        recovery_timeout: int = 30,
    ) -> None:
        self._threshold = failure_threshold
        self._window = window_seconds
        self._recovery_timeout = recovery_timeout

        self._state: CircuitState = CircuitState.CLOSED
        self._failures: deque[float] = deque()   # monotonic timestamps
        self._opened_at: float | None = None
        self._half_open_in_flight: bool = False
        self._lock: asyncio.Lock = asyncio.Lock()

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    @property
    def state(self) -> CircuitState:
        """Current circuit state (read-only snapshot)."""
        return self._state

    @property
    def failure_count(self) -> int:
        """Number of failures currently inside the rolling window."""
        self._evict_stale_failures()
        return len(self._failures)

    async def call(self, coro: Coroutine[Any, Any, _T]) -> _T:
        """Execute the coroutine, applying circuit breaker semantics.

        Args:
            coro: An awaitable coroutine (e.g. ``provider.generate_completion(...)``).

        Returns:
            The coroutine's return value.

        Raises:
            CircuitOpenError:  Circuit is OPEN or HALF_OPEN probe slot is busy.
            Any exception the coroutine raises is re-raised after recording the failure.
        """
        is_half_open = await self._acquire_slot()

        try:
            result = await coro
        except Exception:
            await self._record_failure(is_half_open=is_half_open)
            raise
        else:
            await self._record_success(is_half_open=is_half_open)
            return result

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _evict_stale_failures(self) -> None:
        """Remove failure timestamps older than the rolling window."""
        cutoff = time.monotonic() - self._window
        while self._failures and self._failures[0] < cutoff:
            self._failures.popleft()

    async def _transition(self, new_state: CircuitState) -> None:
        """Mutate state and emit a structured log event.  Must hold the lock."""
        old = self._state
        self._state = new_state
        logger.info(
            "circuit_breaker_state_transition",
            module="ai_engine",
            operation="state_transition",
            circuit_state=new_state.value,
            previous_state=old.value,
            new_state=new_state.value,
            failure_count=len(self._failures),
            timestamp=time.time(),
        )

    async def _acquire_slot(self) -> bool:
        """Check state and reserve a slot if allowed.

        Returns:
            True if the slot was acquired in HALF_OPEN (probe request).

        Raises:
            CircuitOpenError: If the circuit is not accepting requests.
        """
        async with self._lock:
            if self._state == CircuitState.OPEN:
                # Check if recovery_timeout has elapsed — if so, try HALF_OPEN.
                if (
                    self._opened_at is not None
                    and (time.monotonic() - self._opened_at) >= self._recovery_timeout
                ):
                    self._half_open_in_flight = False
                    await self._transition(CircuitState.HALF_OPEN)
                else:
                    raise CircuitOpenError(self._state.value)

            if self._state == CircuitState.HALF_OPEN:
                if self._half_open_in_flight:
                    # Another probe is already running — fast-fail this request.
                    raise CircuitOpenError(self._state.value)
                self._half_open_in_flight = True
                return True  # is_half_open

            return False  # CLOSED

    async def _record_failure(self, *, is_half_open: bool) -> None:
        async with self._lock:
            if is_half_open:
                # Probe failed → back to OPEN immediately.
                self._half_open_in_flight = False
                self._failures.clear()
                self._failures.append(time.monotonic())
                await self._transition(CircuitState.OPEN)
                self._opened_at = time.monotonic()
            else:
                # CLOSED: record and check threshold.
                self._failures.append(time.monotonic())
                self._evict_stale_failures()
                if len(self._failures) >= self._threshold:
                    await self._transition(CircuitState.OPEN)
                    self._opened_at = time.monotonic()

    async def _record_success(self, *, is_half_open: bool) -> None:
        async with self._lock:
            if is_half_open:
                # Probe succeeded → close the circuit.
                self._failures.clear()
                self._half_open_in_flight = False
                await self._transition(CircuitState.CLOSED)
