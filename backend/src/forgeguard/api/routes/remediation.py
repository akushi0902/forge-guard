"""Remediation lifecycle API endpoints (WO-058, WO-062).

Routes:
    GET  /api/v1/findings/{finding_id}/remediation  — get/generate remediation recommendation
    POST /api/v1/findings/{finding_id}/exceptions   — submit exception request
    GET  /api/v1/exceptions/{exception_id}          — retrieve exception details

RBAC:
  - GET remediation: service.view permission (all authenticated roles)
  - POST exception:  exception.request permission (Developer, Tech Lead, Platform Admin)
  - GET exception:   service.view permission (all authenticated roles)
"""

from __future__ import annotations

import uuid
from typing import Annotated, Optional

import asyncpg
import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import JSONResponse

from forgeguard.api.dependencies.audit import get_audit_service
from forgeguard.api.dependencies.auth import CurrentUser, CurrentUserDep
from forgeguard.api.schemas.exception import ExceptionRequest, ExceptionResponse
from forgeguard.api.schemas.remediation import RemediationResponse
from forgeguard.core.dependencies import get_pool
from forgeguard.core.exceptions import BadRequestError, ConflictError, NotFoundError
from forgeguard.core.permissions import Permissions, has_permission
from forgeguard.data.repositories.exception_repository import ExceptionRepository
from forgeguard.data.repositories.findings import FindingRepository
from forgeguard.data.repositories.remediation_recommendation_repository import (
    RemediationRecommendationRepository,
)
from forgeguard.services.ai_engine.circuit_breaker import CircuitBreaker
from forgeguard.services.ai_engine.recommendation_generator import RecommendationGenerator
from forgeguard.services.ai_engine.service import AIEngineService
from forgeguard.services.audit import AuditService
from forgeguard.services.remediation.exception_service import ExceptionService
from forgeguard.services.remediation.recommendation_service import RecommendationService

logger = structlog.get_logger(__name__)

router = APIRouter(tags=["remediation"])

_FORBIDDEN_MSG = (
    "This action requires the exception.request permission. "
    "Developers and Tech Leads may submit exception requests."
)


# ---------------------------------------------------------------------------
# Dependency providers
# ---------------------------------------------------------------------------


async def get_finding_repo(pool: asyncpg.Pool = Depends(get_pool)) -> FindingRepository:
    return FindingRepository(pool)


async def get_exception_repo(pool: asyncpg.Pool = Depends(get_pool)) -> ExceptionRepository:
    return ExceptionRepository(pool)


async def get_rec_repo(
    pool: asyncpg.Pool = Depends(get_pool),
) -> RemediationRecommendationRepository:
    return RemediationRecommendationRepository(pool)


async def get_recommendation_service(
    finding_repo: FindingRepository = Depends(get_finding_repo),
    rec_repo: RemediationRecommendationRepository = Depends(get_rec_repo),
    audit_svc: AuditService = Depends(get_audit_service),
) -> RecommendationService:
    from forgeguard.services.ai_engine.cache import ResponseCache
    from forgeguard.services.ai_engine.providers.openai_provider import OpenAIProvider
    from forgeguard.core.config import get_settings

    settings = get_settings()
    provider = OpenAIProvider(api_key=getattr(settings, "openai_api_key", ""))
    cb = CircuitBreaker(failure_threshold=5, window_seconds=60, recovery_timeout=30)
    cache = ResponseCache()
    ai_engine = AIEngineService(provider=provider, circuit_breaker=cb, cache=cache)
    generator = RecommendationGenerator(ai_engine=ai_engine)
    return RecommendationService(
        finding_repo=finding_repo,
        rec_repo=rec_repo,
        generator=generator,
        audit_svc=audit_svc,
    )


async def get_exception_service(
    exception_repo: ExceptionRepository = Depends(get_exception_repo),
    finding_repo: FindingRepository = Depends(get_finding_repo),
    audit_svc: AuditService = Depends(get_audit_service),
) -> ExceptionService:
    return ExceptionService(exception_repo, finding_repo, audit_svc)


async def _require_exception_request(current_user: CurrentUserDep) -> CurrentUser:
    """Enforce exception.request permission and return the authenticated user."""
    if not has_permission(current_user.role, Permissions.EXCEPTION_REQUEST):
        raise HTTPException(
            status_code=403,
            detail={
                "error": {
                    "code": "forbidden",
                    "message": _FORBIDDEN_MSG,
                    "details": None,
                }
            },
        )
    return current_user


