"""Release Assessment REST API endpoints (WO-048).

Routes:
    POST  /api/v1/releases/assess   — request a new release risk assessment
    GET   /api/v1/releases/{id}     — retrieve assessment results
    GET   /api/v1/releases          — list assessments with filtering and cursor pagination

The POST endpoint returns 202 immediately; the full pipeline runs as a
FastAPI BackgroundTask (ChangeAnalyzer → RiskScorer → ExplanationGenerator).
"""

from __future__ import annotations

import asyncio
import json
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

import asyncpg
import structlog
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request
from fastapi.responses import JSONResponse

from forgeguard.api.dependencies.audit import get_audit_service
from forgeguard.api.dependencies.rbac import require_any_permission, require_permission
from forgeguard.api.schemas.releases import (
    ContributingFactorResponse,
    EscalationReasonResponse,
    FindingResponse,
    PaginatedAssessmentResponse,
    ReleaseAssessmentDetailResponse,
    ReleaseAssessmentRequest,
    ReleaseAssessmentResponse,
    ReleaseDecisionCreate,
    ReleaseDecisionRequest,
    ReleaseDecisionResponse,
    RiskScoreResponse,
    decode_cursor,
    encode_cursor,
)
from forgeguard.core.dependencies import (
    get_ai_engine,
    get_assessment_score_repo,
    get_pool,
    get_release_assessment_repo,
    get_service_repository,
)
from forgeguard.core.permissions import Permissions, UserRole
from forgeguard.data.repositories.decisions import DecisionRepository
from forgeguard.services.audit import AuditService, SYSTEM_ACTOR_ROLE
from forgeguard.services.decision_engine import (
    DecisionEngine,
    DecisionOutcome,
    SecurityEscalationService,
    SYSTEM_ACTOR_UUID,
)

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/api/v1/releases", tags=["releases"])

# Maximum seconds the assessment pipeline is allowed to run.
_PIPELINE_TIMEOUT_SECONDS = 300


# ---------------------------------------------------------------------------
# Background pipeline
# ---------------------------------------------------------------------------


