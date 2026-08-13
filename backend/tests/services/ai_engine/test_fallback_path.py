"""Integration tests for the template fallback path through AIEngineService.

Verifies that when the LLM circuit breaker opens, AIEngineService transparently
returns template-generated responses for all 20 finding types.

Test strategy:
  1. Create AIEngineService with a MockLLMProvider that always fails.
  2. Trip the circuit breaker by making enough requests to exceed the threshold.
  3. Verify subsequent calls return LLMResponse with source=TEMPLATE_GENERATED.
  4. Verify confidence_score and model fields are set correctly.
  5. Verify all 20 canonical finding types produce non-empty responses.
  6. Verify behaviour when no template engine is configured (should re-raise).
"""

from __future__ import annotations

import pytest

from forgeguard.services.ai_engine.cache import ResponseCache
from forgeguard.services.ai_engine.circuit_breaker import CircuitBreaker
from forgeguard.services.ai_engine.errors import CircuitOpenError
from forgeguard.services.ai_engine.models import LLMResponse, ResponseSource
from forgeguard.services.ai_engine.service import AIEngineService
from forgeguard.services.ai_engine.template_engine import TemplateEngine

from .conftest import MockLLMProvider


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_engine(default_confidence: float = 0.7) -> TemplateEngine:
    eng = TemplateEngine(default_confidence=default_confidence)
    eng.load_templates()
    return eng


def _make_failing_service(
    template_engine: TemplateEngine | None = None,
    cb_threshold: int = 3,
) -> AIEngineService:
    provider = MockLLMProvider(fail_times=9999)
    cb = CircuitBreaker(
        failure_threshold=cb_threshold,
        window_seconds=60,
        recovery_timeout=30,
    )
    cache = ResponseCache(ttl_seconds=3600)
    return AIEngineService(provider, cb, cache, template_engine=template_engine)


async def _trip_circuit(service: AIEngineService, threshold: int = 3) -> None:
    """Make enough failing calls to open the circuit breaker."""
    for _ in range(threshold):
        try:
            await service.generate_completion("probe", params={"finding_type": "probe"})
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Circuit opens and template fallback activates
# ---------------------------------------------------------------------------

class TestCircuitBreakerOpensAndFallbackActivates:
    async def test_circuit_opens_after_failures(self) -> None:
        engine = _make_engine()
        service = _make_failing_service(template_engine=engine)
        await _trip_circuit(service)
        # After circuit opens, next call should return a template response, not raise
        resp = await service.generate_completion(
            "Analysis prompt",
            params={
                "finding_type": "high_cyclomatic_complexity",
                "dimension": "code_complexity",
                "severity": "high",
            },
        )
        assert isinstance(resp, LLMResponse)
        assert resp.source == ResponseSource.TEMPLATE_GENERATED

    async def test_template_response_has_correct_model(self) -> None:
        engine = _make_engine()
        service = _make_failing_service(template_engine=engine)
        await _trip_circuit(service)
        resp = await service.generate_completion(
            "prompt",
            params={
                "finding_type": "known_cve",
                "dimension": "dependencies",
                "severity": "critical",
            },
        )
        assert resp.model == "template-engine"

    async def test_template_response_has_zero_latency(self) -> None:
        engine = _make_engine()
        service = _make_failing_service(template_engine=engine)
        await _trip_circuit(service)
        resp = await service.generate_completion(
            "prompt",
            params={
                "finding_type": "secrets_in_code",
                "dimension": "security",
                "severity": "critical",
            },
        )
        assert resp.latency_ms == 0

    async def test_template_response_confidence(self) -> None:
        engine = _make_engine(default_confidence=0.7)
        service = _make_failing_service(template_engine=engine)
        await _trip_circuit(service)
        resp = await service.generate_completion(
            "prompt",
            params={
                "finding_type": "test_regression",
                "dimension": "test_coverage",
                "severity": "critical",
            },
        )
        assert resp.confidence_score == pytest.approx(0.7)

    async def test_template_response_content_non_empty(self) -> None:
        engine = _make_engine()
        service = _make_failing_service(template_engine=engine)
        await _trip_circuit(service)
        resp = await service.generate_completion(
            "prompt",
            params={
                "finding_type": "sql_injection_risk",
                "dimension": "security",
                "severity": "critical",
                "service_name": "api-gateway",
            },
        )
        assert resp.content
        assert "api-gateway" in resp.content


