"""Unit tests for ExplanationGenerator (WO-047).

All tests use mocked AIEngineService — no database or external LLM required.

Scenarios covered:
  - All-risky: all dimensions > threshold → findings for each
  - Single-dimension risky: only one dimension > threshold
  - No-risk: all scores below threshold → empty list
  - Contributing factor findings: top-5 factors generate specific findings
  - Timeout fallback: LLM takes > 5 s → template source
  - LLM format error fallback: non-JSON response → template fields filled in
  - Deduplication: same metric in multiple dimensions → single highest-severity finding
  - Severity mapping at each threshold boundary
  - Max explanation length truncation
  - Source field: ai-generated vs template-generated
"""

from __future__ import annotations

import asyncio
import json
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from forgeguard.services.ai_engine.models import LLMResponse, ResponseSource
from forgeguard.services.release_guardian.explanation_generator import ExplanationGenerator
from forgeguard.services.release_guardian.models import (
    AnalysisMetadata,
    ChangeAnalysisResult,
    ComplexityMetrics,
    ContributingFactor,
    CoverageMetrics,
    DependencyMetrics,
    FindingSource,
    RiskDimension,
    RiskFinding,
    RiskScoreResult,
    RiskSeverity,
    SecurityMetrics,
)
from forgeguard.services.release_guardian.prompt_loader import PromptLoader

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_SERVICE_CONTEXT = {
    "service_id": str(uuid.uuid4()),
    "assessment_id": str(uuid.uuid4()),
    "service_name": "payment-service",
}

_NOW = datetime.now(tz=timezone.utc)


def _make_risk_result(
    *,
    complexity=0,
    coverage=0,
    dependencies=0,
    security=0,
    factors: list[ContributingFactor] | None = None,
) -> RiskScoreResult:
    return RiskScoreResult(
        overall_score=max(complexity, coverage, dependencies, security),
        dimension_scores={
            "code_complexity": complexity,
            "test_coverage": coverage,
            "dependencies": dependencies,
            "security": security,
        },
        contributing_factors=factors or [],
        weights_used={"code_complexity": 0.25, "test_coverage": 0.25, "dependencies": 0.25, "security": 0.25},
        scored_at=_NOW,
    )


def _make_change_analysis() -> ChangeAnalysisResult:
    return ChangeAnalysisResult(
        complexity=ComplexityMetrics(files_changed=5),
        coverage=CoverageMetrics(),
        dependencies=DependencyMetrics(),
        security=SecurityMetrics(),
        metadata=AnalysisMetadata(),
    )


def _llm_response(content: str, source: ResponseSource = ResponseSource.AI_GENERATED) -> LLMResponse:
    return LLMResponse(
        content=content,
        confidence_score=0.85,
        source=source,
        latency_ms=100,
        model="gpt-4o-mini",
        token_usage={},
    )


def _json_response(explanation="Test explanation.", business_impact="Test impact.", steps=None):
    return json.dumps({
        "explanation": explanation,
        "business_impact": business_impact,
        "remediation_steps": steps or ["Step 1", "Step 2", "Step 3"],
    })


def _make_ai_engine(response_content: str | None = None, source=ResponseSource.AI_GENERATED) -> MagicMock:
    ai_engine = MagicMock()
    content = response_content if response_content is not None else _json_response()
    ai_engine.generate_completion = AsyncMock(return_value=_llm_response(content, source))
    return ai_engine


def _make_generator(ai_engine=None, threshold=40, llm_timeout=5.0) -> ExplanationGenerator:
    loader = PromptLoader()
    loader.load_all()
    return ExplanationGenerator(
        ai_engine=ai_engine or _make_ai_engine(),
        prompt_loader=loader,
        threshold=threshold,
        llm_timeout=llm_timeout,
    )


# ---------------------------------------------------------------------------
# No-risk scenario
# ---------------------------------------------------------------------------

class TestNoRisk:
    async def test_empty_list_when_all_below_threshold(self):
        gen = _make_generator()
        result = _make_risk_result(complexity=10, coverage=20, dependencies=30, security=15)
        findings = await gen.generate_findings(result, _make_change_analysis(), _SERVICE_CONTEXT)
        assert findings == []

    async def test_empty_contributing_factors_no_findings(self):
        gen = _make_generator()
        result = _make_risk_result(complexity=0, coverage=0)
        findings = await gen.generate_findings(result, _make_change_analysis(), _SERVICE_CONTEXT)
        assert findings == []


# ---------------------------------------------------------------------------
# Severity mapping
# ---------------------------------------------------------------------------

class TestSeverityMapping:
    @pytest.mark.parametrize("score,expected_severity", [
        (30, RiskSeverity.LOW),
        (31, RiskSeverity.MEDIUM),
        (50, RiskSeverity.MEDIUM),
        (51, RiskSeverity.HIGH),
        (75, RiskSeverity.HIGH),
        (76, RiskSeverity.CRITICAL),
        (100, RiskSeverity.CRITICAL),
    ])
    async def test_severity_mapping(self, score, expected_severity):
        gen = _make_generator(threshold=0)
        result = _make_risk_result(complexity=score)
        findings = await gen.generate_findings(result, _make_change_analysis(), _SERVICE_CONTEXT)
        complexity_findings = [f for f in findings if f.dimension == RiskDimension.CODE_COMPLEXITY]
        assert len(complexity_findings) >= 1
        assert complexity_findings[0].severity == expected_severity


