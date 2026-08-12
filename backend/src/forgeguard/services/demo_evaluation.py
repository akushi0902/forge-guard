"""DemoEvaluationService: orchestrates the full governance evaluation pipeline (WO-056).

Pipeline steps:
    1. Load Payment Service from SERVICES table (is_demo=True)
    2. Collect mock data via MockDataCollector
    3. Load active policy rules from POLICY_RULES
    4. Evaluate each rule against collected_data using RuleEvaluationEngine
    5. Generate Finding records for failed rules
    6. Calculate dimension scores and overall Health Score
    7. Generate AI explanations with circuit breaker + template fallback
    8. Generate remediation recommendations with circuit breaker + template fallback
    9. Persist ASSESSMENTS, ASSESSMENT_SCORES, FINDINGS, REMEDIATION_RECOMMENDATIONS
    10. Write AUDIT_LOGS record
    11. Return assembled DemoEvaluationResponse
"""

from __future__ import annotations

import json
import time
import uuid
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from types import SimpleNamespace
from typing import Any

import structlog

from forgeguard.api.schemas.demo_evaluation import (
    ContributingFactor,
    DemoEvaluationResponse,
    DimensionScores,
    EvaluationSummary,
    FindingDetail,
    HealthScoreBreakdown,
    RemediationDetail,
    SeverityBreakdown,
)
from forgeguard.services.ai_engine.errors import CircuitOpenError
from forgeguard.services.domain.evaluation import EvaluationStatus
from forgeguard.services.templates.demo_explanations import get_explanation

logger = structlog.get_logger(__name__)

_PAYMENT_SERVICE_ID = uuid.UUID("d0000000-0000-0000-0000-000000000001")

_DIMENSION_WEIGHTS: dict[str, Decimal] = {
    "code_quality": Decimal("20"),
    "test_coverage": Decimal("20"),
    "security": Decimal("20"),
    "documentation": Decimal("20"),
    "operations_readiness": Decimal("20"),
}

_SEVERITY_ORDER = ("critical", "high", "medium", "low")


