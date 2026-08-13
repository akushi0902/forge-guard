"""AI Agent conversational API endpoints (WO-065).

Routes:
    POST /api/v1/agent/query             — submit a natural-language query
    GET  /api/v1/agent/conversations     — list the caller's conversation history
    POST /api/v1/agent/query/feedback    — rate a response thumbs-up / thumbs-down

RBAC:
    POST /query:          agent.query permission (Developer, Tech Lead, Eng Manager)
    GET  /conversations:  service.view permission (all authenticated roles)
    POST /query/feedback: service.view permission (all authenticated roles)

Rate limiting:
    POST /query is additionally rate-limited at 20 queries/min per user (in addition
    to the global 100 req/min per IP enforced by RateLimiterMiddleware).
"""

from __future__ import annotations

import asyncio
import time
import uuid
from collections import defaultdict, deque
from typing import Any

import asyncpg
import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, Request

from forgeguard.api.dependencies.audit import get_audit_service
from forgeguard.api.dependencies.auth import CurrentUser, CurrentUserDep
from forgeguard.api.schemas.agent import (
    AgentFeedbackRequest,
    AgentFeedbackResponse,
    AgentQueryRequest,
    AgentQueryResponse,
    ConversationListResponse,
)
from forgeguard.core.dependencies import get_pool
from forgeguard.core.exceptions import ForbiddenError, NotFoundError
from forgeguard.core.permissions import Permissions, has_permission
from forgeguard.services.audit import AuditService

logger = structlog.get_logger(__name__)

router = APIRouter(tags=["agent"])

# ---------------------------------------------------------------------------
# Per-user rate limiter (20 queries / 60 s)
# ---------------------------------------------------------------------------

_AGENT_RATE_LIMIT = 20
_AGENT_RATE_WINDOW = 60.0
_user_timestamps: dict[str, deque[float]] = defaultdict(lambda: deque(maxlen=_AGENT_RATE_LIMIT + 1))
_rate_lock: asyncio.Lock | None = None


def _get_rate_lock() -> asyncio.Lock:
    global _rate_lock
    if _rate_lock is None:
        _rate_lock = asyncio.Lock()
    return _rate_lock


async def _check_user_rate_limit(user_id: uuid.UUID) -> None:
    key = str(user_id)
    now = time.monotonic()
    async with _get_rate_lock():
        q = _user_timestamps[key]
        # Evict entries outside the window
        while q and now - q[0] > _AGENT_RATE_WINDOW:
            q.popleft()
        if len(q) >= _AGENT_RATE_LIMIT:
            oldest = q[0]
            retry_after = max(1, int(_AGENT_RATE_WINDOW - (now - oldest)) + 1)
            raise HTTPException(
                status_code=429,
                detail={
                    "detail": "Agent query rate limit exceeded (20 queries/min).",
                    "error_code": "AGENT_RATE_LIMIT",
                },
                headers={"Retry-After": str(retry_after)},
            )
        q.append(now)


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# POST /api/v1/agent/query
# ---------------------------------------------------------------------------


