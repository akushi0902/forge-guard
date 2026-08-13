"""Health assessment API endpoints (WO-042).

Routes:
    POST /api/v1/services/{service_id}/assess          — trigger a health assessment
    GET  /api/v1/services/{service_id}/scores          — retrieve latest health score
    GET  /api/v1/services/{service_id}/findings        — list findings (paginated, filterable)
    GET  /api/v1/services/{service_id}/findings/{id}   — retrieve finding detail

RBAC:
  - POST assess:      assessment.request (Developer, Tech Lead, Platform Admin)
  - GET scores:       service.view (all authenticated roles)
  - GET findings:     service.view (all authenticated roles)
  - GET finding/:id:  service.view (all authenticated roles)
"""

from __future__ import annotations

import json
import uuid
from decimal import Decimal
from typing import Annotated, Any, Optional

import asyncpg
import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, Request

from forgeguard.api.dependencies.audit import get_audit_service
from forgeguard.api.dependencies.auth import CurrentUserDep
from forgeguard.api.schemas.assessment import (
    AssessmentTriggerResponse,
    DimensionScoreResponse,
    FindingDetailResponse,
    FindingListResponse,
    HealthScoreResponse,
)
from forgeguard.core.dependencies import get_pool
from forgeguard.core.exceptions import ConflictError, NotFoundError
from forgeguard.core.permissions import Permissions, has_permission
from forgeguard.data.repositories.assessment_repository import AssessmentRepository
from forgeguard.data.repositories.findings import FindingRepository
from forgeguard.data.repositories.policies import PolicyRepository
from forgeguard.data.repositories.scores import ScoreRepository
from forgeguard.data.repositories.services import ServiceRepository
from forgeguard.services.assessment_orchestrator import AssessmentOrchestrator
from forgeguard.services.audit import AuditService
from forgeguard.services.mock_data_collector import MockDataCollector
from forgeguard.services.forge_scorecard import ForgeScorecardHttpAdapter
from forgeguard.services.sync_queue import SyncQueueService

logger = structlog.get_logger(__name__)

router = APIRouter(tags=["health"])


# ---------------------------------------------------------------------------
# Dependency providers
# ---------------------------------------------------------------------------


async def _get_pool(pool: asyncpg.Pool = Depends(get_pool)) -> asyncpg.Pool:
    return pool


async def get_service_repo(pool: asyncpg.Pool = Depends(get_pool)) -> ServiceRepository:
    return ServiceRepository(pool)


async def get_assessment_repo(pool: asyncpg.Pool = Depends(get_pool)) -> AssessmentRepository:
    return AssessmentRepository(pool)


async def get_finding_repo(pool: asyncpg.Pool = Depends(get_pool)) -> FindingRepository:
    return FindingRepository(pool)


async def get_score_repo(pool: asyncpg.Pool = Depends(get_pool)) -> ScoreRepository:
    return ScoreRepository(pool)


async def get_policy_repo(pool: asyncpg.Pool = Depends(get_pool)) -> PolicyRepository:
    return PolicyRepository(pool)