# ---------------------------------------------------------------------------
# All 20 finding types produce responses via fallback
# ---------------------------------------------------------------------------

_ALL_FINDING_TYPES = [
    ("high_cyclomatic_complexity", "code_complexity", "high"),
    ("large_file_change", "code_complexity", "medium"),
    ("excessive_churn", "code_complexity", "critical"),
    ("deeply_nested_logic", "code_complexity", "medium"),
    ("low_coverage_delta", "test_coverage", "high"),
    ("missing_unit_tests", "test_coverage", "medium"),
    ("missing_integration_tests", "test_coverage", "high"),
    ("test_regression", "test_coverage", "critical"),
    ("known_cve", "dependencies", "critical"),
    ("outdated_dependency", "dependencies", "medium"),
    ("major_version_bump", "dependencies", "high"),
    ("new_transitive_dependency", "dependencies", "low"),
    ("secrets_in_code", "security", "critical"),
    ("sql_injection_risk", "security", "critical"),
    ("xss_risk", "security", "high"),
    ("insecure_configuration", "security", "high"),
    ("similar_change_caused_incident", "historical", "high"),
    ("high_risk_file_modified", "historical", "high"),
    ("deployment_window_risk", "historical", "high"),
    ("insufficient_soak_time", "historical", "high"),
]


class TestAllFindingTypesFallback:
    @pytest.fixture(scope="class")
    async def open_circuit_service(self) -> AIEngineService:
        engine = _make_engine()
        service = _make_failing_service(template_engine=engine)
        await _trip_circuit(service)
        return service

    @pytest.mark.parametrize("finding_type,dimension,severity", _ALL_FINDING_TYPES)
    async def test_all_finding_types_return_template_response(
        self,
        open_circuit_service: AIEngineService,
        finding_type: str,
        dimension: str,
        severity: str,
    ) -> None:
        resp = await open_circuit_service.generate_completion(
            "analysis prompt",
            params={
                "finding_type": finding_type,
                "dimension": dimension,
                "severity": severity,
                "service_name": "test-service",
            },
        )
        assert isinstance(resp, LLMResponse), f"Expected LLMResponse for {finding_type}"
        assert resp.source == ResponseSource.TEMPLATE_GENERATED, (
            f"Expected TEMPLATE_GENERATED for {finding_type}, got {resp.source}"
        )
        assert resp.content, f"Empty content for {finding_type}"


# ---------------------------------------------------------------------------
# No template engine configured → re-raises CircuitOpenError
# ---------------------------------------------------------------------------

class TestNoTemplateEngineConfigured:
    async def test_circuit_open_reraises_without_engine(self) -> None:
        service = _make_failing_service(template_engine=None)
        await _trip_circuit(service)
        with pytest.raises(CircuitOpenError):
            await service.generate_completion("prompt", params={})

    async def test_no_engine_default_is_none(self) -> None:
        provider = MockLLMProvider(fail_times=0)
        cb = CircuitBreaker(failure_threshold=5, window_seconds=60, recovery_timeout=30)
        cache = ResponseCache(ttl_seconds=3600)
        service = AIEngineService(provider, cb, cache)
        assert service._template_engine is None


# ---------------------------------------------------------------------------
# Generic fallback for unknown finding types
# ---------------------------------------------------------------------------

class TestGenericFallbackViaService:
    async def test_unknown_finding_type_uses_generic_fallback(self) -> None:
        engine = _make_engine()
        service = _make_failing_service(template_engine=engine)
        await _trip_circuit(service)
        resp = await service.generate_completion(
            "prompt",
            params={
                "finding_type": "totally_unknown_finding",
                "dimension": "generic",
                "severity": "medium",
            },
        )
        assert resp.source == ResponseSource.TEMPLATE_GENERATED
        # Generic fallback has lower confidence
        assert resp.confidence_score == pytest.approx(0.5)

    async def test_missing_params_uses_defaults(self) -> None:
        engine = _make_engine()
        service = _make_failing_service(template_engine=engine)
        await _trip_circuit(service)
        # No params at all — should not crash
        resp = await service.generate_completion("prompt", params={})
        assert resp.source == ResponseSource.TEMPLATE_GENERATED
