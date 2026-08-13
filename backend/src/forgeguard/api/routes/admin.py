"""Admin CRUD endpoints for Prompt Template management.

All endpoints require the ``policy.manage`` permission (Platform Admin role).
Every mutation produces a structured audit log entry.

Routes:
    POST   /api/v1/admin/prompt-templates         — create a new template
    GET    /api/v1/admin/prompt-templates         — list with optional filters
    PATCH  /api/v1/admin/prompt-templates/{id}    — update (auto-increments version)
    DELETE /api/v1/admin/prompt-templates/{id}    — deactivate (soft delete)

Authentication:
    A real JWT auth dependency will be wired in by the auth WO.  Until then
    this module uses a placeholder ``require_policy_manage`` dependency that
    reads an ``X-User-Role`` header and raises ForbiddenError for non-admins.
    Replace ``require_policy_manage`` with the real auth dependency when ready.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Annotated, Any

import structlog
from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from forgeguard.api.schemas.prompt_template import (
    PromptTemplateCreate,
    PromptTemplateDeactivateResponse,
    PromptTemplateListResponse,
    PromptTemplateResponse,
    PromptTemplateUpdate,
)
from forgeguard.core.exceptions import ForbiddenError, NotFoundError
from forgeguard.data.repositories.prompt_template_repository import (
    PromptTemplateRepository,
)

logger = structlog.get_logger(__name__)

router = APIRouter(
    prefix="/api/v1/admin/prompt-templates",
    tags=["admin", "prompt-templates"],
)


# ---------------------------------------------------------------------------
# Auth dependency (placeholder — replaced by real JWT auth when available)
# ---------------------------------------------------------------------------

_PLATFORM_ADMIN_ROLES = {"platform_admin", "Platform Admin"}


async def require_policy_manage(request: Request) -> str:
    """Enforce policy.manage permission.

    Reads the X-User-Role header.  Returns the role string if authorised.
    Raises ForbiddenError(403) for missing or non-admin roles.

    Replace this dependency with the real JWT auth dependency once WO-XXX
    (JWT Authentication) is implemented.
    """
    role = request.headers.get("X-User-Role", "")
    if role not in _PLATFORM_ADMIN_ROLES:
        raise ForbiddenError(
            "Admin prompt template management requires Platform Admin role.",
            required_permission="policy.manage",
            contact_role="platform administrator",
        )
    return role


PolicyManageDep = Annotated[str, Depends(require_policy_manage)]


# ---------------------------------------------------------------------------
# DB session dependency (placeholder — real async session factory in future WO)
# ---------------------------------------------------------------------------

async def get_db_session() -> AsyncSession:  # pragma: no cover
    """Return an async SQLAlchemy session.

    Placeholder: a real session factory (with asyncpg pool) will be provided
    by the database WO.  Import and replace Depends(get_db_session) with
    the real dependency once available.
    """
    from forgeguard.core.dependencies import get_settings  # noqa: PLC0415
    settings = get_settings()
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: PLC0415
    engine = create_async_engine(settings.database_url, echo=False)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        yield session


SessionDep = Annotated[AsyncSession, Depends(get_db_session)]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _audit(
    action: str,
    template_id: uuid.UUID | None,
    actor_role: str,
    **extra: Any,
) -> None:
    """Emit a structured audit log entry for every mutation."""
    logger.info(
        "prompt_template_admin_action",
        action=action,
        template_id=str(template_id) if template_id else None,
        actor_role=actor_role,
        **extra,
    )


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.post(
    "",
    response_model=PromptTemplateResponse,
    status_code=201,
    summary="Create a prompt template",
)
async def create_prompt_template(
    body: PromptTemplateCreate,
    role: PolicyManageDep,
    session: SessionDep,
) -> PromptTemplateResponse:
    """Create a new prompt template at version 1."""
    repo = PromptTemplateRepository(session)
    template = await repo.create(
        name=body.name,
        template_text=body.template_text,
        variables=body.variables,
        dimension=body.dimension,
        severity_level=body.severity_level,
    )
    await session.commit()
    _audit("create", template.id, role, name=body.name, dimension=body.dimension)
    return PromptTemplateResponse.model_validate(template)


@router.get(
    "",
    response_model=PromptTemplateListResponse,
    summary="List prompt templates",
)
async def list_prompt_templates(
    role: PolicyManageDep,
    session: SessionDep,
    dimension: str | None = Query(default=None, description="Filter by dimension."),
    severity_level: str | None = Query(default=None, description="Filter by severity."),
    active_only: bool = Query(default=False, description="Return only active templates."),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> PromptTemplateListResponse:
    """List all prompt templates with optional filters and pagination."""
    repo = PromptTemplateRepository(session)
    items, total = await repo.list_all(
        dimension=dimension,
        severity_level=severity_level,
        active_only=active_only,
        limit=limit,
        offset=offset,
    )
    return PromptTemplateListResponse(
        items=[PromptTemplateResponse.model_validate(t) for t in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.patch(
    "/{template_id}",
    response_model=PromptTemplateResponse,
    summary="Update a prompt template (auto-increments version)",
)
async def update_prompt_template(
    template_id: uuid.UUID,
    body: PromptTemplateUpdate,
    role: PolicyManageDep,
    session: SessionDep,
) -> PromptTemplateResponse:
    """Update a template by creating a new version row.

    The previous version is deactivated; it is never deleted.
    """
    repo = PromptTemplateRepository(session)
    existing = await repo.get_by_id(template_id)
    if existing is None:
        raise NotFoundError(f"Prompt template {template_id!r} not found.")
    if not existing.is_active:
        raise NotFoundError(
            f"Prompt template {template_id!r} is inactive. "
            "Update the latest active version instead."
        )

    new_template = await repo.update(
        existing,
        template_text=body.template_text,
        variables=body.variables,
    )
    await session.commit()
    _audit(
        "update",
        new_template.id,
        role,
        name=new_template.name,
        old_version=existing.version,
        new_version=new_template.version,
    )
    return PromptTemplateResponse.model_validate(new_template)


@router.delete(
    "/{template_id}",
    response_model=PromptTemplateDeactivateResponse,
    summary="Deactivate a prompt template",
)
async def deactivate_prompt_template(
    template_id: uuid.UUID,
    role: PolicyManageDep,
    session: SessionDep,
) -> PromptTemplateDeactivateResponse:
    """Deactivate a template (soft delete — row is retained for audit trail)."""
    repo = PromptTemplateRepository(session)
    template = await repo.deactivate(template_id)
    if template is None:
        raise NotFoundError(f"Prompt template {template_id!r} not found.")
    await session.commit()
    _audit("deactivate", template.id, role, name=template.name)
    return PromptTemplateDeactivateResponse(
        id=template.id,
        is_active=template.is_active,
        deactivated_at=datetime.now(tz=timezone.utc),
    )
