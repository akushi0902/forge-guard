"""ReEvaluationService: finding re-evaluation with before/after comparison (WO-061).

Pipeline:
    1. Load finding — 404 if not found
    2. Guard: exception_granted → 400; remediated → 409
    3. Capture before-state (status + latest health score)
    4. Load all active policy rules for the service
    5. Collect current service data via DataCollector
    6. Evaluate all rules with RuleEvaluationEngine
    7. Determine new finding status from the specific rule's result
    8. Apply update with optimistic locking (version column)
    9. Recalculate health score from all rule results
    10. Persist new ASSESSMENT_SCORES record
    11. If not resolved: generate updated AI guidance
    12. Write AUDIT_LOGS record
    13. Return ReEvaluationResponse
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

import structlog

from forgeguard.api.schemas.remediation import ReEvaluationResponse, RuleResult
from forgeguard.core.exceptions import BadRequestError, ConflictError, NotFoundError
from forgeguard.services.ai_engine.errors import CircuitOpenError
from forgeguard.services.domain.evaluation import EvaluationStatus
from forgeguard.services.domain.finding_status import FindingStatus

logger = structlog.get_logger(__name__)

_TWO_DP = Decimal("0.01")
_DIMENSION_WEIGHTS: dict[str, Decimal] = {
    "code_quality": Decimal("20"),
    "test_coverage": Decimal("20"),
    "security": Decimal("20"),
    "documentation": Decimal("20"),
    "operations_readiness": Decimal("20"),
}


def _quantize(v: Decimal) -> float:
    return float(v.quantize(_TWO_DP, rounding=ROUND_HALF_UP))


class _PolicyRef:
    __slots__ = ("dimension",)
    def __init__(self, dimension: str) -> None:
        self.dimension = dimension


class _RuleAdapter:
    """Adapts a policy_rule dict row to the duck-typed evaluator interface."""
    __slots__ = ("id", "name", "rule_type", "threshold_config", "severity", "weight", "policy")

    def __init__(self, row: dict[str, Any]) -> None:
        self.id = row["id"]
        self.name = row["name"]
        self.rule_type = row["rule_type"]
        cfg = row.get("threshold_config", {})
        self.threshold_config = json.loads(cfg) if isinstance(cfg, str) else (cfg or {})
        self.severity = row["severity"]
        w = row.get("weight")
        self.weight = Decimal(str(w)) if w is not None else Decimal("1")
        self.policy = _PolicyRef(row.get("dimension", "unknown"))


def _compute_overall_score(eval_results: list[Any]) -> float:
    """Weighted-aggregate health score from evaluation results."""
    dim_total: dict[str, Decimal] = {}
    dim_passing: dict[str, Decimal] = {}

    for r in eval_results:
        dim = r.dimension if r.dimension != "unknown" else "code_quality"
        if dim not in dim_total:
            dim_total[dim] = Decimal("0")
            dim_passing[dim] = Decimal("0")
        w = r.weight if isinstance(r.weight, Decimal) else Decimal(str(r.weight))
        dim_total[dim] += w
        if r.status == EvaluationStatus.PASS:
            dim_passing[dim] += w

    dim_scores: dict[str, Decimal] = {}
    for dim in dim_total:
        if dim_total[dim] > Decimal("0"):
            dim_scores[dim] = dim_passing[dim] / dim_total[dim] * Decimal("100")

    active_dims = {d: s for d, s in dim_scores.items()}
    if not active_dims:
        return 0.0

    total_w = Decimal("0")
    weighted_sum = Decimal("0")
    for dim, score in active_dims.items():
        w = _DIMENSION_WEIGHTS.get(dim, Decimal("20"))
        total_w += w
        weighted_sum += score * w

    if total_w == Decimal("0"):
        return 0.0
    return _quantize(weighted_sum / total_w)


class ReEvaluationService:
    """Orchestrates finding re-evaluation with before/after Health Score comparison."""

    def __init__(
        self,
        *,
        finding_repo: Any,
        policy_repo: Any,
        score_repo: Any,
        assessment_repo: Any,
        audit_svc: Any,
        ai_engine: Any,
        evaluation_engine: Any,
        data_collector: Any,
    ) -> None:
        self._findings = finding_repo
        self._policies = policy_repo
        self._scores = score_repo
        self._assessments = assessment_repo
        self._audit = audit_svc
        self._ai = ai_engine
        self._engine = evaluation_engine
        self._collector = data_collector

    async def re_evaluate(
        self,
        finding_id: uuid.UUID,
        *,
        actor_id: str | None = None,
        actor_role: str = "developer",
    ) -> ReEvaluationResponse:
        """Run the full re-evaluation pipeline for a single finding."""

        # ── Step 1: Load finding ──────────────────────────────────────────────
        finding = await self._findings.get_by_id(finding_id)
        if finding is None:
            raise NotFoundError(f"Finding {finding_id} not found.")

        service_id: uuid.UUID = finding["service_id"]
        policy_rule_id: uuid.UUID = finding["policy_rule_id"]
        current_status = finding["status"]
        current_version = finding.get("version", 1)

        # ── Step 2: Status guards ─────────────────────────────────────────────
        if current_status == FindingStatus.EXCEPTION_GRANTED.value:
            raise BadRequestError(
                "Cannot re-evaluate excepted finding — the exception must expire or be "
                "revoked before re-evaluation.",
                details={"error_code": "EXCEPTED_FINDING"},
            )
        if current_status == FindingStatus.REMEDIATED.value:
            raise ConflictError(
                "Finding already resolved — re-evaluation is not needed.",
                details={"error_code": "FINDING_ALREADY_RESOLVED"},
            )

        before_status = current_status

        # ── Step 3: Capture before-state health score ──────────────────────────
        before_score_row = await self._scores.get_latest_health_score(service_id)
        before_health_score: float | None = None
        if before_score_row and before_score_row.get("overall_score") is not None:
            before_health_score = float(before_score_row["overall_score"])

        # ── Steps 4 & 5: Load rules + collect data ────────────────────────────
        rule_rows = await self._policies.list_active_rules(service_id)
        collected_data = await self._collector.collect(service_id)

        # ── Step 6: Evaluate all rules ────────────────────────────────────────
        rules = [_RuleAdapter(r) for r in rule_rows]
        eval_results = await self._engine.evaluate_rules(rules, collected_data)

        # ── Step 7: Find result for the specific rule ─────────────────────────
        specific_result = next(
            (r for r in eval_results if r.rule_id == policy_rule_id), None
        )

        rule_results: list[RuleResult] = []
        if specific_result is not None:
            rule_results = [RuleResult(
                rule_id=specific_result.rule_id,
                rule_name=specific_result.rule_name,
                passed=specific_result.status == EvaluationStatus.PASS,
                actual_value=str(specific_result.actual_value),
                threshold=str(specific_result.expected_value),
            )]

        rule_passed = specific_result is not None and specific_result.status == EvaluationStatus.PASS

        # ── Step 8: Determine new status + apply optimistic lock update ───────
        re_evaluated_at = datetime.now(tz=timezone.utc)
        resolved_at = None

        if rule_passed:
            after_status = FindingStatus.REMEDIATED.value
            resolved_at = re_evaluated_at
        elif current_status in (FindingStatus.OPEN.value, FindingStatus.REOPENED.value):
            after_status = FindingStatus.ACKNOWLEDGED.value
        else:
            after_status = current_status  # already acknowledged — stay there

        update_data: dict[str, Any] = {"status": after_status}
        if resolved_at is not None:
            update_data["resolved_at"] = resolved_at

        updated_finding = await self._findings.update_with_optimistic_lock(
            finding_id, current_version, update_data
        )
        if updated_finding is None:
            raise NotFoundError(f"Finding {finding_id} disappeared during re-evaluation.")

        # ── Step 9 & 10: Recalculate and persist new health score ─────────────
        after_health_score = _compute_overall_score(eval_results)
        new_assessment_id = uuid.uuid4()

        try:
            await self._assessments.create({
                "id": new_assessment_id,
                "service_id": service_id,
                "assessment_type": "health",
                "trigger_type": "re_evaluation",
                "status": "completed",
                "collected_data": json.dumps(collected_data),
                "started_at": re_evaluated_at,
                "completed_at": re_evaluated_at,
            })
            await self._scores.create({
                "id": uuid.uuid4(),
                "assessment_id": new_assessment_id,
                "service_id": service_id,
                "score_type": "health",
                "overall_score": Decimal(str(after_health_score)),
                "dimension_scores": json.dumps({}),
                "contributing_factors": json.dumps([]),
            })
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "reevaluation.score_persist_failed",
                finding_id=str(finding_id),
                error=str(exc),
            )

        # ── Step 11: Generate updated guidance if not resolved ────────────────
        updated_guidance: str | None = None
        if not rule_passed and specific_result is not None:
            updated_guidance = await self._generate_updated_guidance(
                finding=finding,
                eval_result=specific_result,
            )

        # ── Step 12: Write audit record ───────────────────────────────────────
        score_delta = (
            round(after_health_score - before_health_score, 2)
            if before_health_score is not None
            else None
        )
        try:
            await self._audit.log_event(
                actor_id=actor_id,
                actor_role=actor_role,
                action="finding.re_evaluated",
                resource_type="finding",
                resource_id=finding_id,
                before_state={
                    "status": before_status,
                    "health_score": before_health_score,
                },
                after_state={
                    "status": after_status,
                    "health_score": after_health_score,
                    "rule_passed": rule_passed,
                },
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "reevaluation.audit_failed",
                finding_id=str(finding_id),
                error=str(exc),
            )

        # ── Step 13: Assemble response ────────────────────────────────────────
        return ReEvaluationResponse(
            finding_id=finding_id,
            before_health_score=before_health_score,
            after_health_score=after_health_score,
            score_delta=score_delta,
            before_finding_status=before_status,
            after_finding_status=after_status,
            rule_results=rule_results,
            updated_guidance=updated_guidance,
            re_evaluated_at=re_evaluated_at,
        )

    async def _generate_updated_guidance(
        self,
        finding: dict[str, Any],
        eval_result: Any,
    ) -> str | None:
        """Generate updated remediation guidance based on the new evidence."""
        prompt = (
            f"The following policy violation was re-evaluated and still fails. "
            f"Rule: {eval_result.rule_name}, Dimension: {eval_result.dimension}. "
            f"Latest evidence: actual={eval_result.actual_value}, "
            f"threshold={eval_result.expected_value}. "
            f"Provide updated, specific remediation guidance in 2-3 sentences."
        )
        try:
            resp = await self._ai.generate_completion(
                prompt,
                params={
                    "dimension": eval_result.dimension,
                    "finding_type": eval_result.rule_name,
                },
            )
            return resp.content
        except (CircuitOpenError, Exception) as exc:  # noqa: BLE001
            logger.warning(
                "reevaluation.updated_guidance_failed",
                rule_name=eval_result.rule_name,
                error=str(exc),
            )
            return None
