"""Admin endpoints for decision threshold configuration (WO-049).

Routes:
    POST   /api/v1/admin/decision-thresholds           — create a new threshold config
    GET    /api/v1/admin/decision-thresholds           — list all configs (paginated)
    GET    /api/v1/admin/decision-thresholds/active    — get the active config
    GET    /api/v1/admin/decision-thresholds/{id}      — get a specific config
    PUT    /api/v1/admin/decision-thresholds/{id}      — update a config
    POST   /api/v1/admin/decision-thresholds/{id}/activate — activate a config
    DELETE /api/v1/admin/decision-thresholds/{id}      — deactivate a config

RBAC:
    All endpoints require the ``threshold.manage`` permission (Platform Admin only).
    Returns 403 with ``required_permission: threshold.manage`` for other roles.

Every mutation produces an audit record with actor, timestamp, before/after state.
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Annotated, Any, Optional

import asyncpg
import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, Request

from forgeguard.api.dependencies.audit import get_audit_service
from forgeguard.api.dependencies.auth import CurrentUserDep
from forgeguard.api.schemas.decision_threshold import (
    DecisionThresholdCreate,
    DecisionThresholdListResponse,
    DecisionThresholdResponse,
    DecisionThresholdUpdate,
    MergeScoresRequest,
    MergeScoresResponse,
)
from forgeguard.core.dependencies import get_pool
from forgeguard.core.permissions import Permissions, has_permission
from forgeguard.data.repositories.decision_threshold_repository import (
    DecisionThresholdRepository,
)
from forgeguard.services.audit import AuditService
from forgeguard.services.decision_engine.engine import DEFAULT_THRESHOLDS, DecisionEngine
from forgeguard.services.decision_engine.threshold_service import (
    DecisionThresholdService,
    ThresholdValidationError,
)

logger = structlog.get_logger(__name__)

router = APIRouter(
    prefix="/api/v1/admin/decision-thresholds",
    tags=["admin", "decision-thresholds"],
)


# ---------------------------------------------------------------------------
# Dependency providers
# ---------------------------------------------------------------------------

async def get_threshold_repo(pool: asyncpg.Pool = Depends(get_pool)) -> DecisionThresholdRepository:
    return DecisionThresholdRepository(pool)


async def get_threshold_service(
    repo: DecisionThresholdRepository = Depends(get_threshold_repo),
) -> DecisionThresholdService:
    return DecisionThresholdService(repo)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _require_threshold_manage(current_user: Any) -> None:
    if not has_permission(current_user.role, Permissions.THRESHOLD_MANAGE):
        raise HTTPException(
            status_code=403,
            detail={
                "detail": "This action requires the threshold.manage permission.",
                "error_code": "forbidden",
                "required_permission": Permissions.THRESHOLD_MANAGE,
            },
        )


def _row_to_response(row: dict[str, Any]) -> DecisionThresholdResponse:
    return DecisionThresholdResponse(
        id=row["id"],
        name=row["name"],
        approve_health_min=Decimal(str(row["approve_health_min"])),
        approve_risk_max=Decimal(str(row["approve_risk_max"])),
        conditional_health_min=Decimal(str(row["conditional_health_min"])),
        conditional_risk_max=Decimal(str(row["conditional_risk_max"])),
        is_active=row["is_active"],
        created_by=row.get("created_by"),
        updated_by=row.get("updated_by"),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.post(
    "",
    response_model=DecisionThresholdResponse,
    status_code=201,
    summary="Create a new decision threshold configuration",
)
async def create_threshold(
    body: DecisionThresholdCreate,
    request: Request,
    current_user: CurrentUserDep,
    svc: DecisionThresholdService = Depends(get_threshold_service),
    audit: AuditService = Depends(get_audit_service),
) -> DecisionThresholdResponse:
    _require_threshold_manage(current_user)
    try:
        row = await svc.create(
            body.model_dump(),
            actor_id=current_user.user_id,
        )
    except ThresholdValidationError as exc:
        raise HTTPException(status_code=400, detail={"detail": str(exc), "error_code": "validation_error"})

    try:
        await audit.log_event(
            actor_id=current_user.user_id,
            actor_role=current_user.role,
            action="threshold.create",
            resource_type="decision_threshold",
            resource_id=row["id"],
            after_state={"name": row["name"], "is_active": row["is_active"]},
        )
    except Exception:
        logger.warning("admin_thresholds.audit_failed", threshold_id=str(row["id"]))

    return _row_to_response(row)


@router.get(
    "",
    response_model=DecisionThresholdListResponse,
    summary="List all decision threshold configurations",
)
async def list_thresholds(
    current_user: CurrentUserDep,
    cursor: Optional[str] = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    svc: DecisionThresholdService = Depends(get_threshold_service),
) -> DecisionThresholdListResponse:
    _require_threshold_manage(current_user)
    rows, total = await svc.list_all(cursor=cursor, limit=limit + 1)
    has_more = len(rows) > limit
    page = rows[:limit]
    next_cursor = page[-1]["created_at"].isoformat() if has_more and page else None
    return DecisionThresholdListResponse(
        items=[_row_to_response(r) for r in page],
        next_cursor=next_cursor,
        total=total,
    )


@router.get(
    "/active",
    response_model=DecisionThresholdResponse,
    summary="Get the currently active threshold configuration",
)
async def get_active_threshold(
    current_user: CurrentUserDep,
    svc: DecisionThresholdService = Depends(get_threshold_service),
) -> DecisionThresholdResponse:
    _require_threshold_manage(current_user)
    row = await svc.get_active()
    if row is None:
        raise HTTPException(
            status_code=404,
            detail={
                "detail": "No active threshold configuration found.",
                "error_code": "no_active_threshold",
            },
        )
    return _row_to_response(row)


@router.get(
    "/{threshold_id}",
    response_model=DecisionThresholdResponse,
    summary="Get a decision threshold configuration by ID",
)
async def get_threshold(
    threshold_id: uuid.UUID,
    current_user: CurrentUserDep,
    svc: DecisionThresholdService = Depends(get_threshold_service),
) -> DecisionThresholdResponse:
    _require_threshold_manage(current_user)
    row = await svc.get_by_id(threshold_id)
    if row is None:
        raise HTTPException(
            status_code=404,
            detail={"detail": "Threshold configuration not found.", "error_code": "not_found"},
        )
    return _row_to_response(row)


@router.put(
    "/{threshold_id}",
    response_model=DecisionThresholdResponse,
    summary="Update a decision threshold configuration",
)
async def update_threshold(
    threshold_id: uuid.UUID,
    body: DecisionThresholdUpdate,
    current_user: CurrentUserDep,
    svc: DecisionThresholdService = Depends(get_threshold_service),
    audit: AuditService = Depends(get_audit_service),
) -> DecisionThresholdResponse:
    _require_threshold_manage(current_user)

    before = await svc.get_by_id(threshold_id)
    if before is None:
        raise HTTPException(
            status_code=404,
            detail={"detail": "Threshold configuration not found.", "error_code": "not_found"},
        )

    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    try:
        row = await svc.update(threshold_id, updates, actor_id=current_user.user_id)
    except ThresholdValidationError as exc:
        raise HTTPException(status_code=400, detail={"detail": str(exc), "error_code": "validation_error"})

    if row is None:
        raise HTTPException(
            status_code=404,
            detail={"detail": "Threshold configuration not found.", "error_code": "not_found"},
        )

    try:
        await audit.log_event(
            actor_id=current_user.user_id,
            actor_role=current_user.role,
            action="threshold.update",
            resource_type="decision_threshold",
            resource_id=row["id"],
            before_state={"name": before["name"]},
            after_state={"name": row["name"]},
        )
    except Exception:
        logger.warning("admin_thresholds.audit_failed", threshold_id=str(row["id"]))

    return _row_to_response(row)


@router.post(
    "/{threshold_id}/activate",
    response_model=DecisionThresholdResponse,
    summary="Activate a threshold configuration (deactivates the current active one)",
)
async def activate_threshold(
    threshold_id: uuid.UUID,
    current_user: CurrentUserDep,
    svc: DecisionThresholdService = Depends(get_threshold_service),
    audit: AuditService = Depends(get_audit_service),
) -> DecisionThresholdResponse:
    _require_threshold_manage(current_user)

    before_active = await svc.get_active()
    row = await svc.activate(threshold_id, actor_id=current_user.user_id)
    if row is None:
        raise HTTPException(
            status_code=404,
            detail={"detail": "Threshold configuration not found.", "error_code": "not_found"},
        )

    try:
        await audit.log_event(
            actor_id=current_user.user_id,
            actor_role=current_user.role,
            action="threshold.activate",
            resource_type="decision_threshold",
            resource_id=row["id"],
            before_state={"active_id": str(before_active["id"]) if before_active else None},
            after_state={"active_id": str(row["id"])},
        )
    except Exception:
        logger.warning("admin_thresholds.audit_failed", threshold_id=str(row["id"]))

    return _row_to_response(row)


@router.delete(
    "/{threshold_id}",
    response_model=DecisionThresholdResponse,
    summary="Deactivate a decision threshold configuration",
)
async def deactivate_threshold(
    threshold_id: uuid.UUID,
    current_user: CurrentUserDep,
    svc: DecisionThresholdService = Depends(get_threshold_service),
    audit: AuditService = Depends(get_audit_service),
) -> DecisionThresholdResponse:
    _require_threshold_manage(current_user)

    before = await svc.get_by_id(threshold_id)
    if before is None:
        raise HTTPException(
            status_code=404,
            detail={"detail": "Threshold configuration not found.", "error_code": "not_found"},
        )

    row = await svc.deactivate(threshold_id, actor_id=current_user.user_id)
    if row is None:
        raise HTTPException(
            status_code=404,
            detail={"detail": "Threshold configuration not found.", "error_code": "not_found"},
        )

    try:
        await audit.log_event(
            actor_id=current_user.user_id,
            actor_role=current_user.role,
            action="threshold.deactivate",
            resource_type="decision_threshold",
            resource_id=row["id"],
            before_state={"is_active": True},
            after_state={"is_active": False},
        )
    except Exception:
        logger.warning("admin_thresholds.audit_failed", threshold_id=str(row["id"]))

    return _row_to_response(row)


@router.post(
    "/merge-scores",
    response_model=MergeScoresResponse,
    summary="Preview the release decision for a given health+risk score pair",
    tags=["admin", "decision-thresholds"],
)
async def merge_scores(
    body: MergeScoresRequest,
    current_user: CurrentUserDep,
    svc: DecisionThresholdService = Depends(get_threshold_service),
) -> MergeScoresResponse:
    """Compute a decision for the supplied scores without persisting anything.

    Uses the active threshold config unless a specific threshold_id is provided.
    Falls back to hardcoded defaults if no active config exists.
    """
    _require_threshold_manage(current_user)

    if body.threshold_id is not None:
        config = await svc.get_by_id(body.threshold_id)
        if config is None:
            raise HTTPException(
                status_code=404,
                detail={"detail": "Threshold configuration not found.", "error_code": "not_found"},
            )
    else:
        config = await svc.get_active()

    result = DecisionEngine.merge_scores(
        body.health_score,
        body.risk_score,
        threshold_config=config,
    )
    return MergeScoresResponse(
        decision=result.decision.value,
        health_score=result.health_score,
        risk_score=result.risk_score,
        threshold_config_id=result.threshold_config_id,
        contributing_factors=result.contributing_factors,
    )
