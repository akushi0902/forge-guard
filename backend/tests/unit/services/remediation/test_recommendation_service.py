"""Unit tests for RecommendationService and RecommendationGenerator (WO-058).

Covers:
  - RecommendationGenerator: LLM success path, circuit-open fallback, LLM error fallback
  - RecommendationGenerator: prompt structure contains finding fields
  - RecommendationGenerator: response parsing (structured sections)
  - RecommendationService: returns cached recommendation (idempotent)
  - RecommendationService: generates new recommendation when none exists
  - RecommendationService: force_refresh bypasses cache
  - RecommendationService: raises NotFoundError for unknown finding
  - RecommendationService: audit event is logged after generation
  - Confidence score validation: 0.0, 0.5, 1.0, clamped at boundaries
  - Source values: ai_generated vs template_fallback

Run:
    pytest tests/unit/services/remediation/test_recommendation_service.py -v
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from forgeguard.core.exceptions import NotFoundError
from forgeguard.services.ai_engine.errors import CircuitOpenError
from forgeguard.services.ai_engine.recommendation_generator import (
    RecommendationGenerator,
    RecommendationResult,
    _build_prompt,
    _parse_llm_response,
    _template_fallback,
)
from forgeguard.services.remediation.recommendation_service import RecommendationService
from tests.fixtures.remediation_fixtures import (
    AI_RECOMMENDATION_RESULT,
    CRITICAL_SECURITY_FINDING,
    FINDING_CVE_ID,
    HIGH_COVERAGE_FINDING,
    LLM_RESPONSE_AI,
    TEMPLATE_RECOMMENDATION_RESULT,
    make_persisted_recommendation,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_service(
    *,
    finding: dict | None = CRITICAL_SECURITY_FINDING,
    existing_rec: dict | None = None,
    generator_result: RecommendationResult = AI_RECOMMENDATION_RESULT,
) -> tuple[RecommendationService, MagicMock, MagicMock, MagicMock, MagicMock]:
    finding_repo = MagicMock()
    finding_repo.get_by_id = AsyncMock(return_value=finding)

    rec_repo = MagicMock()
    rec_repo.get_latest_by_finding_id = AsyncMock(return_value=existing_rec)
    persisted = make_persisted_recommendation(result=generator_result)
    rec_repo.upsert = AsyncMock(return_value=persisted)
    rec_repo.create = AsyncMock(return_value=persisted)

    generator = MagicMock()
    generator.generate = AsyncMock(return_value=generator_result)

    audit_svc = MagicMock()
    audit_svc.log_event = AsyncMock(return_value={})

    svc = RecommendationService(
        finding_repo=finding_repo,
        rec_repo=rec_repo,
        generator=generator,
        audit_svc=audit_svc,
    )
    return svc, finding_repo, rec_repo, generator, audit_svc


# ===========================================================================
# RecommendationService — core flow
# ===========================================================================

class TestRecommendationService_GetOrGenerate:
    @pytest.mark.asyncio
    async def test_returns_cached_when_exists(self):
        existing = make_persisted_recommendation()
        svc, finding_repo, rec_repo, generator, _ = _make_service(existing_rec=existing)
        result = await svc.get_or_generate(FINDING_CVE_ID)
        assert result["id"] == existing["id"]
        generator.generate.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_generates_when_no_existing(self):
        svc, _, rec_repo, generator, _ = _make_service(existing_rec=None)
        await svc.get_or_generate(FINDING_CVE_ID)
        generator.generate.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_force_refresh_bypasses_cache(self):
        existing = make_persisted_recommendation()
        svc, _, rec_repo, generator, _ = _make_service(existing_rec=existing)
        await svc.get_or_generate(FINDING_CVE_ID, force_refresh=True)
        generator.generate.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_raises_not_found_for_missing_finding(self):
        svc, _, _, _, _ = _make_service(finding=None)
        with pytest.raises(NotFoundError):
            await svc.get_or_generate(FINDING_CVE_ID)

    @pytest.mark.asyncio
    async def test_persists_via_upsert(self):
        svc, _, rec_repo, _, _ = _make_service(existing_rec=None)
        await svc.get_or_generate(FINDING_CVE_ID)
        rec_repo.upsert.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_upsert_fallback_to_create_on_error(self):
        svc, _, rec_repo, _, _ = _make_service(existing_rec=None)
        rec_repo.upsert.side_effect = Exception("no unique constraint")
        await svc.get_or_generate(FINDING_CVE_ID)
        rec_repo.create.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_audit_event_logged_after_generation(self):
        svc, _, _, _, audit_svc = _make_service(existing_rec=None)
        await svc.get_or_generate(FINDING_CVE_ID, actor_id=str(uuid.uuid4()), actor_role="developer")
        audit_svc.log_event.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_audit_event_action_is_recommendation_generated(self):
        svc, _, _, _, audit_svc = _make_service(existing_rec=None)
        await svc.get_or_generate(FINDING_CVE_ID)
        call_kwargs = audit_svc.log_event.call_args[1]
        assert call_kwargs["action"] == "recommendation.generated"

    @pytest.mark.asyncio
    async def test_audit_event_resource_type(self):
        svc, _, _, _, audit_svc = _make_service(existing_rec=None)
        await svc.get_or_generate(FINDING_CVE_ID)
        call_kwargs = audit_svc.log_event.call_args[1]
        assert call_kwargs["resource_type"] == "remediation_recommendation"

    @pytest.mark.asyncio
    async def test_audit_failure_does_not_propagate(self):
        svc, _, _, _, audit_svc = _make_service(existing_rec=None)
        audit_svc.log_event.side_effect = Exception("DB down")
        # Should not raise — audit is best-effort
        result = await svc.get_or_generate(FINDING_CVE_ID)
        assert result is not None

    @pytest.mark.asyncio
    async def test_recommendation_has_source_field(self):
        svc, _, _, _, _ = _make_service(existing_rec=None)
        result = await svc.get_or_generate(FINDING_CVE_ID)
        assert "source" in result

    @pytest.mark.asyncio
    async def test_cached_recommendation_not_logged(self):
        existing = make_persisted_recommendation()
        svc, _, _, _, audit_svc = _make_service(existing_rec=existing)
        await svc.get_or_generate(FINDING_CVE_ID)
        audit_svc.log_event.assert_not_awaited()


# ===========================================================================
# RecommendationGenerator — LLM path
# ===========================================================================

class TestRecommendationGenerator_LLMPath:
    @pytest.mark.asyncio
    async def test_llm_success_returns_ai_generated_source(self):
        ai_engine = MagicMock()
        ai_engine.generate_completion = AsyncMock(return_value=LLM_RESPONSE_AI)
        gen = RecommendationGenerator(ai_engine=ai_engine)
        result = await gen.generate(CRITICAL_SECURITY_FINDING)
        assert result.source == "ai_generated"

    @pytest.mark.asyncio
    async def test_llm_success_confidence_clamped_to_01(self):
        from forgeguard.services.ai_engine.models import LLMResponse, ResponseSource
        over_conf = LLMResponse(
            content="## Recommendation\nFix it.\n\n## Implementation Steps\n1. Do it.\n\n## Business Impact\nBig.",
            confidence_score=1.5,  # over 1.0
            source=ResponseSource.AI_GENERATED,
            latency_ms=100,
            model="gpt-4o-mini",
        )
        ai_engine = MagicMock()
        ai_engine.generate_completion = AsyncMock(return_value=over_conf)
        gen = RecommendationGenerator(ai_engine=ai_engine)
        result = await gen.generate(CRITICAL_SECURITY_FINDING)
        assert result.confidence_score <= 1.0

    @pytest.mark.asyncio
    async def test_circuit_open_falls_back_to_template(self):
        ai_engine = MagicMock()
        ai_engine.generate_completion = AsyncMock(
            side_effect=CircuitOpenError("open")
        )
        gen = RecommendationGenerator(ai_engine=ai_engine)
        result = await gen.generate(CRITICAL_SECURITY_FINDING)
        assert result.source == "template_fallback"

    @pytest.mark.asyncio
    async def test_llm_error_falls_back_to_template(self):
        ai_engine = MagicMock()
        ai_engine.generate_completion = AsyncMock(
            side_effect=Exception("connection error")
        )
        gen = RecommendationGenerator(ai_engine=ai_engine)
        result = await gen.generate(CRITICAL_SECURITY_FINDING)
        assert result.source == "template_fallback"

    @pytest.mark.asyncio
    async def test_fallback_has_nonzero_confidence(self):
        ai_engine = MagicMock()
        ai_engine.generate_completion = AsyncMock(
            side_effect=CircuitOpenError("open")
        )
        gen = RecommendationGenerator(ai_engine=ai_engine)
        result = await gen.generate(CRITICAL_SECURITY_FINDING)
        assert 0.0 < result.confidence_score <= 1.0

    @pytest.mark.asyncio
    async def test_fallback_has_nonempty_implementation_guide(self):
        ai_engine = MagicMock()
        ai_engine.generate_completion = AsyncMock(
            side_effect=CircuitOpenError("open")
        )
        gen = RecommendationGenerator(ai_engine=ai_engine)
        result = await gen.generate(CRITICAL_SECURITY_FINDING)
        assert len(result.implementation_guide) > 0

    @pytest.mark.asyncio
    async def test_result_always_returned_never_raises(self):
        ai_engine = MagicMock()
        ai_engine.generate_completion = AsyncMock(
            side_effect=RuntimeError("unexpected")
        )
        gen = RecommendationGenerator(ai_engine=ai_engine)
        # Should not raise
        result = await gen.generate(CRITICAL_SECURITY_FINDING)
        assert isinstance(result, RecommendationResult)


# ===========================================================================
# Prompt building
# ===========================================================================

class TestPromptBuilding:
    def test_prompt_includes_severity(self):
        prompt = _build_prompt(CRITICAL_SECURITY_FINDING)
        assert "critical" in prompt.lower()

    def test_prompt_includes_dimension(self):
        prompt = _build_prompt(CRITICAL_SECURITY_FINDING)
        assert "security" in prompt.lower()

    def test_prompt_includes_title(self):
        prompt = _build_prompt(CRITICAL_SECURITY_FINDING)
        assert CRITICAL_SECURITY_FINDING["title"] in prompt

    def test_prompt_includes_evidence(self):
        prompt = _build_prompt(CRITICAL_SECURITY_FINDING)
        # evidence dict keys should appear
        assert "actual_value" in prompt or "critical_cve_count" in prompt

    def test_prompt_requests_three_sections(self):
        prompt = _build_prompt(CRITICAL_SECURITY_FINDING)
        assert "Recommendation" in prompt
        assert "Implementation Steps" in prompt
        assert "Business Impact" in prompt


# ===========================================================================
# Response parsing
# ===========================================================================

class TestResponseParsing:
    def test_parses_all_three_sections(self):
        content = (
            "## Recommendation\nFix the CVE.\n\n"
            "## Implementation Steps\n1. Upgrade.\n2. Test.\n\n"
            "## Business Impact\nExposure to exploits."
        )
        rec, impl, impact = _parse_llm_response(content)
        assert "Fix the CVE" in rec
        assert "Upgrade" in impl
        assert "exploits" in impact

    def test_missing_sections_use_defaults(self):
        content = "Just a plain response without sections."
        rec, impl, impact = _parse_llm_response(content)
        assert len(rec) > 0
        assert len(impl) > 0
        assert len(impact) > 0

    def test_partial_content_fills_defaults(self):
        content = "## Recommendation\nOnly this section."
        rec, impl, impact = _parse_llm_response(content)
        assert "Only this section" in rec
        assert impl != ""
        assert impact != ""


# ===========================================================================
# Template fallback
# ===========================================================================

class TestTemplateFallback:
    def test_no_template_engine_returns_generic(self):
        result = _template_fallback(CRITICAL_SECURITY_FINDING, None)
        assert result.source == "template_fallback"
        assert len(result.recommendation_text) > 0
        assert len(result.implementation_guide) > 0
        assert result.confidence_score == 0.50

    def test_fallback_mentions_severity(self):
        result = _template_fallback(CRITICAL_SECURITY_FINDING, None)
        assert "critical" in result.recommendation_text.lower() or "critical" in result.business_impact.lower()

    def test_template_engine_failure_falls_back_to_generic(self):
        bad_engine = MagicMock()
        bad_engine.render = MagicMock(side_effect=Exception("YAML missing"))
        result = _template_fallback(CRITICAL_SECURITY_FINDING, bad_engine)
        assert result.source == "template_fallback"
        assert len(result.recommendation_text) > 0


# ===========================================================================
# Confidence score edge cases
# ===========================================================================

class TestConfidenceScore:
    @pytest.mark.asyncio
    async def test_confidence_zero_point_zero(self):
        from forgeguard.services.ai_engine.models import LLMResponse, ResponseSource
        response = LLMResponse(
            content="## Recommendation\nFix.\n## Implementation Steps\n1. Do it.\n## Business Impact\nBig.",
            confidence_score=0.0,
            source=ResponseSource.AI_GENERATED,
            latency_ms=100,
            model="gpt-4o-mini",
        )
        ai_engine = MagicMock()
        ai_engine.generate_completion = AsyncMock(return_value=response)
        gen = RecommendationGenerator(ai_engine=ai_engine)
        result = await gen.generate(CRITICAL_SECURITY_FINDING)
        assert result.confidence_score == 0.0

    @pytest.mark.asyncio
    async def test_confidence_one_point_zero(self):
        from forgeguard.services.ai_engine.models import LLMResponse, ResponseSource
        response = LLMResponse(
            content="## Recommendation\nFix.\n## Implementation Steps\n1. Do it.\n## Business Impact\nBig.",
            confidence_score=1.0,
            source=ResponseSource.AI_GENERATED,
            latency_ms=100,
            model="gpt-4o-mini",
        )
        ai_engine = MagicMock()
        ai_engine.generate_completion = AsyncMock(return_value=response)
        gen = RecommendationGenerator(ai_engine=ai_engine)
        result = await gen.generate(CRITICAL_SECURITY_FINDING)
        assert result.confidence_score == 1.0

    @pytest.mark.asyncio
    async def test_negative_confidence_clamped_to_zero(self):
        from forgeguard.services.ai_engine.models import LLMResponse, ResponseSource
        response = LLMResponse(
            content="## Recommendation\nFix.\n## Implementation Steps\n1. Do it.\n## Business Impact\nBig.",
            confidence_score=-0.1,
            source=ResponseSource.AI_GENERATED,
            latency_ms=100,
            model="gpt-4o-mini",
        )
        ai_engine = MagicMock()
        ai_engine.generate_completion = AsyncMock(return_value=response)
        gen = RecommendationGenerator(ai_engine=ai_engine)
        result = await gen.generate(CRITICAL_SECURITY_FINDING)
        assert result.confidence_score >= 0.0
