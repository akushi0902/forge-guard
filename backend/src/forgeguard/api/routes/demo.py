"""Demo API endpoints — mock Payment Service.

Routes:
    POST /api/v1/demo/transactions          — create a mock transaction
    GET  /api/v1/demo/transactions/{id}     — fetch a single transaction
    GET  /api/v1/demo/services/payment      — get Payment Service metadata
    POST /api/v1/demo/reset                 — reset all demo data (Admin only)

Authentication:
    X-User-Role header placeholder (replaced by JWT auth in a future WO).
    All authenticated roles can read; only Platform Admin can reset.
"""

from __future__ import annotations

import uuid
from typing import Annotated, Any

import asyncpg
import structlog
from fastapi import APIRouter, Depends, Request

from forgeguard.api.schemas.demo import (
    PaymentServiceInfoResponse,
    ResetResponse,
    TransactionCreateRequest,
    TransactionResponse,
)
from forgeguard.api.schemas.demo_evaluation import DemoEvaluationResponse
from forgeguard.core.dependencies import get_demo_app_service, get_pool
from forgeguard.core.exceptions import ForbiddenError
from forgeguard.services.demo_app import DemoAppService

logger = structlog.get_logger(__name__)

router = APIRouter(
    prefix="/api/v1/demo",
    tags=["demo"],
)

_VALID_ROLES: frozenset[str] = frozenset({
    "platform_admin", "Platform Admin",
    "developer", "Developer",
    "tech_lead", "Tech Lead",
    "security_reviewer", "Security Reviewer",
    "engineering_manager", "Engineering Manager",
    "operator", "Operator",
})

_PLATFORM_ADMIN_ROLES: frozenset[str] = frozenset({
    "platform_admin", "Platform Admin",
})


async def require_authenticated(request: Request) -> str:
    """Require any valid ForgeGuard role header.

    Replace with the real JWT dependency once WO-XXX (JWT auth) is complete.
    """
    role = request.headers.get("X-User-Role", "")
    if not role or role not in _VALID_ROLES:
        raise ForbiddenError(
            "Authentication required to access demo endpoints.",
            required_permission="demo.read",
            contact_role="platform administrator",
        )
    return role


async def require_platform_admin(request: Request) -> str:
    """Enforce Platform Admin role for destructive demo operations."""
    role = request.headers.get("X-User-Role", "")
    if role not in _PLATFORM_ADMIN_ROLES:
        raise ForbiddenError(
            "Demo data reset requires Platform Admin role.",
            required_permission="demo.reset",
            contact_role="platform administrator",
        )
    return role


AuthenticatedDep = Annotated[str, Depends(require_authenticated)]
PlatformAdminDep = Annotated[str, Depends(require_platform_admin)]
DemoServiceDep = Annotated[DemoAppService, Depends(get_demo_app_service)]


@router.post(
    "/transactions",
    response_model=TransactionResponse,
    status_code=201,
    summary="Create a mock payment transaction",
    description=(
        "Simulates a payment authorization. No real financial processing occurs. "
        "Returns approved/declined status with a synthetic authorization code."
    ),
)
async def create_transaction(
    body: TransactionCreateRequest,
    service: DemoServiceDep,
    _role: AuthenticatedDep,
) -> TransactionResponse:
    result = await service.create_transaction(
        amount=body.amount,
        currency=body.currency,
        merchant=body.merchant,
        card_last_four=body.card_last_four,
    )
    return TransactionResponse.model_validate(result)


@router.get(
    "/transactions/{transaction_id}",
    response_model=TransactionResponse,
    status_code=200,
    summary="Get a mock payment transaction",
    description="Returns a single synthetic transaction by UUID. Returns 404 if not found.",
)
async def get_transaction(
    transaction_id: uuid.UUID,
    service: DemoServiceDep,
    _role: AuthenticatedDep,
) -> TransactionResponse:
    result = await service.get_transaction(transaction_id)
    return TransactionResponse.model_validate(result)


@router.get(
    "/services/payment",
    response_model=PaymentServiceInfoResponse,
    status_code=200,
    summary="Get Payment Service metadata",
    description=(
        "Returns metadata for the ForgeGuard Payment Service demo application, "
        "including name, version, is_demo flag, and simulated capabilities."
    ),
)
async def get_payment_service(
    service: DemoServiceDep,
    _role: AuthenticatedDep,
) -> PaymentServiceInfoResponse:
    result = await service.get_service_info()
    return PaymentServiceInfoResponse.model_validate(result)


@router.post(
    "/reset",
    response_model=ResetResponse,
    status_code=200,
    summary="Reset all demo transaction data",
    description=(
        "Purges all demo-generated transaction records and returns a confirmation "
        "with the count of purged records. Restricted to Platform Admin role."
    ),
)
async def reset_demo_data(
    service: DemoServiceDep,
    _role: PlatformAdminDep,
) -> ResetResponse:
    result = await service.reset_demo_data()
    return ResetResponse.model_validate(result)


@router.post(
    "/evaluate",
    response_model=DemoEvaluationResponse,
    status_code=200,
    summary="Trigger full governance evaluation of the Payment Service",
    description=(
        "Runs a complete governance evaluation of the ForgeGuard demo Payment Service: "
        "collects simulated data, evaluates all policy rules, generates findings, "
        "calculates the Health Score, generates AI explanations with template fallbacks, "
        "and persists all results. Returns the complete assessment including Health Score, "
        "dimension breakdown, findings, and remediation recommendations."
    ),
)
async def evaluate_demo_service(
    request: Request,
    role: AuthenticatedDep,
    pool: asyncpg.Pool = Depends(get_pool),
) -> Any:
    from forgeguard.data.repositories.assessment_repository import AssessmentRepository  # noqa: PLC0415
    from forgeguard.data.repositories.assessment_score_repository import AssessmentScoreRepository  # noqa: PLC0415
    from forgeguard.data.repositories.audit_logs import AuditLogRepository  # noqa: PLC0415
    from forgeguard.data.repositories.findings import FindingRepository  # noqa: PLC0415
    from forgeguard.data.repositories.policies import PolicyRepository  # noqa: PLC0415
    from forgeguard.data.repositories.remediation_recommendation_repository import (  # noqa: PLC0415
        RemediationRecommendationRepository,
    )
    from forgeguard.data.repositories.services import ServiceRepository  # noqa: PLC0415
    from forgeguard.core.dependencies import get_ai_engine  # noqa: PLC0415
    from forgeguard.services.demo_evaluation import DemoEvaluationService  # noqa: PLC0415
    from forgeguard.services.evaluation_engine import RuleEvaluationEngine  # noqa: PLC0415
    from forgeguard.services.mock_data_collector import MockDataCollector  # noqa: PLC0415

    svc = DemoEvaluationService(
        policy_repo=PolicyRepository(pool),
        service_repo=ServiceRepository(pool),
        assessment_repo=AssessmentRepository(pool),
        score_repo=AssessmentScoreRepository(pool),
        finding_repo=FindingRepository(pool),
        remediation_repo=RemediationRecommendationRepository(pool),
        audit_repo=AuditLogRepository(pool),
        ai_engine=get_ai_engine(),
        data_collector=MockDataCollector(),
        evaluation_engine=RuleEvaluationEngine(),
    )
    result = await svc.evaluate_payment_service(actor_role=role)
    return result.model_dump(mode="json")