ExceptionRequestDep = Annotated[CurrentUser, Depends(_require_exception_request)]


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _exception_response(row: dict) -> ExceptionResponse:
    return ExceptionResponse(
        id=row["id"],
        finding_id=row["finding_id"],
        requested_by=row.get("requested_by"),
        justification=row["justification"],
        status=row["status"],
        approver_role=row["approver_role"],
        decided_by=row.get("decided_by"),
        decision_comment=row.get("decision_comment"),
        expires_at=row["expires_at"],
        decided_at=row.get("decided_at"),
        created_at=row["created_at"],
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get(
    "/api/v1/findings/{finding_id}/remediation",
    response_model=RemediationResponse,
    summary="Get or generate a remediation recommendation for a finding",
)
async def get_remediation(
    finding_id: uuid.UUID,
    request: Request,
    current_user: CurrentUserDep,
    force_refresh: bool = Query(default=False, description="Force regeneration even if cached"),
    svc: RecommendationService = Depends(get_recommendation_service),
) -> RemediationResponse:
    """Return the remediation recommendation for a finding, generating it if needed.

    The recommendation is cached — subsequent calls return the same record
    unless force_refresh=true is supplied.  Source is 'ai_generated' when the
    LLM was available, or 'template_fallback' when the circuit breaker was open.
    """
    correlation_id = request.headers.get("x-request-id")
    try:
        rec = await svc.get_or_generate(
            finding_id=finding_id,
            actor_id=str(current_user.user_id),
            actor_role=current_user.role,
            force_refresh=force_refresh,
            correlation_id=correlation_id,
        )
    except NotFoundError:
        raise HTTPException(
            status_code=404,
            detail={"detail": "Finding not found", "error_code": "FINDING_NOT_FOUND"},
        )
    return RemediationResponse(
        id=rec["id"],
        finding_id=rec["finding_id"],
        recommendation_text=rec["recommendation_text"],
        implementation_guide=rec.get("implementation_guide") or "",
        business_impact=rec.get("business_impact"),
        confidence_score=rec.get("confidence_score"),
        source=rec["source"],
        created_at=rec["created_at"],
    )


@router.post(
    "/api/v1/findings/{finding_id}/exceptions",
    status_code=201,
    summary="Submit an exception request for an open finding",
)
async def submit_exception_request(
    finding_id: uuid.UUID,
    body: ExceptionRequest,
    request: Request,
    current_user: ExceptionRequestDep,
    svc: ExceptionService = Depends(get_exception_service),
) -> JSONResponse:
    """Submit a time-bounded exception request for a policy finding.

    The approver is automatically determined from the finding's dimension:
    security findings route to Security Reviewer, all others to Platform Admin.
    """
    try:
        created = await svc.submit_request(
            finding_id=finding_id,
            justification=body.justification,
            expires_at=body.expires_at,
            actor_id=str(current_user.user_id),
            actor_role=current_user.role,
        )
    except NotFoundError as exc:
        raise HTTPException(
            status_code=404,
            detail={"detail": str(exc), "error_code": "NOT_FOUND"},
        )
    except BadRequestError as exc:
        raise HTTPException(
            status_code=400,
            detail={"detail": str(exc), "error_code": getattr(exc, "details", {}).get("error_code", "BAD_REQUEST")},
        )
    except ConflictError as exc:
        raise HTTPException(
            status_code=409,
            detail={"detail": str(exc), "error_code": "CONFLICT"},
        )

    return JSONResponse(
        status_code=201,
        content=_exception_response(created).model_dump(mode="json"),
    )


@router.get(
    "/api/v1/exceptions/{exception_id}",
    response_model=ExceptionResponse,
    summary="Retrieve an exception request by ID",
)
async def get_exception(
    exception_id: uuid.UUID,
    svc: ExceptionService = Depends(get_exception_service),
) -> ExceptionResponse:
    """Return the full details of an exception request."""
    row = await svc.get_exception(exception_id)
    if row is None:
        raise HTTPException(
            status_code=404,
            detail={"detail": f"Exception {exception_id} not found"},
        )
    return _exception_response(row)
