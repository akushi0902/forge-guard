"""GDPR data subject rights endpoints.

Routes:
    GET    /api/v1/users/me/data              — Article 15: right of access
    PATCH  /api/v1/users/me/data              — Article 16: right to rectification
    DELETE /api/v1/users/me/data              — Article 17: right to erasure
    GET    /api/v1/users/me/data?export=true  — Article 20: right to data portability

Authentication:
    All routes require a valid JWT access-token cookie (access_token).
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Annotated, Optional

import structlog
from fastapi import APIRouter, Depends, Query, Response
from fastapi.responses import StreamingResponse

from forgeguard.api.dependencies.auth import CurrentUserDep
from forgeguard.api.schemas.data_subject import (
    UserDataExport,
    UserDataRectifyRequest,
    UserDataRectifyResponse,
    UserDataResponse,
)
from forgeguard.core.dependencies import get_data_subject_service
from forgeguard.services.data_subject import DataSubjectService

logger = structlog.get_logger(__name__)

router = APIRouter(
    prefix="/api/v1/users/me",
    tags=["data-subject"],
)


@router.get(
    "/data",
    summary="GDPR Article 15: right of access",
    response_model=UserDataResponse,
    responses={
        200: {"description": "User's personal data and related record counts."},
        401: {"description": "Authentication required."},
    },
)
async def get_user_data(
    current_user: CurrentUserDep,
    export: Optional[bool] = Query(default=None),
    service: DataSubjectService = Depends(get_data_subject_service),
) -> Response:
    """Return personal data profile (access) or a downloadable export (portability).

    When ``?export=true`` is passed the response is a streaming JSON attachment
    containing the full data export (GDPR Article 20).  Without the flag the
    endpoint returns a standard JSON response with profile and related-record
    counts (GDPR Article 15).
    """
    if export:
        return await _export_data(current_user.user_id, service)

    data = await service.access_data(current_user.user_id)

    profile = {
        "id": data["id"],
        "email": data["email"],
        "name": data["name"],
        "role": data["role"],
        "created_at": data["created_at"],
        "related_records": data["related_records"],
    }
    return UserDataResponse(data=profile)


async def _export_data(user_id, service: DataSubjectService) -> StreamingResponse:
    """Stream the full data export as a JSON attachment."""
    export_data = await service.export_data(user_id)
    timestamp = datetime.now(tz=timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    filename = f"user-data-export-{timestamp}.json"

    json_bytes = json.dumps(export_data, default=str, indent=2).encode("utf-8")

    return StreamingResponse(
        content=iter([json_bytes]),
        media_type="application/json",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
        },
    )


@router.patch(
    "/data",
    summary="GDPR Article 16: right to rectification",
    response_model=UserDataRectifyResponse,
    responses={
        200: {"description": "Updated user data."},
        400: {"description": "No fields provided or user not found."},
        401: {"description": "Authentication required."},
        409: {"description": "Email already in use."},
    },
)
async def rectify_user_data(
    body: UserDataRectifyRequest,
    current_user: CurrentUserDep,
    service: DataSubjectService = Depends(get_data_subject_service),
) -> UserDataRectifyResponse:
    """Update the authenticated user's email and/or display name (Article 16)."""
    result = await service.rectify_data(
        current_user.user_id,
        current_user.role,
        email=body.email,
        name=body.name,
    )
    return UserDataRectifyResponse(**result)


@router.delete(
    "/data",
    summary="GDPR Article 17: right to erasure",
    status_code=204,
    responses={
        204: {"description": "User data erased. Account deactivated."},
        401: {"description": "Authentication required."},
        409: {"description": "Cannot erase the last active Platform Admin."},
    },
)
async def erase_user_data(
    current_user: CurrentUserDep,
    service: DataSubjectService = Depends(get_data_subject_service),
) -> Response:
    """Cryptographically erase the authenticated user's PII and deactivate their account (Article 17).

    This operation is irreversible:
      - Email and name are overwritten with random data.
      - The account is deactivated (is_active=false, deleted_at=now).
      - All refresh tokens are revoked.
      - Audit log references to this user are anonymized (actor_id → well-known UUID).
    """
    await service.erase_data(current_user.user_id, current_user.role)
    return Response(status_code=204)