async def _run_assessment_pipeline(
    *,
    assessment_id: uuid.UUID,
    service_id: uuid.UUID,
    service_name: str,
    commit_sha: Optional[str],
    pr_reference: Optional[str],
    pool: asyncpg.Pool,
    ai_engine: Any,
    actor_id: Optional[str],
    actor_role: str,
) -> None:
    """Orchestrate ChangeAnalyzer → RiskScorer → ExplanationGenerator.

    Always resolves the assessment to either 'completed' or 'failed'.
    """
    from forgeguard.data.repositories.assessment_score_repository import (  # noqa: PLC0415
        AssessmentScoreRepository,
    )
    from forgeguard.data.repositories.audit_logs import AuditLogRepository  # noqa: PLC0415
    from forgeguard.data.repositories.release_assessment_repository import (  # noqa: PLC0415
        ReleaseAssessmentRepository,
    )
    from forgeguard.services.audit import AuditService  # noqa: PLC0415
    from forgeguard.services.release_guardian.change_analyzer import ChangeAnalyzer  # noqa: PLC0415
    from forgeguard.services.release_guardian.explanation_generator import (  # noqa: PLC0415
        ExplanationGenerator,
    )
    from forgeguard.services.release_guardian.prompt_loader import PromptLoader  # noqa: PLC0415
    from forgeguard.services.release_guardian.providers_mock import (  # noqa: PLC0415
        MockChangeDataProvider,
    )
    from forgeguard.services.release_guardian.risk_scorer import RiskScorer  # noqa: PLC0415

    assessment_repo = ReleaseAssessmentRepository(pool)
    score_repo = AssessmentScoreRepository(pool)
    audit_svc = AuditService(AuditLogRepository(pool))
    provider = MockChangeDataProvider()
    change_analyzer = ChangeAnalyzer(provider)
    risk_scorer = RiskScorer()
    prompt_loader = PromptLoader()
    prompt_loader.load_all()
    explanation_generator = ExplanationGenerator(ai_engine, prompt_loader)

    log = logger.bind(
        assessment_id=str(assessment_id),
        service_id=str(service_id),
    )

    try:
        await assessment_repo.update(assessment_id, {"status": "in_progress"})

        async def _pipeline() -> tuple[Any, Any, list[Any]]:
            analysis = await change_analyzer.analyze(
                service_id,
                commit_sha=commit_sha,
                pr_reference=pr_reference,
            )
            score = risk_scorer.score(analysis)
            findings = await explanation_generator.generate_findings(
                score,
                analysis,
                {
                    "service_id": service_id,
                    "assessment_id": assessment_id,
                    "service_name": service_name,
                },
            )
            return analysis, score, findings

        analysis, score, findings = await asyncio.wait_for(
            _pipeline(), timeout=_PIPELINE_TIMEOUT_SECONDS
        )

        # Persist the risk score to assessment_scores table.
        await score_repo.save_risk_score(assessment_id, service_id, score)

        # Serialize findings to dicts for JSONB storage.
        findings_payload = [
            {
                "id": str(f.id),
                "title": f.title,
                "severity": f.severity.value if hasattr(f.severity, "value") else str(f.severity),
                "dimension": f.dimension.value if hasattr(f.dimension, "value") else str(f.dimension),
                "explanation": f.explanation,
                "business_impact": f.business_impact,
                "remediation_steps": f.remediation_steps,
                "confidence_score": float(f.confidence_score),
                "source": f.source.value if hasattr(f.source, "value") else str(f.source),
            }
            for f in findings
        ]

        change_analysis_payload = {
            "summary": analysis.model_dump(mode="json") if hasattr(analysis, "model_dump") else {},
            "findings": findings_payload,
        }

        await assessment_repo.update(
            assessment_id,
            {
                "status": "completed",
                "change_analysis": json.dumps(change_analysis_payload),
                "completed_at": datetime.now(timezone.utc).isoformat(),
            },
        )

        await audit_svc.log_event(
            actor_id=actor_id,
            actor_role=actor_role,
            action="release_assessment.completed",
            resource_type="release_assessment",
            resource_id=assessment_id,
            after_state={"status": "completed", "overall_score": score.overall_score},
        )

        log.info(
            "assessment_pipeline.completed",
            overall_score=score.overall_score,
            findings_count=len(findings),
        )

    except asyncio.TimeoutError:
        log.error("assessment_pipeline.timeout", timeout=_PIPELINE_TIMEOUT_SECONDS)
        _reason = f"Pipeline exceeded {_PIPELINE_TIMEOUT_SECONDS}s timeout"
        await _mark_failed(assessment_repo, audit_svc, assessment_id, actor_id, actor_role, _reason)

    except Exception as exc:
        log.exception("assessment_pipeline.failed", error=str(exc))
        await _mark_failed(
            assessment_repo, audit_svc, assessment_id, actor_id, actor_role, str(exc)
        )


async def _mark_failed(
    assessment_repo: Any,
    audit_svc: AuditService,
    assessment_id: uuid.UUID,
    actor_id: Optional[str],
    actor_role: str,
    reason: str,
) -> None:
    """Update status to 'failed' and write an audit event; never raises."""
    try:
        await assessment_repo.update(
            assessment_id,
            {
                "status": "failed",
                "completed_at": datetime.now(timezone.utc).isoformat(),
            },
        )
    except Exception:
        logger.exception("assessment_pipeline.status_update_failed", assessment_id=str(assessment_id))

    try:
        await audit_svc.log_event(
            actor_id=actor_id,
            actor_role=actor_role,
            action="release_assessment.failed",
            resource_type="release_assessment",
            resource_id=assessment_id,
            after_state={"status": "failed", "reason": reason},
        )
    except Exception:
        logger.exception("assessment_pipeline.audit_failed", assessment_id=str(assessment_id))


# ---------------------------------------------------------------------------
# Serialization helpers
# ---------------------------------------------------------------------------


def _build_risk_score(score_row: dict[str, Any]) -> Optional[RiskScoreResponse]:
    """Convert an assessment_scores row to RiskScoreResponse."""
    if score_row is None:
        return None
    dimension_scores = score_row.get("dimension_scores") or {}
    if isinstance(dimension_scores, str):
        dimension_scores = json.loads(dimension_scores)
    contributing_factors_raw = score_row.get("contributing_factors") or []
    if isinstance(contributing_factors_raw, str):
        contributing_factors_raw = json.loads(contributing_factors_raw)
    factors = [
        ContributingFactorResponse(
            metric_name=f.get("metric_name", ""),
            actual_value=float(f.get("actual_value", 0)),
            threshold=float(f.get("threshold", 0)),
            risk_contribution=float(f.get("risk_contribution", 0)),
            dimension=f.get("dimension", ""),
        )
        for f in contributing_factors_raw
    ]
    overall = score_row.get("overall_score")
    if overall is not None:
        try:
            overall = int(overall)
        except (TypeError, ValueError):
            overall = 0
    return RiskScoreResponse(
        overall_score=overall or 0,
        dimension_scores=dimension_scores,
        contributing_factors=factors,
    )