async def get_orchestrator(
    pool: asyncpg.Pool = Depends(get_pool),
    assessment_repo: AssessmentRepository = Depends(get_assessment_repo),
    policy_repo: PolicyRepository = Depends(get_policy_repo),
    score_repo: ScoreRepository = Depends(get_score_repo),
    finding_repo: FindingRepository = Depends(get_finding_repo),
    service_repo: ServiceRepository = Depends(get_service_repo),
    audit_svc: AuditService = Depends(get_audit_service),
) -> AssessmentOrchestrator:
    from forgeguard.core.config import get_settings  # noqa: PLC0415
    settings = get_settings()
    scorecard_adapter: ForgeScorecardHttpAdapter | None = None
    if settings.forge_scorecard_api_key:
        scorecard_adapter = ForgeScorecardHttpAdapter(
            base_url=settings.forge_scorecard_url,
            api_key=settings.forge_scorecard_api_key,
        )
    sync_queue = SyncQueueService(pool)
    return AssessmentOrchestrator(
        assessment_repo=assessment_repo,
        policy_repo=policy_repo,
        score_repo=score_repo,
        finding_repo=finding_repo,
        data_collector=MockDataCollector(),
        audit_svc=audit_svc,
        scorecard_adapter=scorecard_adapter,
        sync_queue=sync_queue,
        service_repo=service_repo,
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _require_permission(current_user: Any, permission: str, action_desc: str) -> None:
    if not has_permission(current_user.role, permission):
        raise HTTPException(
            status_code=403,
            detail={
                "error": {
                    "code": "forbidden",
                    "message": f"This action requires the {permission} permission.",
                    "details": {"required_permission": permission, "action": action_desc},
                }
            },
        )


def _dim_score_response(dim_score: Any) -> DimensionScoreResponse:
    return DimensionScoreResponse(
        dimension=dim_score.dimension,
        score=dim_score.score,
        total_rules=dim_score.total_rules,
        passed_rules=dim_score.passed_rules,
        failed_rules=dim_score.failed_rules,
        inconclusive_rules=dim_score.inconclusive_rules,
        error_rules=dim_score.error_rules,
        has_data=dim_score.has_data,
    )


def _dim_score_from_jsonb(dim_str: str, data: dict[str, Any]) -> DimensionScoreResponse:
    """Reconstruct a DimensionScoreResponse from a stored JSONB dimension_scores dict."""
    score_val = data.get("score")
    return DimensionScoreResponse(
        dimension=dim_str,
        score=Decimal(str(score_val)) if score_val is not None else None,
        total_rules=data.get("total_rules", 0),
        passed_rules=data.get("passed_rules", 0),
        failed_rules=data.get("failed_rules", 0),
        inconclusive_rules=data.get("inconclusive_rules", 0),
        error_rules=data.get("error_rules", 0),
        has_data=data.get("has_data", False),
    )


# ---------------------------------------------------------------------------
# POST /api/v1/services/{service_id}/assess
# ---------------------------------------------------------------------------


@router.post(
    "/api/v1/services/{service_id}/assess",
    response_model=AssessmentTriggerResponse,
    status_code=200,
    summary="Trigger a health assessment for a service",
)
async def trigger_assessment(
    service_id: uuid.UUID,
    request: Request,
    current_user: CurrentUserDep,
    service_repo: ServiceRepository = Depends(get_service_repo),
    assessment_repo: AssessmentRepository = Depends(get_assessment_repo),
    orchestrator: AssessmentOrchestrator = Depends(get_orchestrator),
) -> AssessmentTriggerResponse:
    """Trigger a synchronous health assessment for the given service.

    Executes the complete policy evaluation pipeline and returns results.
    Returns 409 if an assessment is already in progress for this service.
    """
    _require_permission(current_user, Permissions.ASSESSMENT_REQUEST, "trigger assessment")

    # ── 404 if service doesn't exist ──────────────────────────────────────
    service = await service_repo.get_by_id(service_id)
    if service is None:
        raise HTTPException(
            status_code=404,
            detail={"detail": "Service not found", "error_code": "SERVICE_NOT_FOUND"},
        )

    # ── 409 if assessment already in progress ─────────────────────────────
    in_progress = await assessment_repo.check_in_progress(service_id)
    if in_progress is not None:
        raise HTTPException(
            status_code=409,
            detail={
                "detail": "Assessment already in progress for this service",
                "error_code": "ASSESSMENT_IN_PROGRESS",
                "assessment_id": str(in_progress["id"]),
            },
        )

    correlation_id = request.headers.get("x-request-id")

    try:
        result = await orchestrator.run(
            service_id=service_id,
            actor_id=str(current_user.user_id),
            actor_role=current_user.role,
            trigger_type="manual",
            correlation_id=correlation_id,
        )
    except Exception as exc:
        logger.error(
            "health.trigger_assessment.failed",
            service_id=str(service_id),
            error=str(exc),
            correlation_id=correlation_id,
        )
        raise HTTPException(
            status_code=500,
            detail={
                "detail": "Assessment failed. See server logs for details.",
                "error_code": "ASSESSMENT_FAILED",
                "correlation_id": correlation_id,
            },
        )

    return AssessmentTriggerResponse(
        assessment_id=result.assessment_id,
        status=result.status,
        overall_score=result.overall_score,
        dimension_scores={
            dim: _dim_score_response(ds)
            for dim, ds in result.dimension_scores.items()
        },
        finding_counts=result.finding_counts,
        evaluated_at=result.evaluated_at,
        message=result.message,
    )


# ---------------------------------------------------------------------------
# GET /api/v1/services/{service_id}/scores
# ---------------------------------------------------------------------------


@router.get(
    "/api/v1/services/{service_id}/scores",
    response_model=HealthScoreResponse,
    summary="Get the latest health score for a service",
)
async def get_service_scores(
    service_id: uuid.UUID,
    current_user: CurrentUserDep,
    service_repo: ServiceRepository = Depends(get_service_repo),
    score_repo: ScoreRepository = Depends(get_score_repo),
    finding_repo: FindingRepository = Depends(get_finding_repo),
) -> HealthScoreResponse:
    """Return the most recent health score for a service with dimension breakdown.

    Returns overall_score=null when no assessments have been run.
    """
    _require_permission(current_user, Permissions.SERVICE_VIEW, "view service scores")

    service = await service_repo.get_by_id(service_id)
    if service is None:
        raise HTTPException(
            status_code=404,
            detail={"detail": "Service not found", "error_code": "SERVICE_NOT_FOUND"},
        )

    score_row = await score_repo.get_latest_health_score(service_id)

    if score_row is None:
        return HealthScoreResponse(
            service_id=service_id,
            overall_score=None,
            dimension_scores={},
            weights_used={},
            finding_counts={},
            last_evaluated_at=None,
            message="No assessments have been run for this service.",
        )

    # Parse dimension_scores from JSONB
    dim_scores_raw = score_row.get("dimension_scores") or {}
    if isinstance(dim_scores_raw, str):
        dim_scores_raw = json.loads(dim_scores_raw)

    dimension_scores = {
        dim: _dim_score_from_jsonb(dim, data)
        for dim, data in dim_scores_raw.items()
    }

    # Parse weights_used from JSONB
    weights_raw = score_row.get("weights_used") or {}
    if isinstance(weights_raw, str):
        weights_raw = json.loads(weights_raw)
    weights_used = {k: Decimal(str(v)) for k, v in weights_raw.items()}

    # Finding counts
    finding_counts = await finding_repo.count_by_severity(service_id)

    overall = score_row.get("overall_score")
    scorecard_sync_status = score_row.get("forge_sync_status", "pending")
    last_scorecard_sync_at = score_row.get("last_scorecard_sync_at")

    return HealthScoreResponse(
        service_id=service_id,
        overall_score=Decimal(str(overall)) if overall is not None else None,
        dimension_scores=dimension_scores,
        weights_used=weights_used,
        finding_counts=finding_counts,
        last_evaluated_at=score_row.get("created_at"),
        message=None,
        forge_scorecard_stale=(scorecard_sync_status == "stale"),
        last_scorecard_sync_at=last_scorecard_sync_at,
        scorecard_sync_status=scorecard_sync_status,
    )


# ---------------------------------------------------------------------------
# GET /api/v1/services/{service_id}/findings
# ---------------------------------------------------------------------------


@router.get(
    "/api/v1/services/{service_id}/findings",
    response_model=FindingListResponse,
    summary="List findings for a service with filtering and pagination",
)
async def list_service_findings(
    service_id: uuid.UUID,
    current_user: CurrentUserDep,
    severity: Optional[str] = Query(
        default=None,
        description="Comma-separated severity filter: critical,high,medium,low",
    ),
    status: Optional[str] = Query(
        default=None,
        description="Comma-separated status filter: open,acknowledged,remediated,…",
    ),
    dimension: Optional[str] = Query(
        default=None,
        description="Comma-separated dimension filter",
    ),
    cursor: Optional[str] = Query(default=None, description="Pagination cursor"),
    limit: int = Query(default=20, ge=1, le=200),
    service_repo: ServiceRepository = Depends(get_service_repo),
    finding_repo: FindingRepository = Depends(get_finding_repo),
) -> FindingListResponse:
    """Return cursor-paginated findings for a service.

    Supports multi-value filters for severity, status, and dimension.
    Pass ``next_cursor`` from the previous response as ``cursor`` for the next page.
    """
    _require_permission(current_user, Permissions.SERVICE_VIEW, "view findings")

    service = await service_repo.get_by_id(service_id)
    if service is None:
        raise HTTPException(
            status_code=404,
            detail={"detail": "Service not found", "error_code": "SERVICE_NOT_FOUND"},
        )

    severity_list = [s.strip() for s in severity.split(",")] if severity else None
    status_list = [s.strip() for s in status.split(",")] if status else None
    dimension_list = [d.strip() for d in dimension.split(",")] if dimension else None

    rows = await finding_repo.list_by_service(
        service_id,
        severity=severity_list,
        status=status_list,
        cursor=cursor,
        limit=limit + 1,  # fetch one extra to detect more pages
    )

    # Apply dimension filter in-memory (list_by_service doesn't filter by dimension)
    if dimension_list:
        rows = [r for r in rows if r.get("dimension") in dimension_list]

    has_more = len(rows) > limit
    page_rows = rows[:limit]

    next_cursor: Optional[str] = None
    if has_more and page_rows:
        last = page_rows[-1]
        created_at = last.get("created_at")
        if created_at is not None:
            ts_str = created_at.isoformat() if hasattr(created_at, "isoformat") else str(created_at)
            next_cursor = f"{ts_str}:{last['id']}"

    items = [
        FindingDetailResponse(
            id=row["id"],
            assessment_id=row["assessment_id"],
            service_id=row["service_id"],
            title=row["title"],
            description=row.get("description"),
            severity=row["severity"],
            dimension=row["dimension"],
            status=row["status"],
            evidence=row.get("evidence"),
            ai_explanation=row.get("ai_explanation"),
            escalation_required=row.get("escalation_required", False),
            created_at=row["created_at"],
            resolved_at=row.get("resolved_at"),
        )
        for row in page_rows
    ]

    # total_count: approximate — count all non-terminal findings for this service
    total_q_rows = await finding_repo.list_by_service(
        service_id,
        severity=severity_list,
        status=status_list,
        limit=10_000,
    )
    if dimension_list:
        total_q_rows = [r for r in total_q_rows if r.get("dimension") in dimension_list]

    return FindingListResponse(
        items=items,
        next_cursor=next_cursor,
        total_count=len(total_q_rows),
    )


# ---------------------------------------------------------------------------
# GET /api/v1/services/{service_id}/findings/{finding_id}
# ---------------------------------------------------------------------------


@router.get(
    "/api/v1/services/{service_id}/findings/{finding_id}",
    response_model=FindingDetailResponse,
    summary="Retrieve a specific finding by ID",
)
async def get_finding_detail(
    service_id: uuid.UUID,
    finding_id: uuid.UUID,
    current_user: CurrentUserDep,
    service_repo: ServiceRepository = Depends(get_service_repo),
    finding_repo: FindingRepository = Depends(get_finding_repo),
) -> FindingDetailResponse:
    """Return full detail for a specific finding including evidence and escalation flag."""
    _require_permission(current_user, Permissions.SERVICE_VIEW, "view finding detail")

    service = await service_repo.get_by_id(service_id)
    if service is None:
        raise HTTPException(
            status_code=404,
            detail={"detail": "Service not found", "error_code": "SERVICE_NOT_FOUND"},
        )

    finding = await finding_repo.get_by_id(finding_id)
    if finding is None or str(finding.get("service_id")) != str(service_id):
        raise HTTPException(
            status_code=404,
            detail={"detail": "Finding not found", "error_code": "FINDING_NOT_FOUND"},
        )

    return FindingDetailResponse(
        id=finding["id"],
        assessment_id=finding["assessment_id"],
        service_id=finding["service_id"],
        title=finding["title"],
        description=finding.get("description"),
        severity=finding["severity"],
        dimension=finding["dimension"],
        status=finding["status"],
        evidence=finding.get("evidence"),
        ai_explanation=finding.get("ai_explanation"),
        escalation_required=finding.get("escalation_required", False),
        created_at=finding["created_at"],
        resolved_at=finding.get("resolved_at"),
    )