def _quantize(value: Decimal) -> float:
    return float(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


class _PolicyRef:
    """Stub that exposes `.dimension` so evaluators can call `rule.policy.dimension`."""

    __slots__ = ("dimension",)

    def __init__(self, dimension: str) -> None:
        self.dimension = dimension


class _RuleAdapter:
    """Adapts a policy_rule dict row to the duck-typed interface the evaluators expect."""

    __slots__ = ("id", "name", "rule_type", "threshold_config", "severity", "weight", "policy")

    def __init__(self, row: dict[str, Any]) -> None:
        self.id = row["id"]
        self.name = row["name"]
        self.rule_type = row["rule_type"]
        config = row.get("threshold_config", {})
        self.threshold_config = json.loads(config) if isinstance(config, str) else (config or {})
        self.severity = row["severity"]
        w = row.get("weight")
        self.weight = Decimal(str(w)) if w is not None else Decimal("1")
        self.policy = _PolicyRef(row.get("dimension", "unknown"))


def _dimension_scores_from_results(
    results: list[Any],
) -> tuple[dict[str, float | None], list[ContributingFactor]]:
    """Calculate per-dimension scores from rule evaluation results.

    Score per dimension = (sum of passing weights) / (sum of all weights) * 100.
    A dimension with no rules scores None.
    """
    dim_total: dict[str, Decimal] = {}
    dim_passing: dict[str, Decimal] = {}
    factors: list[ContributingFactor] = []

    for r in results:
        dim = r.dimension if r.dimension != "unknown" else "code_quality"
        if dim not in dim_total:
            dim_total[dim] = Decimal("0")
            dim_passing[dim] = Decimal("0")
        w = r.weight if isinstance(r.weight, Decimal) else Decimal(str(r.weight))
        dim_total[dim] += w
        passed = r.status == EvaluationStatus.PASS
        if passed:
            dim_passing[dim] += w
        impact = _quantize(w * Decimal("100") / dim_total[dim]) if dim_total[dim] else 0.0
        factors.append(ContributingFactor(
            rule_name=r.rule_name,
            dimension=dim,
            passed=passed,
            weight=float(w),
            impact=impact,
        ))

    scores: dict[str, float | None] = {}
    for dim in _DIMENSION_WEIGHTS:
        total = dim_total.get(dim, Decimal("0"))
        if total == Decimal("0"):
            scores[dim] = None
        else:
            scores[dim] = _quantize(dim_passing[dim] / total * Decimal("100"))

    # Recalculate impacts now that final dim_total is known
    for f in factors:
        t = dim_total.get(f.dimension, Decimal("0"))
        if t:
            f.impact = _quantize(Decimal(str(f.weight)) / t * Decimal("100"))

    return scores, factors


def _overall_score_from_dimensions(scores: dict[str, float | None]) -> float:
    """Weighted average of active dimension scores."""
    total_weight = Decimal("0")
    weighted_sum = Decimal("0")
    for dim, score in scores.items():
        if score is None:
            continue
        w = _DIMENSION_WEIGHTS.get(dim, Decimal("20"))
        total_weight += w
        weighted_sum += Decimal(str(score)) * w
    if total_weight == Decimal("0"):
        return 0.0
    return _quantize(weighted_sum / total_weight)


def _severity_breakdown(findings: list[FindingDetail]) -> SeverityBreakdown:
    counts: dict[str, int] = {s: 0 for s in _SEVERITY_ORDER}
    for f in findings:
        sev = f.severity.lower()
        if sev in counts:
            counts[sev] += 1
    return SeverityBreakdown(
        critical=counts["critical"],
        high=counts["high"],
        medium=counts["medium"],
        low=counts["low"],
    )


class DemoEvaluationService:
    """Orchestrates the full governance evaluation pipeline for the demo Payment Service.

    All dependencies are injected via the constructor so tests can mock them.
    """

    def __init__(
        self,
        *,
        policy_repo: Any,
        service_repo: Any,
        assessment_repo: Any,
        score_repo: Any,
        finding_repo: Any,
        remediation_repo: Any,
        audit_repo: Any,
        ai_engine: Any,
        data_collector: Any,
        evaluation_engine: Any,
    ) -> None:
        self._policy_repo = policy_repo
        self._service_repo = service_repo
        self._assessment_repo = assessment_repo
        self._score_repo = score_repo
        self._finding_repo = finding_repo
        self._remediation_repo = remediation_repo
        self._audit_repo = audit_repo
        self._ai_engine = ai_engine
        self._data_collector = data_collector
        self._evaluation_engine = evaluation_engine

    async def evaluate_payment_service(self, *, actor_role: str) -> DemoEvaluationResponse:
        """Run the full evaluation pipeline and return the assembled response."""
        start_ms = time.monotonic()

        # ── Step 1: Load Payment Service ──────────────────────────────────────
        service = await self._service_repo.get_by_id(_PAYMENT_SERVICE_ID)
        if service is None:
            from fastapi import HTTPException  # noqa: PLC0415
            raise HTTPException(
                status_code=404,
                detail={
                    "detail": (
                        "ForgeGuard Payment Service not found. "
                        "Ensure demo seed data has been loaded."
                    ),
                    "error_code": "DEMO_SERVICE_NOT_FOUND",
                },
            )

        service_id = service["id"]
        service_name = service.get("name", "Payment Service")

        # ── Step 2: Collect mock data ──────────────────────────────────────────
        collected_data = await self._data_collector.collect(service_id)

        # ── Step 3: Load active policy rules ──────────────────────────────────
        rule_rows = await self._policy_repo.list_active_rules(service_id)
        if not rule_rows:
            from fastapi import HTTPException  # noqa: PLC0415
            raise HTTPException(
                status_code=422,
                detail={
                    "detail": (
                        "No policy rules configured for evaluation. "
                        "Ensure violation seed data has been loaded."
                    ),
                    "error_code": "NO_POLICY_RULES",
                },
            )

        rules = [_RuleAdapter(r) for r in rule_rows]

        # ── Step 4: Evaluate rules ─────────────────────────────────────────────
        eval_results = await self._evaluation_engine.evaluate_rules(rules, collected_data)

        # ── Step 5: Identify failed rules (violations) ─────────────────────────
        failed_results = [r for r in eval_results if r.status == EvaluationStatus.FAIL]

        # ── Step 6: Calculate dimension scores and overall Health Score ────────
        dim_scores, contributing_factors = _dimension_scores_from_results(eval_results)
        overall = _overall_score_from_dimensions(dim_scores)

        # ── Step 7 & 8: Generate findings with AI explanations + remediation ───
        findings: list[FindingDetail] = []
        for r in failed_results:
            data_key = None
            # Recover the data_key from the rule's threshold_config for template lookup
            if hasattr(r, "evidence") and isinstance(r.evidence, dict):
                data_key = r.evidence.get("data_key")
            if data_key is None:
                # Find matching rule adapter to read threshold_config
                for rule in rules:
                    if rule.id == r.rule_id:
                        data_key = rule.threshold_config.get("data_key")
                        break

            tpl = get_explanation(data_key, r.dimension)

            explanation = await self._generate_explanation(
                rule_name=r.rule_name,
                dimension=r.dimension,
                severity=r.severity.value if hasattr(r.severity, "value") else str(r.severity),
                evidence=r.evidence,
                fallback_text=tpl["explanation"],
            )

            remediation = await self._generate_remediation(
                rule_name=r.rule_name,
                dimension=r.dimension,
                fallback_recommendation=tpl["recommendation"],
                fallback_guide=tpl["implementation_guide"],
            )

            severity_str = r.severity.value if hasattr(r.severity, "value") else str(r.severity)
            findings.append(FindingDetail(
                id=uuid.uuid4(),
                severity=severity_str,
                dimension=r.dimension,
                title=f"Policy violation: {r.rule_name}",
                description=(
                    f"Rule '{r.rule_name}' failed evaluation. "
                    f"Actual value: {r.actual_value}, expected: {r.expected_value}."
                ),
                evidence=r.evidence,
                ai_explanation=explanation["text"],
                confidence_score=explanation["confidence"],
                remediation=remediation,
            ))

        # ── Step 9: Persist to database (best-effort — don't fail response) ───
        assessment_id = uuid.uuid4()
        persistence_warning = None
        try:
            assessment_id = await self._persist_results(
                service_id=service_id,
                collected_data=collected_data,
                overall_score=overall,
                dim_scores=dim_scores,
                contributing_factors=contributing_factors,
                findings=findings,
                eval_results=eval_results,
            )
        except Exception as exc:  # noqa: BLE001
            persistence_warning = str(exc)
            logger.error(
                "demo_evaluation.persistence_failed",
                service_id=str(service_id),
                error=persistence_warning,
            )

        # ── Step 10: Write audit log ───────────────────────────────────────────
        try:
            await self._audit_repo.insert({
                "id": uuid.uuid4(),
                "actor_role": actor_role,
                "action": "demo_evaluation_triggered",
                "resource_type": "service",
                "resource_id": service_id,
                "after_state": json.dumps({
                    "assessment_id": str(assessment_id),
                    "overall_score": float(overall),
                    "finding_count": len(findings),
                }),
            })
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "demo_evaluation.audit_log_failed",
                service_id=str(service_id),
                error=str(exc),
            )

        # ── Step 11: Assemble response ─────────────────────────────────────────
        elapsed_ms = int((time.monotonic() - start_ms) * 1000)
        evaluated_at = datetime.now(tz=timezone.utc)

        severity_counts = _severity_breakdown(findings)

        return DemoEvaluationResponse(
            assessment_id=assessment_id,
            service_id=service_id,
            service_name=service_name,
            is_simulated=True,
            health_score=HealthScoreBreakdown(
                overall=overall,
                dimensions=DimensionScores(
                    code_quality=dim_scores.get("code_quality"),
                    test_coverage=dim_scores.get("test_coverage"),
                    security=dim_scores.get("security"),
                    documentation=dim_scores.get("documentation"),
                    operations_readiness=dim_scores.get("operations_readiness"),
                ),
                contributing_factors=contributing_factors,
            ),
            findings=findings,
            summary=EvaluationSummary(
                total_findings=len(findings),
                by_severity=severity_counts,
                evaluated_at=evaluated_at,
                evaluation_duration_ms=elapsed_ms,
            ),
        )

    # ── Private helpers ────────────────────────────────────────────────────────

    async def _generate_explanation(
        self,
        *,
        rule_name: str,
        dimension: str,
        severity: str,
        evidence: dict[str, Any],
        fallback_text: str,
    ) -> dict[str, Any]:
        """Generate an AI explanation, falling back to templates on failure."""
        prompt = (
            f"Explain this governance policy violation in 2-3 sentences for an engineering team:\n"
            f"Rule: {rule_name}\nDimension: {dimension}\nSeverity: {severity}\n"
            f"Evidence: {json.dumps(evidence, default=str)}"
        )
        try:
            resp = await self._ai_engine.generate_completion(
                prompt,
                params={"dimension": dimension, "severity": severity, "finding_type": rule_name},
            )
            return {"text": resp.content, "confidence": float(resp.confidence_score)}
        except (CircuitOpenError, Exception) as exc:  # noqa: BLE001
            logger.warning(
                "demo_evaluation.ai_explanation_fallback",
                rule_name=rule_name,
                error=str(exc),
            )
            return {"text": fallback_text, "confidence": 0.70}

    async def _generate_remediation(
        self,
        *,
        rule_name: str,
        dimension: str,
        fallback_recommendation: str,
        fallback_guide: str,
    ) -> RemediationDetail:
        """Generate a remediation recommendation, falling back to templates on failure."""
        prompt = (
            f"Provide a concise remediation recommendation for this governance violation:\n"
            f"Rule: {rule_name}\nDimension: {dimension}\n"
            "Format as: <one sentence recommendation>\\n<numbered implementation steps>"
        )
        try:
            resp = await self._ai_engine.generate_completion(
                prompt,
                params={"dimension": dimension, "finding_type": rule_name},
            )
            lines = resp.content.strip().splitlines()
            recommendation_text = lines[0] if lines else fallback_recommendation
            guide = "\n".join(lines[1:]).strip() if len(lines) > 1 else fallback_guide
            return RemediationDetail(
                recommendation_text=recommendation_text,
                implementation_guide=guide,
                confidence_score=float(resp.confidence_score),
                source="ai",
            )
        except (CircuitOpenError, Exception) as exc:  # noqa: BLE001
            logger.warning(
                "demo_evaluation.ai_remediation_fallback",
                rule_name=rule_name,
                error=str(exc),
            )
            return RemediationDetail(
                recommendation_text=fallback_recommendation,
                implementation_guide=fallback_guide,
                confidence_score=0.70,
                source="template",
            )

    async def _persist_results(
        self,
        *,
        service_id: uuid.UUID,
        collected_data: dict[str, Any],
        overall_score: float,
        dim_scores: dict[str, float | None],
        contributing_factors: list[ContributingFactor],
        findings: list[FindingDetail],
        eval_results: list[Any],
    ) -> uuid.UUID:
        """Persist assessment, scores, findings, and recommendations to the database."""
        assessment_id = uuid.uuid4()
        now = datetime.now(tz=timezone.utc)

        # ASSESSMENTS record
        await self._assessment_repo.create({
            "id": assessment_id,
            "service_id": service_id,
            "assessment_type": "health",
            "trigger_type": "demo",
            "status": "completed",
            "collected_data": json.dumps(collected_data),
            "started_at": now,
            "completed_at": now,
        })

        # ASSESSMENT_SCORES record
        dimension_scores_payload: dict[str, Any] = {}
        for dim, score in dim_scores.items():
            dimension_scores_payload[dim] = {
                "dimension": dim,
                "score": score,
                "has_data": score is not None,
            }
        contributing_factors_payload = [
            {
                "rule_name": f.rule_name,
                "dimension": f.dimension,
                "passed": f.passed,
                "weight": f.weight,
                "impact": f.impact,
            }
            for f in contributing_factors
        ]
        await self._score_repo.create({
            "id": uuid.uuid4(),
            "assessment_id": assessment_id,
            "service_id": service_id,
            "score_type": "health",
            "overall_score": Decimal(str(overall_score)),
            "dimension_scores": json.dumps(dimension_scores_payload),
            "contributing_factors": json.dumps(contributing_factors_payload),
        })

        # FINDINGS + REMEDIATION_RECOMMENDATIONS records
        for finding in findings:
            finding_row = await self._finding_repo.create({
                "id": finding.id,
                "assessment_id": assessment_id,
                "service_id": service_id,
                "severity": finding.severity,
                "dimension": finding.dimension,
                "status": "open",
                "title": finding.title,
                "description": finding.description,
                "evidence": json.dumps(finding.evidence),
                "ai_explanation": finding.ai_explanation,
                "confidence_score": Decimal(str(finding.confidence_score)),
            })

            await self._remediation_repo.create({
                "id": uuid.uuid4(),
                "finding_id": finding.id,
                "recommendation_text": finding.remediation.recommendation_text,
                "implementation_guide": finding.remediation.implementation_guide,
                "confidence_score": Decimal(str(finding.remediation.confidence_score)),
                "source": finding.remediation.source,
            })

        return assessment_id
