"""Data models for the AI Engine module.

All types in this module are plain dataclasses or enums so they can be
imported by any layer (provider, service, route handler) without pulling in
framework dependencies.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class ResponseSource(str, Enum):
    """Indicates where an LLMResponse originated."""

    AI_GENERATED = "ai-generated"
    AI_GENERATED_CACHED = "ai-generated-cached"
    TEMPLATE_GENERATED = "template-generated"


class CircuitState(str, Enum):
    """States of the circuit breaker."""

    CLOSED = "closed"       # Normal operation — requests pass through.
    OPEN = "open"           # Failing — requests rejected immediately.
    HALF_OPEN = "half-open" # Recovery probe — one request allowed through.


@dataclass
class LLMResponse:
    """Structured response returned by every LLM provider call."""

    content: str
    confidence_score: float          # 0.0–1.0
    source: ResponseSource
    latency_ms: int
    model: str
    token_usage: dict = field(default_factory=dict)


@dataclass
class HealthStatus:
    """Aggregated health metrics for the AI Engine service."""

    circuit_state: CircuitState
    cache_hit_ratio: float           # 0.0–1.0
    avg_latency_ms: float
    error_rate_pct: float            # 0.0–100.0


@dataclass
class LLMConfig:
    """Configuration for an LLM provider instance."""

    base_url: str = "https://api.openai.com/v1"
    api_key: str = ""
    model: str = "gpt-4o-mini"
    temperature: float = 0.7
    max_tokens: int = 2048
    timeout_seconds: int = 30