def _build_findings(change_analysis: Optional[Any]) -> list[FindingResponse]:
    """Extract findings from the change_analysis JSONB field."""
    if not change_analysis:
        return []
    if isinstance(change_analysis, str):
        try:
            change_analysis = json.loads(change_analysis)
        except (json.JSONDecodeError, TypeError):
            return []
    if not isinstance(change_analysis, dict):
        return []
    findings_raw = change_analysis.get("findings") or []
    results: list[FindingResponse] = []
    for f in findings_raw:
        try:
            results.append(
                FindingResponse(
                    id=uuid.UUID(f["id"]),
                    title=f.get("title", ""),
                    severity=f.get("severity", ""),
                    dimension=f.get("dimension", ""),
                    explanation=f.get("explanation", ""),
                    business_impact=f.get("business_impact", ""),
                    remediation_steps=f.get("remediation_steps") or [],
                    confidence_score=float(f.get("confidence_score", 0.0)),
                    source=f.get("source", ""),
                )
            )
        except Exception:
            logger.warning("releases.invalid_finding_in_change_analysis", finding=f)
    return results


def _change_analysis_summary(change_analysis: Optional[Any]) -> Optional[dict]:
    """Return the 'summary' portion of the change_analysis JSONB or None."""
    if not change_analysis:
        return None
    if isinstance(change_analysis, str):
        try:
            change_analysis = json.loads(change_analysis)
        except (json.JSONDecodeError, TypeError):
            return None
    if isinstance(change_analysis, dict):
        return change_analysis.get("summary")
    return None