@router.post(
    "/api/v1/agent/query",
    response_model=AgentQueryResponse,
    status_code=200,
    summary="Submit a natural-language query to the ForgeGuard AI agent",
)
async def agent_query(
    body: AgentQueryRequest,
    request: Request,
    current_user: CurrentUserDep,
    pool: asyncpg.Pool = Depends(get_pool),
    audit_svc: AuditService = Depends(get_audit_service),
) -> Any:
    """Process a conversational query about service health, findings, or guidance.

    Creates a new conversation if *conversation_id* is not supplied.  The response
    includes the AI-generated answer (or a template fallback if the LLM is
    unavailable), a confidence score, and the conversation_id for follow-ups.
    """
    if not has_permission(current_user.role, Permissions.AGENT_QUERY):
        raise HTTPException(
            status_code=403,
            detail={
                "detail": (
                    "This action requires the agent.query permission. "
                    "Developers, Tech Leads, and Engineering Managers may submit queries."
                ),
                "required_permission": Permissions.AGENT_QUERY,
            },
        )

    await _check_user_rate_limit(current_user.user_id)

    from forgeguard.core.dependencies import get_ai_engine  # noqa: PLC0415
    from forgeguard.data.repositories.agent_repository import AgentRepository  # noqa: PLC0415
    from forgeguard.services.agent.conversation_service import ConversationService  # noqa: PLC0415

    svc = ConversationService(
        agent_repo=AgentRepository(pool),
        ai_engine=get_ai_engine(),
        audit_svc=audit_svc,
    )

    try:
        return await svc.handle_query(
            body.query,
            user_id=current_user.user_id,
            actor_role=current_user.role,
            conversation_id=body.conversation_id,
            service_id=body.service_id,
        )
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail={"detail": str(exc)})
    except ForbiddenError as exc:
        raise HTTPException(status_code=403, detail={"detail": str(exc)})


# ---------------------------------------------------------------------------
# GET /api/v1/agent/conversations
# ---------------------------------------------------------------------------


@router.get(
    "/api/v1/agent/conversations",
    response_model=ConversationListResponse,
    summary="List conversation history for the authenticated user",
)
async def list_conversations(
    request: Request,
    current_user: CurrentUserDep,
    pool: asyncpg.Pool = Depends(get_pool),
    cursor: str | None = Query(default=None, description="Opaque pagination cursor"),
    limit: int = Query(default=50, ge=1, le=100, description="Page size (1–100)"),
) -> Any:
    """Return paginated conversation history scoped to the authenticated user.

    Conversations from other users are never included in the response.
    """
    from forgeguard.data.repositories.agent_repository import AgentRepository  # noqa: PLC0415
    from forgeguard.services.agent.conversation_service import ConversationService  # noqa: PLC0415
    from forgeguard.services.audit import AuditService as _AuditSvc  # noqa: PLC0415
    from forgeguard.data.repositories.audit_logs import AuditLogRepository  # noqa: PLC0415

    audit_svc = _AuditSvc(AuditLogRepository(pool))
    svc = ConversationService(
        agent_repo=AgentRepository(pool),
        ai_engine=None,
        audit_svc=audit_svc,
    )
    return await svc.list_conversations(
        current_user.user_id,
        cursor=cursor,
        limit=limit,
    )


# ---------------------------------------------------------------------------
# POST /api/v1/agent/query/feedback
# ---------------------------------------------------------------------------


@router.post(
    "/api/v1/agent/query/feedback",
    response_model=AgentFeedbackResponse,
    status_code=200,
    summary="Rate an AI agent response thumbs-up or thumbs-down",
)
async def agent_feedback(
    body: AgentFeedbackRequest,
    request: Request,
    current_user: CurrentUserDep,
    pool: asyncpg.Pool = Depends(get_pool),
) -> Any:
    """Record a user satisfaction rating for a specific message in a conversation.

    Uses the authenticated user's identity to both scope the feedback and verify
    conversation ownership (users can only rate their own conversations).
    """
    from forgeguard.data.repositories.agent_repository import AgentRepository  # noqa: PLC0415
    from forgeguard.data.repositories.audit_logs import AuditLogRepository  # noqa: PLC0415
    from forgeguard.services.agent.conversation_service import ConversationService  # noqa: PLC0415
    from forgeguard.services.audit import AuditService as _AuditSvc  # noqa: PLC0415

    audit_svc = _AuditSvc(AuditLogRepository(pool))
    svc = ConversationService(
        agent_repo=AgentRepository(pool),
        ai_engine=None,
        audit_svc=audit_svc,
    )

    try:
        return await svc.save_feedback(
            conversation_id=body.conversation_id,
            message_index=body.message_index,
            user_id=current_user.user_id,
            rating=body.rating,
        )
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail={"detail": str(exc)})
    except ForbiddenError as exc:
        raise HTTPException(status_code=403, detail={"detail": str(exc)})
