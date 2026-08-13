"""Recommendation generator: converts a finding into structured remediation guidance (WO-058).

Orchestrates the full LLM-or-template pipeline:
    1. Build a prompt from finding context.
    2. Call AIEngineService.generate_completion (circuit-breaker protected).
    3. On CircuitOpenError / any LLM failure: fall back to TemplateEngine.
    4. Parse the raw text response into structured fields.
    5. Return a RecommendationResult with source, confidence_score, and three
       text fields (recommendation_text, implementation_guide, business_impact).

Template fallback always succeeds — the generator never propagates LLM errors
to its caller; it degrades gracefully to source='template_fallback'.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

import structlog

from forgeguard.services.ai_engine.errors import CircuitOpenError
from forgeguard.services.ai_engine.models import ResponseSource
from forgeguard.services.ai_engine.service import AIEngineService
from forgeguard.services.ai_engine.template_engine import TemplateEngine

logger = structlog.get_logger(__name__)

_FALLBACK_CONFIDENCE = 0.50
_AI_CONFIDENCE_DEFAULT = 0.75


@dataclass
class RecommendationResult:
    """Structured output of a single recommendation generation call."""

    recommendation_text: str
    implementation_guide: str
    business_impact: str
    confidence_score: float  # 0.0–1.0
    source: str  # 'ai_generated' | 'template_fallback'


def _build_prompt(finding: dict[str, Any]) -> str:
    """Construct the LLM prompt from finding fields."""
    severity = finding.get("severity", "unknown")
    dimension = finding.get("dimension", "unknown")
    title = finding.get("title", "Policy violation")
    description = finding.get("description", "")
    evidence = finding.get("evidence", {})

    evidence_str = ""
    if isinstance(evidence, dict):
        for k, v in evidence.items():
            evidence_str += f"  {k}: {v}\n"
    else:
        evidence_str = str(evidence)

    return (
        "You are a senior software engineer providing remediation guidance for a "
        "policy violation detected during a governance assessment.\n\n"
        f"Finding Title: {title}\n"
        f"Severity: {severity}\n"
        f"Dimension: {dimension}\n"
        f"Description: {description}\n"
        f"Evidence:\n{evidence_str}\n\n"
        "Please provide a structured response with EXACTLY these three sections:\n"
        "## Recommendation\n"
        "<concise explanation of what needs to be fixed and why>\n\n"
        "## Implementation Steps\n"
        "<numbered step-by-step implementation guide>\n\n"
        "## Business Impact\n"
        "<explanation of the business risk if this finding is not remediated>\n"
    )


def _parse_llm_response(content: str) -> tuple[str, str, str]:
    """Extract the three structured sections from the LLM response.

    Returns (recommendation_text, implementation_guide, business_impact).
    Falls back to using the full content in recommendation_text when parsing fails.
    """
    rec_match = re.search(
        r"##\s*Recommendation\s*\n(.*?)(?=##|\Z)", content, re.DOTALL | re.IGNORECASE
    )
    impl_match = re.search(
        r"##\s*Implementation Steps?\s*\n(.*?)(?=##|\Z)", content, re.DOTALL | re.IGNORECASE
    )
    impact_match = re.search(
        r"##\s*Business Impact\s*\n(.*?)(?=##|\Z)", content, re.DOTALL | re.IGNORECASE
    )

    recommendation_text = rec_match.group(1).strip() if rec_match else content.strip()
    implementation_guide = impl_match.group(1).strip() if impl_match else ""
    business_impact = impact_match.group(1).strip() if impact_match else ""

    if not implementation_guide:
        implementation_guide = "See recommendation text for guidance."
    if not business_impact:
        business_impact = "Unresolved policy violations may impact release readiness and compliance posture."

    return recommendation_text, implementation_guide, business_impact


def _template_fallback(
    finding: dict[str, Any],
    template_engine: TemplateEngine | None,
) -> RecommendationResult:
    """Generate a template-based recommendation when the LLM is unavailable."""
    severity = finding.get("severity", "unknown")
    dimension = finding.get("dimension", "unknown")
    title = finding.get("title", "Policy violation")
    description = finding.get("description", "")

    if template_engine is not None:
        try:
            context = {
                "finding_title": title,
                "dimension": dimension,
                "severity": severity,
                "evidence": str(finding.get("evidence", {})),
                "policy_rule_description": description or title,
            }
            rendered = template_engine.render(
                finding_type=dimension,
                severity=severity,
                variables=context,
            )
            return RecommendationResult(
                recommendation_text=rendered.recommendation_text,
                implementation_guide=rendered.implementation_guide or "Review and remediate per engineering standards.",
                business_impact=rendered.business_impact or (
                    f"A {severity} finding in the {dimension} dimension may block release approval."
                ),
                confidence_score=rendered.confidence_score,
                source="template_fallback",
            )
        except Exception as exc:
            logger.warning(
                "recommendation_generator.template_engine_failed",
                error=str(exc),
                dimension=dimension,
                severity=severity,
            )

    # Generic fallback when no template engine or template rendering failed
    return RecommendationResult(
        recommendation_text=(
            f"This {severity} finding in the {dimension} dimension requires attention. "
            f"{description or title}"
        ),
        implementation_guide=(
            "1. Review the evidence attached to this finding.\n"
            "2. Identify the root cause of the policy violation.\n"
            "3. Implement the necessary fix and verify compliance.\n"
            "4. Re-run the assessment to confirm resolution."
        ),
        business_impact=(
            f"A {severity} violation in {dimension} may impact release readiness "
            "and overall engineering health score."
        ),
        confidence_score=_FALLBACK_CONFIDENCE,
        source="template_fallback",
    )


class RecommendationGenerator:
    """Generates structured remediation recommendations from finding context.

    Wraps AIEngineService with structured parsing and graceful template fallback.

    Args:
        ai_engine:       AIEngineService facade (circuit breaker + cache + provider).
        template_engine: Optional TemplateEngine for fallback responses.
    """

    def __init__(
        self,
        ai_engine: AIEngineService,
        template_engine: TemplateEngine | None = None,
    ) -> None:
        self._ai = ai_engine
        self._template_engine = template_engine

    async def generate(
        self,
        finding: dict[str, Any],
    ) -> RecommendationResult:
        """Generate a structured recommendation for the given finding.

        Attempts LLM generation first; falls back to templates on any failure.
        Never raises — always returns a RecommendationResult.
        """
        prompt = _build_prompt(finding)

        try:
            response = await self._ai.generate_completion(prompt)
            confidence = max(0.0, min(1.0, float(response.confidence_score)))
            rec_text, impl_guide, biz_impact = _parse_llm_response(response.content)
            source = (
                "ai_generated"
                if response.source in (
                    ResponseSource.AI_GENERATED,
                    ResponseSource.AI_GENERATED_CACHED,
                )
                else "template_fallback"
            )
            return RecommendationResult(
                recommendation_text=rec_text,
                implementation_guide=impl_guide,
                business_impact=biz_impact,
                confidence_score=confidence,
                source=source,
            )
        except CircuitOpenError:
            logger.warning(
                "recommendation_generator.circuit_open_fallback",
                finding_id=str(finding.get("id", "")),
            )
        except Exception as exc:
            logger.error(
                "recommendation_generator.llm_error_fallback",
                finding_id=str(finding.get("id", "")),
                error=str(exc),
            )

        return _template_fallback(finding, self._template_engine)
