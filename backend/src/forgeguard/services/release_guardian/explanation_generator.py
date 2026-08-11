"""ExplanationGenerator — transforms RiskScoreResult into RiskFinding objects.

Orchestration:
  1. Collect candidate findings from dimension scores (score > threshold) and
     top contributing factors.
  2. Deduplicate candidates by (dimension, primary_metric); same metric across
     dimensions merges into the higher-severity finding.
  3. Generate explanation, business impact, and remediation steps for each
     finding via AIEngineService.generate_completion, wrapped in
     asyncio.wait_for(5 s).  On timeout or any exception, fall back to the
     PromptLoader text templates.
  4. Optionally persist findings and remediation recommendations.

Severity mapping (0-100 risk score, higher = riskier):
  0-30  → low
  31-50 → medium
  51-75 → high
  76-100 → critical
"""

from __future__ import annotations

import asyncio
import json
import time
import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import structlog

from forgeguard.services.ai_engine.models import ResponseSource
from forgeguard.services.release_guardian.models import (
    ChangeAnalysisResult,
    FindingSource,
    RiskDimension,
    RiskFinding,
    RiskScoreResult,
    RiskSeverity,
)
from forgeguard.services.release_guardian.prompt_loader import PromptLoader

if TYPE_CHECKING:
    from forgeguard.data.repositories.findings import FindingRepository
    from forgeguard.data.repositories.remediation_recommendation_repository import (
        RemediationRecommendationRepository,
    )
    from forgeguard.services.ai_engine.service import AIEngineService

logger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_DEFAULT_THRESHOLD = 40
_MAX_EXPLANATION_LENGTH = 2000
_LLM_TIMEOUT_SECONDS = 5.0
_TOP_FACTORS = 5
_TEMPLATE_CONFIDENCE = 0.5

_SEVERITY_RANK: dict[str, int] = {
    "low": 0,
    "medium": 1,
    "high": 2,
    "critical": 3,
}

# Known release_guardian dimension values mapped to RiskDimension enum values.
_KNOWN_DIMENSIONS: frozenset[str] = frozenset(d.value for d in RiskDimension)


# ---------------------------------------------------------------------------
# Internal data class
# ---------------------------------------------------------------------------


@dataclass
class _FindingCandidate:
    """Intermediate representation before LLM enrichment."""

    dimension: str
    primary_metric: str  # "dimension_overall" for dimension-level; metric_name otherwise
    score: int
    metric_name: str
    metric_value: float
    threshold: float
    severity: str
    title: str


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _score_to_severity(score: int) -> str:
    if score <= 30:
        return "low"
    if score <= 50:
        return "medium"
    if score <= 75:
        return "high"
    return "critical"


def _to_risk_dimension(dimension: str) -> RiskDimension:
    try:
        return RiskDimension(dimension)
    except ValueError:
        return RiskDimension.CODE_COMPLEXITY


# ---------------------------------------------------------------------------
# ExplanationGenerator
# ---------------------------------------------------------------------------