# ---------------------------------------------------------------------------
# Single dimension risky
# ---------------------------------------------------------------------------

class TestSingleDimensionRisky:
    async def test_one_finding_for_one_risky_dimension(self):
        gen = _make_generator()
        result = _make_risk_result(complexity=80, coverage=10, dependencies=10, security=10)
        findings = await gen.generate_findings(result, _make_change_analysis(), _SERVICE_CONTEXT)
        assert len(findings) >= 1
        dims = {f.dimension for f in findings}
        assert RiskDimension.CODE_COMPLEXITY in dims

    async def test_finding_has_required_fields(self):
        gen = _make_generator()
        result = _make_risk_result(complexity=80)
        findings = await gen.generate_findings(result, _make_change_analysis(), _SERVICE_CONTEXT)
        f = findings[0]
        assert f.title
        assert f.explanation
        assert f.business_impact
        assert isinstance(f.remediation_steps, list)
        assert len(f.remediation_steps) >= 1
        assert 0.0 <= f.confidence_score <= 1.0
        assert f.source in (FindingSource.AI_GENERATED, FindingSource.TEMPLATE_GENERATED)


# ---------------------------------------------------------------------------
# All dimensions risky
# ---------------------------------------------------------------------------

class TestAllDimensionsRisky:
    async def test_findings_for_all_risky_dimensions(self):
        gen = _make_generator()
        result = _make_risk_result(complexity=80, coverage=70, dependencies=60, security=90)
        findings = await gen.generate_findings(result, _make_change_analysis(), _SERVICE_CONTEXT)
        dims = {f.dimension for f in findings}
        assert RiskDimension.CODE_COMPLEXITY in dims
        assert RiskDimension.TEST_COVERAGE in dims
        assert RiskDimension.DEPENDENCIES in dims
        assert RiskDimension.SECURITY in dims

    async def test_assessment_id_and_service_id_set(self):
        gen = _make_generator()
        result = _make_risk_result(complexity=80)
        ctx = {**_SERVICE_CONTEXT, "assessment_id": "aaa", "service_id": "bbb"}
        findings = await gen.generate_findings(result, _make_change_analysis(), ctx)
        assert all(f.assessment_id == "aaa" for f in findings)
        assert all(f.service_id == "bbb" for f in findings)


# ---------------------------------------------------------------------------
# Contributing factor findings
# ---------------------------------------------------------------------------

class TestContributingFactorFindings:
    async def test_factor_findings_generated(self):
        factors = [
            ContributingFactor(
                metric_name="files_changed",
                actual_value=47.0,
                threshold=20.0,
                risk_contribution=30.0,
                dimension="code_complexity",
            )
        ]
        gen = _make_generator(threshold=0)
        result = _make_risk_result(complexity=60, factors=factors)
        findings = await gen.generate_findings(result, _make_change_analysis(), _SERVICE_CONTEXT)
        titles = [f.title for f in findings]
        assert any("files_changed" in t.lower() or "Files Changed" in t for t in titles)

    async def test_zero_contribution_factor_skipped(self):
        factors = [
            ContributingFactor(
                metric_name="churn_score",
                actual_value=0.0,
                threshold=0.5,
                risk_contribution=0.0,
                dimension="code_complexity",
            )
        ]
        gen = _make_generator(threshold=100)  # only factor findings would generate
        result = _make_risk_result(complexity=0, factors=factors)
        findings = await gen.generate_findings(result, _make_change_analysis(), _SERVICE_CONTEXT)
        assert findings == []


# ---------------------------------------------------------------------------
# Source field
# ---------------------------------------------------------------------------

class TestSourceField:
    async def test_ai_generated_source_on_success(self):
        gen = _make_generator()
        result = _make_risk_result(complexity=80)
        findings = await gen.generate_findings(result, _make_change_analysis(), _SERVICE_CONTEXT)
        dim_findings = [f for f in findings if f.dimension == RiskDimension.CODE_COMPLEXITY]
        assert any(f.source == FindingSource.AI_GENERATED for f in dim_findings)

    async def test_template_generated_when_llm_returns_template_source(self):
        ai_engine = _make_ai_engine(source=ResponseSource.TEMPLATE_GENERATED)
        gen = _make_generator(ai_engine=ai_engine)
        result = _make_risk_result(complexity=80)
        findings = await gen.generate_findings(result, _make_change_analysis(), _SERVICE_CONTEXT)
        assert all(f.source == FindingSource.TEMPLATE_GENERATED for f in findings)


# ---------------------------------------------------------------------------
# Timeout fallback
# ---------------------------------------------------------------------------