def _to_assessment_response(row: dict[str, Any]) -> ReleaseAssessmentResponse:
    return ReleaseAssessmentResponse(
        id=row["id"],
        service_id=row["service_id"],
        commit_sha=row.get("commit_sha"),
        pr_reference=row.get("pr_reference"),
        status=row["status"],
        created_at=row["created_at"],
        completed_at=row.get("completed_at"),
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post(
    "/assess",
    status_code=202,
    summary="Request a new release risk assessment",
    response_description="Assessment accepted; poll GET /api/v1/releases/{id} for results.",
    dependencies=[Depends(require_permission(Permissions.ASSESSMENT_REQUEST))],
)
async def request_assessment(
    body: ReleaseAssessmentRequest,
    request: Request,
    background_tasks: BackgroundTasks,
    assessment_repo=Depends(get_release_assessment_repo),
    service_repo=Depends(get_service_repository),
    pool: asyncpg.Pool = Depends(get_pool),
    ai_engine=Depends(get_ai_engine),
    audit_svc: AuditService = Depends(get_audit_service),
) -> JSONResponse:
    """Accept a release assessment request and enqueue the pipeline."""
    service = await service_repo.get_by_id(body.service_id)
    if service is None:
        raise HTTPException(
            status_code=404,
            detail={
                "error_code": "not_found",
                "message": f"Service {body.service_id} not found",
            },
        )

    actor_id: Optional[str] = getattr(request.state, "user_id", None)
    if actor_id is not None:
        actor_id = str(actor_id)
    actor_role: str = getattr(request.state, "user_role", "unknown") or "unknown"

    assessment_id = uuid.uuid4()
    record = await assessment_repo.create(
        {
            "id": assessment_id,
            "service_id": body.service_id,
            "commit_sha": body.commit_sha,
            "pr_reference": body.pr_reference,
            "requested_by": actor_id,
            "status": "pending",
        }
    )

    await audit_svc.log_mutation(
        actor_id=actor_id,
        actor_role=actor_role,
        action="release_assessment.requested",
        resource_type="release_assessment",
        resource_id=assessment_id,
        after_state={
            "service_id": str(body.service_id),
            "commit_sha": body.commit_sha,
            "pr_reference": body.pr_reference,
        },
    )

    service_name: str = service.get("name", "unknown") if isinstance(service, dict) else "unknown"

    background_tasks.add_task(
        _run_assessment_pipeline,
        assessment_id=assessment_id,
        service_id=body.service_id,
        service_name=service_name,
        commit_sha=body.commit_sha,
        pr_reference=body.pr_reference,
        pool=pool,
        ai_engine=ai_engine,
        actor_id=actor_id,
        actor_role=actor_role,
    )

    created_at = record["created_at"]
    if hasattr(created_at, "isoformat"):
        created_at_str = created_at.isoformat()
    else:
        created_at_str = str(created_at)

    response = JSONResponse(
        status_code=202,
        content={
            "id": str(record["id"]),
            "service_id": str(record["service_id"]),
            "status": record["status"],
            "created_at": created_at_str,
        },
    )
    response.headers["Location"] = f"/api/v1/releases/{assessment_id}"
    return response


@router.get(
    "/{id}",
    response_model=ReleaseAssessmentDetailResponse,
    summary="Retrieve a release assessment by ID",
    dependencies=[Depends(require_permission(Permissions.SERVICE_VIEW))],
)
async def get_assessment(
    id: uuid.UUID,
    assessment_repo=Depends(get_release_assessment_repo),
    score_repo=Depends(get_assessment_score_repo),
) -> ReleaseAssessmentDetailResponse:
    """Return the full assessment including risk score, findings, and metadata."""
    row = await assessment_repo.get_by_id(id)
    if row is None:
        raise HTTPException(
            status_code=404,
            detail={
                "error_code": "not_found",
                "message": f"Assessment {id} not found",
            },
        )

    score_row = await score_repo.get_by_assessment_id(id)
    risk_score = _build_risk_score(score_row)
    findings = _build_findings(row.get("change_analysis"))
    summary = _change_analysis_summary(row.get("change_analysis"))

    return ReleaseAssessmentDetailResponse(
        id=row["id"],
        service_id=row["service_id"],
        commit_sha=row.get("commit_sha"),
        pr_reference=row.get("pr_reference"),
        status=row["status"],
        created_at=row["created_at"],
        completed_at=row.get("completed_at"),
        risk_score=risk_score,
        findings=findings,
        change_analysis_summary=summary,
    )


@router.get(
    "/{id}/decision",
    summary="Get comprehensive combined decision view for a release assessment",
    dependencies=[Depends(require_permission(Permissions.SERVICE_VIEW))],
)
async def get_release_decision_view(
    id: uuid.UUID,
    pool: asyncpg.Pool = Depends(get_pool),
) -> Any:
    """Return the complete combined decision context for a release assessment.

    Aggregates assessment metadata, health and risk scores, all findings grouped
    by severity, the system recommendation (computed from current thresholds),
    escalation status, conditions for conditional approvals, and the human
    decision record if one has been submitted.

    Accessible to all authenticated roles (service.view permission).
    Returns 404 for unknown assessment IDs.
    """
    from forgeguard.data.repositories.assessment_score_repository import (  # noqa: PLC0415
        AssessmentScoreRepository,
    )
    from forgeguard.data.repositories.decisions import DecisionRepository  # noqa: PLC0415
    from forgeguard.data.repositories.release_assessment_repository import (  # noqa: PLC0415
        ReleaseAssessmentRepository,
    )
    from forgeguard.services.decision_engine.decision_view_service import (  # noqa: PLC0415
        CombinedDecisionViewService,
    )

    assessment_repo = ReleaseAssessmentRepository(pool)
    score_repo = AssessmentScoreRepository(pool)
    decision_repo = DecisionRepository(pool)

    svc = CombinedDecisionViewService(assessment_repo, score_repo, decision_repo)
    view = await svc.get_combined_view(id)

    if view is None:
        raise HTTPException(
            status_code=404,
            detail={"detail": "Release assessment not found"},
        )

    logger.info(
        "releases.decision_view.served",
        assessment_id=str(id),
        recommendation=view.system_recommendation.decision,
    )

    return view.model_dump(mode="json")


@router.post(
    "/{id}/decide",
    response_model=ReleaseDecisionResponse,
    status_code=201,
    summary="Submit a human release decision for a completed assessment",
    dependencies=[Depends(require_any_permission([Permissions.RELEASE_APPROVE, Permissions.RELEASE_BLOCK]))],
)
async def decide_release(
    id: uuid.UUID,
    body: ReleaseDecisionRequest,
    request: Request,
    pool: asyncpg.Pool = Depends(get_pool),
    audit_svc: AuditService = Depends(get_audit_service),
) -> ReleaseDecisionResponse:
    """Submit APPROVE, CONDITIONAL_APPROVE, or BLOCK on a completed release assessment.

    Validates the assessment is completed, checks for duplicate decisions, fetches
    Health Score and Risk Score from the assessment_scores table, runs the escalation
    check, and persists an immutable decision record with full audit trail.

    For assessments with critical security findings (was_escalated=true), only Security
    Reviewers may submit APPROVE or CONDITIONAL_APPROVE decisions (403 otherwise).
    """
    from decimal import Decimal  # noqa: PLC0415
    from forgeguard.data.repositories.assessment_score_repository import (  # noqa: PLC0415
        AssessmentScoreRepository,
    )
    from forgeguard.data.repositories.audit_logs import AuditLogRepository  # noqa: PLC0415
    from forgeguard.data.repositories.release_assessment_repository import (  # noqa: PLC0415
        ReleaseAssessmentRepository,
    )

    actor_id: Optional[str] = getattr(request.state, "user_id", None)
    if actor_id is not None:
        actor_id = str(actor_id)
    actor_role: str = getattr(request.state, "user_role", "unknown") or "unknown"

    assessment_repo = ReleaseAssessmentRepository(pool)
    decision_repo = DecisionRepository(pool)
    score_repo = AssessmentScoreRepository(pool)

    # 1. Load assessment (404 if not found).
    assessment = await assessment_repo.get_by_id(id)
    if assessment is None:
        raise HTTPException(
            status_code=404,
            detail={"detail": "Release assessment not found"},
        )

    # 2. Assessment must be completed (400 otherwise).
    assessment_status = assessment.get("status")
    if assessment_status != "completed":
        raise HTTPException(
            status_code=400,
            detail={
                "detail": (
                    f"Assessment is '{assessment_status}'. "
                    "The assessment must be completed before a decision can be submitted."
                ),
                "errors": [
                    {
                        "field": "release_assessment_id",
                        "message": (
                            f"Assessment status is '{assessment_status}', expected 'completed'"
                        ),
                    }
                ],
            },
        )

    # 3. Duplicate decision check (409 if any decision already exists).
    existing_decisions = await decision_repo.find_by_release_assessment(id)
    if existing_decisions:
        raise HTTPException(
            status_code=409,
            detail={
                "detail": "Decision already exists",
                "existing_decision_id": str(existing_decisions[0]["id"]),
            },
        )

    # 4. Fetch Health Score and Risk Score from ASSESSMENT_SCORES (400 if missing).
    health_score_row = await score_repo.get_score_by_type(id, "health")
    risk_score_row = await score_repo.get_score_by_type(id, "risk")

    missing_scores: list[str] = []
    if health_score_row is None:
        missing_scores.append("health")
    if risk_score_row is None:
        missing_scores.append("risk")
    if missing_scores:
        raise HTTPException(
            status_code=400,
            detail={
                "detail": "Both health and risk scores are required for a decision",
                "errors": [
                    {
                        "field": f"{s}_score",
                        "message": f"{s.capitalize()} score not yet computed for this assessment",
                    }
                    for s in missing_scores
                ],
            },
        )

    health_d = Decimal(str(health_score_row.get("overall_score") or 0))  # type: ignore[union-attr]
    risk_d = Decimal(str(risk_score_row.get("overall_score") or 0))  # type: ignore[union-attr]

    # 5. Extract findings from change_analysis JSONB for escalation check.
    findings: list[Any] = _build_findings(assessment.get("change_analysis"))

    # 6. Run escalation check (fail-closed — any exception → BLOCK with should_escalate=True).
    threshold_decision = DecisionEngine.merge_scores(health_d, risk_d)
    escalation = SecurityEscalationService.check_escalation(findings, threshold_decision)

    # 7. Escalation RBAC guard: APPROVE/CONDITIONAL_APPROVE on escalated assessments
    #    require Security Reviewer role.
    if (
        escalation.should_escalate
        and body.decision != ReleaseDecisionCreate.BLOCK
        and actor_role != UserRole.security_reviewer.value
    ):
        raise HTTPException(
            status_code=403,
            detail={
                "detail": (
                    "This assessment has critical security findings that require escalation. "
                    "Only a Security Reviewer can submit APPROVE or CONDITIONAL_APPROVE "
                    "for an escalated assessment."
                ),
                "error_code": "escalation_requires_security_reviewer",
                "required_permission": "release.approve",
                "current_role": actor_role,
            },
        )

    # 8. Persist the immutable decision record.
    decision_id = uuid.uuid4()
    decision_data: dict[str, Any] = {
        "id": decision_id,
        "release_assessment_id": id,
        "health_score_at_decision": health_d,
        "risk_score_at_decision": risk_d,
        "decision": body.decision.value,
        "decided_by_role": actor_role,
        "decided_by": uuid.UUID(actor_id) if actor_id else None,
        "rationale": body.rationale,
        "comment": body.comment,
        "was_escalated": escalation.should_escalate,
    }
    persisted = await decision_repo.create(decision_data)

    # 9. Immutable audit record for the human decision.
    await audit_svc.log_event(
        actor_id=actor_id,
        actor_role=actor_role,
        action="release_decision",
        resource_type="release_decision",
        resource_id=decision_id,
        before_state=None,
        after_state={
            "decision": body.decision.value,
            "rationale": body.rationale,
            "was_escalated": escalation.should_escalate,
            "health_score_at_decision": float(health_d),
            "risk_score_at_decision": float(risk_d),
            "assessment_id": str(id),
        },
    )

    # 10. System audit record for the escalation event (actor=SYSTEM).
    if escalation.should_escalate:
        audit_repo = AuditLogRepository(pool)
        system_audit_svc = AuditService(audit_repo)
        try:
            await system_audit_svc.log_event(
                actor_id=SYSTEM_ACTOR_UUID,
                actor_role=SYSTEM_ACTOR_ROLE,
                action="security_auto_escalation",
                resource_type="release_decision",
                resource_id=decision_id,
                before_state={
                    "original_recommendation": escalation.original_recommendation.value,
                },
                after_state={
                    "final_recommendation": DecisionOutcome.BLOCK.value,
                    "escalation_reasons": escalation.escalation_reasons,
                    "assessment_id": str(id),
                },
            )
        except Exception:
            logger.error(
                "releases.decide.escalation_audit_failed",
                decision_id=str(decision_id),
                assessment_id=str(id),
            )

    logger.info(
        "releases.decide.completed",
        assessment_id=str(id),
        decision=body.decision.value,
        was_escalated=escalation.should_escalate,
        actor_role=actor_role,
    )

    created_at = persisted.get("created_at")

    return ReleaseDecisionResponse(
        id=persisted["id"],
        release_assessment_id=id,
        health_score_at_decision=float(health_d),
        risk_score_at_decision=float(risk_d),
        decision=body.decision.value,
        decided_by_role=actor_role,
        decided_by=uuid.UUID(actor_id) if actor_id else None,
        rationale=body.rationale,
        comment=body.comment,
        was_escalated=escalation.should_escalate,
        escalation_reasons=[
            EscalationReasonResponse(finding_id=r["finding_id"], title=r["title"])
            for r in escalation.escalation_reasons
        ],
        original_recommendation=(
            escalation.original_recommendation.value if escalation.should_escalate else None
        ),
        created_at=created_at or datetime.now(timezone.utc),
    )


@router.get(
    "",
    response_model=PaginatedAssessmentResponse,
    summary="List release assessments with optional filtering and cursor pagination",
    dependencies=[Depends(require_permission(Permissions.SERVICE_VIEW))],
)
async def list_assessments(
    assessment_repo=Depends(get_release_assessment_repo),
    service_id: Optional[uuid.UUID] = Query(default=None),
    status: Optional[str] = Query(default=None),
    cursor: Optional[str] = Query(default=None),
    limit: int = Query(default=50, ge=1, le=100),
) -> PaginatedAssessmentResponse:
    """Return a paginated list of assessments using opaque cursor-based pagination."""
    before_created_at: Optional[datetime] = None
    before_id: Optional[uuid.UUID] = None

    if cursor:
        try:
            before_created_at, before_id = decode_cursor(cursor)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail={
                    "error_code": "invalid_cursor",
                    "message": "The provided cursor is invalid or corrupted",
                },
            )

    # Fetch limit+1 to determine has_more without an extra COUNT query.
    rows = await assessment_repo.list_page(
        service_id=service_id,
        status=status,
        before_created_at=before_created_at,
        before_id=before_id,
        limit=limit + 1,
    )

    has_more = len(rows) > limit
    page = rows[:limit]

    next_cursor: Optional[str] = None
    if has_more and page:
        last = page[-1]
        next_cursor = encode_cursor(last["created_at"], last["id"])

    return PaginatedAssessmentResponse(
        items=[_to_assessment_response(r) for r in page],
        cursor=next_cursor,
        has_more=has_more,
    )
