"""AssessmentOrchestrator: coordinates the full health assessment pipeline (WO-042).

Pipeline order (per architecture spec):
    1. load_active_rules      — PolicyRepository.list_active_rules(service_id)
    2. collect_data           — DataCollector.collect(service_id)
    3. evaluate_rules         — RuleEvaluationEngine.evaluate_rules(rules, input_data)
    4. calculate_dim_scores   — DimensionScoreCalculator.calculate_dimension_scores(results)
    5. aggregate_health_score — HealthScoreAggregator.aggregate(dim_scores, weights, …)
    6. generate_findings      — FindingGenerator.generate_findings(results, assessment_id, service_id)
    7. persist_score          — ScoreRepository.save_health_score(health_result, …)
    8. update_assessment      — AssessmentRepository.update_status(assessment_id, 'completed')
    9. audit_log              — AuditService.log_event(action='assessment.trigger', …)

Lifecycle:
    - On entry: create assessment record with status='pending'.
    - Before pipeline: set status='in_progress' + started_at.
    - On success: set status='completed' + completed_at.
    - On any pipeline exception: set status='failed' + error_details; re-raise.

No policies configured:
    - Returns AssessmentResult with overall_score=None and a message.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Optional, SimpleNamespace

import structlog

from forgeguard.data.repositories.assessment_repository import AssessmentRepository
from forgeguard.data.repositories.findings import FindingRepository
from forgeguard.data.repositories.policies import PolicyRepository
from forgeguard.data.repositories.scores import ScoreRepository
from forgeguard.services.audit import AuditService
from forgeguard.services.dimension_scorer import DimensionScoreCalculator
from forgeguard.services.domain.scoring import DimensionScore
from forgeguard.services.evaluation_engine import RuleEvaluationEngine
from forgeguard.services.finding_generator import FindingGenerator
from forgeguard.services.health_score_aggregator import DEFAULT_WEIGHTS, HealthScoreAggregator
from forgeguard.services.interfaces.data_collector import DataCollector

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------

@dataclass
class AssessmentResult:
    """Structured result returned by AssessmentOrchestrator.run()."""

    assessment_id: uuid.UUID
    status: str
    overall_score: Optional[Decimal]
    dimension_scores: dict[str, DimensionScore]
    finding_counts: dict[str, int]
    evaluated_at: datetime
    message: Optional[str] = None
    findings: list[dict[str, Any]] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Rule adapter
# ---------------------------------------------------------------------------

def _make_rule_obj(rule_dict: dict[str, Any]) -> Any:
    """Wrap a rule dict in a SimpleNamespace so the evaluation engine can use
    attribute access (rule.id, rule.name, rule.severity, etc.).

    The evaluator's _get_dimension() call needs rule.policy.dimension, which
    is the JOIN-projected 'dimension' column from the query in list_active_rules.
    """
    policy_ns = SimpleNamespace(dimension=rule_dict.get("dimension", "unknown"))
    rule = SimpleNamespace(
        id=rule_dict["id"],
        name=rule_dict["name"],
        severity=rule_dict["severity"],
        rule_type=rule_dict["rule_type"],
        threshold_config=rule_dict.get("threshold_config") or {},
        weight=rule_dict.get("weight"),
        policy=policy_ns,
    )
    return rule


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

class AssessmentOrchestrator:
    """Coordinates the full health assessment pipeline.

    Designed for synchronous (in-request) execution.  All dependencies are
    injected so the class is trivially testable with mock objects.
    """

    def __init__(
        self,
        assessment_repo: AssessmentRepository,
        policy_repo: PolicyRepository,
        score_repo: ScoreRepository,
        finding_repo: FindingRepository,
        data_collector: DataCollector,
        audit_svc: AuditService,
        evaluation_engine: RuleEvaluationEngine | None = None,
        dim_scorer: DimensionScoreCalculator | None = None,
        health_aggregator: HealthScoreAggregator | None = None,
    ) -> None:
        self._assessments = assessment_repo
        self._policies = policy_repo
        self._scores = score_repo
        self._findings = finding_repo
        self._collector = data_collector
        self._audit = audit_svc
        self._engine = evaluation_engine or RuleEvaluationEngine()
        self._dim_scorer = dim_scorer or DimensionScoreCalculator()
        self._aggregator = health_aggregator or HealthScoreAggregator()

    async def run(
        self,
        service_id: uuid.UUID,
        *,
        actor_id: str | None = None,
        actor_role: str = "developer",
        trigger_type: str = "manual",
        correlation_id: str | None = None,
    ) -> AssessmentResult:
        """Execute the full health assessment pipeline for *service_id*.

        Args:
            service_id:      UUID of the service to assess.
            actor_id:        UUID of the requesting user (for audit log).
            actor_role:      Role of the requesting user.
            trigger_type:    'manual' | 'scheduled' | 'webhook'.
            correlation_id:  HTTP request correlation ID.

        Returns:
            :class:`AssessmentResult` with scores and finding counts.

        Raises:
            Exception: Any unhandled pipeline error after marking assessment failed.
        """
        assessment_id = uuid.uuid4()
        now = datetime.now(tz=timezone.utc)

        # ── Step 0: create assessment record ─────────────────────────────────
        await self._assessments.create({
            "id": assessment_id,
            "service_id": service_id,
            "assessment_type": "health_check",
            "trigger_type": trigger_type,
            "triggered_by": uuid.UUID(actor_id) if actor_id else None,
            "status": "pending",
            "started_at": now,
        })

        # ── Step 1: set in_progress ───────────────────────────────────────────
        await self._assessments.update_status(
            assessment_id,
            "in_progress",
            started_at=now,
        )

        try:
            result = await self._run_pipeline(
                assessment_id=assessment_id,
                service_id=service_id,
                trigger_type=trigger_type,
            )
        except Exception as exc:
            error_details: dict[str, Any] = {
                "error_type": type(exc).__name__,
                "error_message": str(exc)[:500],
            }
            await self._assessments.update_status(
                assessment_id,
                "failed",
                completed_at=datetime.now(tz=timezone.utc),
                error_details=error_details,
            )
            logger.error(
                "assessment_orchestrator.pipeline_failed",
                assessment_id=str(assessment_id),
                service_id=str(service_id),
                error=str(exc),
            )
            raise

        # ── Final audit record ────────────────────────────────────────────────
        await self._emit_audit(
            assessment_id=assessment_id,
            service_id=service_id,
            actor_id=actor_id,
            actor_role=actor_role,
            result=result,
            correlation_id=correlation_id,
        )

        return result

    # ------------------------------------------------------------------
    # Private: pipeline
    # ------------------------------------------------------------------

    async def _run_pipeline(
        self,
        assessment_id: uuid.UUID,
        service_id: uuid.UUID,
        trigger_type: str,
    ) -> AssessmentResult:
        evaluated_at = datetime.now(tz=timezone.utc)

        # ── Step 1: load active policy rules ─────────────────────────────────
        rule_dicts = await self._policies.list_active_rules(service_id)

        if not rule_dicts:
            await self._assessments.update_status(
                assessment_id,
                "completed",
                completed_at=datetime.now(tz=timezone.utc),
            )
            logger.info(
                "assessment_orchestrator.no_policies",
                assessment_id=str(assessment_id),
                service_id=str(service_id),
            )
            return AssessmentResult(
                assessment_id=assessment_id,
                status="completed",
                overall_score=None,
                dimension_scores={},
                finding_counts={},
                evaluated_at=evaluated_at,
                message="No active policies configured for this service.",
                findings=[],
            )

        rules = [_make_rule_obj(r) for r in rule_dicts]

        # ── Step 2: collect input data ────────────────────────────────────────
        input_data = await self._collector.collect(service_id)

        # ── Step 3: evaluate rules ────────────────────────────────────────────
        eval_results = await self._engine.evaluate_rules(rules, input_data)

        # ── Step 4: calculate dimension scores ───────────────────────────────
        dimension_scores = self._dim_scorer.calculate_dimension_scores(eval_results)

        # ── Step 5: aggregate health score ────────────────────────────────────
        health_result = self._aggregator.aggregate(
            dimension_scores=dimension_scores,
            weights=DEFAULT_WEIGHTS,
            assessment_id=assessment_id,
            service_id=service_id,
        )

        # ── Step 6: generate findings ─────────────────────────────────────────
        finding_gen = FindingGenerator(self._findings)
        findings = await finding_gen.generate_findings(
            results=eval_results,
            assessment_id=assessment_id,
            service_id=service_id,
        )

        # ── Step 7: persist score ─────────────────────────────────────────────
        await self._scores.save_health_score(
            result=health_result,
            assessment_id=assessment_id,
            service_id=service_id,
        )

        # ── Step 8: mark completed ────────────────────────────────────────────
        await self._assessments.update_status(
            assessment_id,
            "completed",
            completed_at=datetime.now(tz=timezone.utc),
        )

        # ── Build finding counts ──────────────────────────────────────────────
        finding_counts = await self._findings.count_by_severity(service_id)

        logger.info(
            "assessment_orchestrator.completed",
            assessment_id=str(assessment_id),
            service_id=str(service_id),
            overall_score=str(health_result.overall_score),
            findings_count=len(findings),
        )

        return AssessmentResult(
            assessment_id=assessment_id,
            status="completed",
            overall_score=health_result.overall_score,
            dimension_scores=dimension_scores,
            finding_counts=finding_counts,
            evaluated_at=evaluated_at,
            message=None,
            findings=findings,
        )

    async def _emit_audit(
        self,
        assessment_id: uuid.UUID,
        service_id: uuid.UUID,
        actor_id: str | None,
        actor_role: str,
        result: AssessmentResult,
        correlation_id: str | None,
    ) -> None:
        try:
            await self._audit.log_event(
                actor_id=actor_id,
                actor_role=actor_role,
                action="assessment.trigger",
                resource_type="service",
                resource_id=service_id,
                after_state={
                    "assessment_id": str(assessment_id),
                    "status": result.status,
                    "overall_score": str(result.overall_score) if result.overall_score is not None else None,
                    "finding_count": sum(result.finding_counts.values()),
                },
                correlation_id=correlation_id,
            )
        except Exception as exc:
            logger.error(
                "assessment_orchestrator.audit_failed",
                assessment_id=str(assessment_id),
                error=str(exc),
            )