class ExplanationGenerator:
    """Generates natural-language risk findings from a RiskScoreResult.

    Args:
        ai_engine:        AIEngineService for LLM-powered explanations.
        prompt_loader:    PromptLoader pre-loaded with template files.
        finding_repo:     Optional FindingRepository for persistence.
        remediation_repo: Optional RemediationRecommendationRepository for
                          persisting remediation recommendations.
        threshold:        Minimum dimension score (0-100) to generate a finding.
        max_explanation_length: Maximum characters for explanation/business_impact.
        llm_timeout:      Per-finding LLM timeout in seconds.
    """

    def __init__(
        self,
        ai_engine: "AIEngineService",
        prompt_loader: PromptLoader,
        finding_repo: "FindingRepository | None" = None,
        remediation_repo: "RemediationRecommendationRepository | None" = None,
        *,
        threshold: int = _DEFAULT_THRESHOLD,
        max_explanation_length: int = _MAX_EXPLANATION_LENGTH,
        llm_timeout: float = _LLM_TIMEOUT_SECONDS,
    ) -> None:
        self._ai_engine = ai_engine
        self._prompt_loader = prompt_loader
        self._finding_repo = finding_repo
        self._remediation_repo = remediation_repo
        self._threshold = threshold
        self._max_explanation_length = max_explanation_length
        self._llm_timeout = llm_timeout

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    async def generate_findings(
        self,
        risk_result: RiskScoreResult,
        change_analysis: ChangeAnalysisResult,
        service_context: dict[str, Any],
    ) -> list[RiskFinding]:
        """Generate RiskFinding objects for a release risk assessment.

        Args:
            risk_result:     Output of RiskScorer.score().
            change_analysis: Output of ChangeAnalyzer.analyze().
            service_context: Dict with keys: service_id, assessment_id, service_name.

        Returns:
            List of RiskFinding objects (empty if all scores are below threshold).
        """
        service_id = str(service_context.get("service_id", ""))
        assessment_id = str(service_context.get("assessment_id", ""))
        service_name = str(service_context.get("service_name", "unknown"))

        candidates = self._collect_candidates(risk_result)
        candidates = self._deduplicate(candidates)

        if not candidates:
            logger.info("explanation_generator.no_findings", threshold=self._threshold)
            return []

        tasks = [
            self._generate_one(c, service_name, assessment_id, service_id)
            for c in candidates
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        findings: list[RiskFinding] = []
        for r in results:
            if isinstance(r, RiskFinding):
                findings.append(r)
            else:
                logger.warning(
                    "explanation_generator.finding_failed",
                    error=str(r),
                )

        # Persist if repositories are available
        if self._finding_repo and assessment_id and service_id:
            findings = await self._persist(findings, assessment_id, service_id)

        logger.info(
            "explanation_generator.complete",
            total_findings=len(findings),
            threshold=self._threshold,
        )
        return findings

    # ------------------------------------------------------------------
    # Candidate collection
    # ------------------------------------------------------------------

    def _collect_candidates(self, risk_result: RiskScoreResult) -> list[_FindingCandidate]:
        candidates: list[_FindingCandidate] = []

        # Dimension-level candidates
        for dim, score in risk_result.dimension_scores.items():
            if score > self._threshold:
                severity = _score_to_severity(score)
                dim_label = dim.replace("_", " ").title()
                candidates.append(
                    _FindingCandidate(
                        dimension=dim,
                        primary_metric="dimension_overall",
                        score=score,
                        metric_name="risk_score",
                        metric_value=float(score),
                        threshold=float(self._threshold),
                        severity=severity,
                        title=f"{dim_label} Risk: {severity.upper()} ({score}/100)",
                    )
                )

        # Contributing factor candidates (top N only)
        for factor in risk_result.contributing_factors[:_TOP_FACTORS]:
            if factor.risk_contribution <= 0:
                continue
            dim_score = risk_result.dimension_scores.get(factor.dimension, 50)
            severity = _score_to_severity(dim_score)
            metric_label = factor.metric_name.replace("_", " ").title()
            dim_label = factor.dimension.replace("_", " ")
            candidates.append(
                _FindingCandidate(
                    dimension=factor.dimension,
                    primary_metric=factor.metric_name,
                    score=dim_score,
                    metric_name=factor.metric_name,
                    metric_value=factor.actual_value,
                    threshold=factor.threshold,
                    severity=severity,
                    title=f"{metric_label} exceeds threshold in {dim_label}",
                )
            )

        return candidates

    # ------------------------------------------------------------------
    # Deduplication
    # ------------------------------------------------------------------

    def _deduplicate(self, candidates: list[_FindingCandidate]) -> list[_FindingCandidate]:
        # Pass 1: group by (dimension, primary_metric) — keep highest severity
        by_dim_metric: dict[tuple[str, str], _FindingCandidate] = {}
        for c in candidates:
            key = (c.dimension, c.primary_metric)
            existing = by_dim_metric.get(key)
            if existing is None or _SEVERITY_RANK[c.severity] > _SEVERITY_RANK[existing.severity]:
                by_dim_metric[key] = c

        # Pass 2: group by primary_metric across dimensions — same metric, higher severity wins
        standalone: list[_FindingCandidate] = []
        by_metric: dict[str, _FindingCandidate] = {}
        for c in by_dim_metric.values():
            if c.primary_metric == "dimension_overall":
                standalone.append(c)
            else:
                existing = by_metric.get(c.primary_metric)
                if (
                    existing is None
                    or _SEVERITY_RANK[c.severity] > _SEVERITY_RANK[existing.severity]
                ):
                    by_metric[c.primary_metric] = c

        return standalone + list(by_metric.values())

    # ------------------------------------------------------------------
    # Single finding generation
    # ------------------------------------------------------------------

    async def _generate_one(
        self,
        candidate: _FindingCandidate,
        service_name: str,
        assessment_id: str,
        service_id: str,
    ) -> RiskFinding:
        start = time.monotonic()
        vars_: dict[str, Any] = {
            "service_name": service_name,
            "dimension": candidate.dimension,
            "score": candidate.score,
            "severity": candidate.severity,
            "metric_name": candidate.metric_name,
            "metric_value": candidate.metric_value,
            "threshold": candidate.threshold,
            "title": candidate.title,
        }

        (
            explanation,
            business_impact,
            remediation_steps,
            source,
            confidence_score,
        ) = await self._call_llm_or_fallback(candidate, vars_)

        latency_ms = int((time.monotonic() - start) * 1000)
        logger.info(
            "explanation_generator.finding_generated",
            dimension=candidate.dimension,
            severity=candidate.severity,
            source=source.value,
            confidence_score=confidence_score,
            latency_ms=latency_ms,
        )

        return RiskFinding(
            assessment_id=assessment_id,
            service_id=service_id,
            title=candidate.title[:500],
            severity=RiskSeverity(candidate.severity),
            dimension=_to_risk_dimension(candidate.dimension),
            explanation=explanation,
            business_impact=business_impact,
            remediation_steps=remediation_steps,
            evidence={
                "metric_name": candidate.metric_name,
                "metric_value": candidate.metric_value,
                "threshold": candidate.threshold,
                "dimension_score": candidate.score,
            },
            confidence_score=confidence_score,
            source=source,
        )

    async def _call_llm_or_fallback(
        self,
        candidate: _FindingCandidate,
        vars_: dict[str, Any],
    ) -> tuple[str, str, list[str], FindingSource, float]:
        prompt = self._prompt_loader.render("risk_explanation", vars_)
        try:
            response = await asyncio.wait_for(
                self._ai_engine.generate_completion(
                    prompt,
                    {
                        "finding_type": candidate.primary_metric,
                        "dimension": candidate.dimension,
                        "severity": candidate.severity,
                    },
                ),
                timeout=self._llm_timeout,
            )
            return self._parse_llm_response(response, candidate, vars_)

        except asyncio.TimeoutError:
            logger.warning(
                "explanation_generator.llm_timeout",
                dimension=candidate.dimension,
                timeout=self._llm_timeout,
            )
        except Exception as exc:
            logger.warning(
                "explanation_generator.llm_error",
                dimension=candidate.dimension,
                error=str(exc),
            )

        return self._build_template_response(vars_)

    def _parse_llm_response(
        self,
        response: Any,
        candidate: _FindingCandidate,
        vars_: dict[str, Any],
    ) -> tuple[str, str, list[str], FindingSource, float]:
        content = response.content
        try:
            parsed = json.loads(content)
            explanation = str(parsed.get("explanation", content))[: self._max_explanation_length]
            business_impact = str(parsed.get("business_impact", ""))[: self._max_explanation_length]
            raw_steps = parsed.get("remediation_steps", [])
            remediation_steps = [str(s) for s in raw_steps if s]
            if not remediation_steps:
                remediation_steps = self._fallback_remediation_steps(vars_)
        except (json.JSONDecodeError, AttributeError, TypeError):
            logger.warning(
                "explanation_generator.non_json_response",
                dimension=candidate.dimension,
            )
            # Use raw text as explanation; fall back to templates for other fields
            explanation = str(content)[: self._max_explanation_length]
            business_impact = self._prompt_loader.render("business_impact", vars_)[
                : self._max_explanation_length
            ]
            remediation_steps = self._fallback_remediation_steps(vars_)

        source = (
            FindingSource.AI_GENERATED
            if response.source in (ResponseSource.AI_GENERATED, ResponseSource.AI_GENERATED_CACHED)
            else FindingSource.TEMPLATE_GENERATED
        )
        return explanation, business_impact, remediation_steps, source, response.confidence_score

    def _build_template_response(
        self,
        vars_: dict[str, Any],
    ) -> tuple[str, str, list[str], FindingSource, float]:
        explanation = self._prompt_loader.render("risk_explanation", vars_)[
            : self._max_explanation_length
        ]
        business_impact = self._prompt_loader.render("business_impact", vars_)[
            : self._max_explanation_length
        ]
        remediation_steps = self._fallback_remediation_steps(vars_)
        return explanation, business_impact, remediation_steps, FindingSource.TEMPLATE_GENERATED, _TEMPLATE_CONFIDENCE

    def _fallback_remediation_steps(self, vars_: dict[str, Any]) -> list[str]:
        text = self._prompt_loader.render("remediation", vars_)
        lines = [line.strip() for line in text.strip().splitlines() if line.strip()]
        return lines[:5] if lines else [
            f"Review {vars_.get('dimension', 'this dimension')} issues before deployment."
        ]

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    async def _persist(
        self,
        findings: list[RiskFinding],
        assessment_id: str,
        service_id: str,
    ) -> list[RiskFinding]:
        persisted: list[RiskFinding] = []
        for finding in findings:
            try:
                row = await self._finding_repo.create(  # type: ignore[union-attr]
                    {
                        "id": finding.id,
                        "assessment_id": assessment_id,
                        "service_id": service_id,
                        "severity": finding.severity.value,
                        "dimension": finding.dimension.value,
                        "status": "open",
                        "title": finding.title[:500],
                        "description": finding.explanation[:4096],
                        "evidence": finding.evidence,
                        "ai_explanation": {
                            "explanation": finding.explanation,
                            "business_impact": finding.business_impact,
                            "remediation_steps": finding.remediation_steps,
                        },
                        "confidence_score": round(finding.confidence_score, 2),
                    }
                )
                finding = finding.model_copy(update={"id": str(row["id"])})

                if self._remediation_repo:
                    await self._remediation_repo.create(
                        {
                            "finding_id": str(row["id"]),
                            "recommendation_text": "\n".join(finding.remediation_steps),
                            "implementation_guide": finding.business_impact[:4096],
                            "confidence_score": round(finding.confidence_score, 2),
                            "source": (
                                "ai_generated"
                                if finding.source == FindingSource.AI_GENERATED
                                else "template_fallback"
                            ),
                        }
                    )
                persisted.append(finding)
            except Exception as exc:
                logger.error(
                    "explanation_generator.persist_failed",
                    finding_title=finding.title,
                    error=str(exc),
                )
                persisted.append(finding)  # Return the in-memory finding even if DB fails

        return persisted