class TestTimeoutFallback:
    async def test_template_used_on_timeout(self):
        async def _slow(*args, **kwargs):
            await asyncio.sleep(10)

        ai_engine = MagicMock()
        ai_engine.generate_completion = _slow
        gen = _make_generator(ai_engine=ai_engine, llm_timeout=0.01)
        result = _make_risk_result(complexity=80)
        findings = await gen.generate_findings(result, _make_change_analysis(), _SERVICE_CONTEXT)
        assert len(findings) >= 1
        assert all(f.source == FindingSource.TEMPLATE_GENERATED for f in findings)

    async def test_other_findings_succeed_if_one_times_out(self):
        call_count = 0

        async def _mixed_responses(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                await asyncio.sleep(10)
            return _llm_response(_json_response())

        ai_engine = MagicMock()
        ai_engine.generate_completion = _mixed_responses
        gen = _make_generator(ai_engine=ai_engine, llm_timeout=0.01)
        result = _make_risk_result(complexity=80, coverage=70)
        findings = await gen.generate_findings(result, _make_change_analysis(), _SERVICE_CONTEXT)
        assert len(findings) >= 1


# ---------------------------------------------------------------------------
# LLM format error fallback
# ---------------------------------------------------------------------------

class TestFormatErrorFallback:
    async def test_non_json_response_uses_template_fields(self):
        ai_engine = _make_ai_engine("This is not JSON at all.")
        gen = _make_generator(ai_engine=ai_engine)
        result = _make_risk_result(complexity=80)
        findings = await gen.generate_findings(result, _make_change_analysis(), _SERVICE_CONTEXT)
        assert len(findings) >= 1
        f = findings[0]
        assert f.explanation  # has some explanation (raw text or template)
        assert f.business_impact  # has business impact from template
        assert isinstance(f.remediation_steps, list)

    async def test_exception_from_llm_uses_template(self):
        ai_engine = MagicMock()
        ai_engine.generate_completion = AsyncMock(side_effect=RuntimeError("LLM failure"))
        gen = _make_generator(ai_engine=ai_engine)
        result = _make_risk_result(complexity=80)
        findings = await gen.generate_findings(result, _make_change_analysis(), _SERVICE_CONTEXT)
        assert len(findings) >= 1
        assert all(f.source == FindingSource.TEMPLATE_GENERATED for f in findings)


# ---------------------------------------------------------------------------
# Deduplication
# ---------------------------------------------------------------------------

class TestDeduplication:
    async def test_same_metric_across_dimensions_deduplicates(self):
        factors = [
            ContributingFactor(
                metric_name="files_changed",
                actual_value=50.0,
                threshold=20.0,
                risk_contribution=25.0,
                dimension="code_complexity",
            ),
            ContributingFactor(
                metric_name="files_changed",
                actual_value=50.0,
                threshold=20.0,
                risk_contribution=20.0,
                dimension="test_coverage",
            ),
        ]
        gen = _make_generator(threshold=0)
        result = _make_risk_result(
            complexity=80, coverage=60, factors=factors
        )
        findings = await gen.generate_findings(result, _make_change_analysis(), _SERVICE_CONTEXT)
        # The files_changed metric should appear only once in findings
        files_changed_findings = [
            f for f in findings if "files_changed" in f.title.lower() or "Files Changed" in f.title
        ]
        assert len(files_changed_findings) <= 1

    async def test_highest_severity_kept_on_dedup(self):
        factors = [
            ContributingFactor(
                metric_name="test_metric",
                actual_value=10.0,
                threshold=5.0,
                risk_contribution=30.0,
                dimension="code_complexity",  # score=80 → critical
            ),
            ContributingFactor(
                metric_name="test_metric",
                actual_value=10.0,
                threshold=5.0,
                risk_contribution=20.0,
                dimension="test_coverage",  # score=40 → medium
            ),
        ]
        gen = _make_generator(threshold=39)
        result = _make_risk_result(complexity=80, coverage=40, factors=factors)
        findings = await gen.generate_findings(result, _make_change_analysis(), _SERVICE_CONTEXT)
        metric_findings = [f for f in findings if "test_metric" in f.title.lower() or "Test Metric" in f.title]
        if metric_findings:
            # The kept finding should be the higher-severity one
            assert metric_findings[0].severity in (RiskSeverity.HIGH, RiskSeverity.CRITICAL)


# ---------------------------------------------------------------------------
# Max explanation length
# ---------------------------------------------------------------------------

class TestMaxExplanationLength:
    async def test_long_explanation_truncated(self):
        long_text = "A" * 5000
        content = json.dumps({
            "explanation": long_text,
            "business_impact": long_text,
            "remediation_steps": ["Step 1"],
        })
        ai_engine = _make_ai_engine(content)
        gen = _make_generator(ai_engine=ai_engine, threshold=0)
        result = _make_risk_result(complexity=80)
        findings = await gen.generate_findings(result, _make_change_analysis(), _SERVICE_CONTEXT)
        assert all(len(f.explanation) <= 2000 for f in findings)
        assert all(len(f.business_impact) <= 2000 for f in findings)
