"""Auth endpoints — user registration.

Routes:
    POST /api/v1/auth/register  — create a new user (Platform Admin only)

Authentication:
    Platform Admin gating via X-User-Role header (placeholder until JWT WO).
    Replace ``require_platform_admin`` with the real JWT dependency when ready.
"""

from __future__ import annotations

from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from forgeguard.api.schemas.auth import UserRegisterRequest, UserResponse
from forgeguard.core.dependencies import get_user_repository
from forgeguard.core.exceptions import ForbiddenError
from forgeguard.core.security import validate_password_strength
from forgeguard.data.repositories.users import UserRepository
from forgeguard.services.auth import AuthService

logger = structlog.get_logger(__name__)

router = APIRouter(
    prefix="/api/v1/auth",
    tags=["auth"],
)

_PLATFORM_ADMIN_ROLES = {"platform_admin", "Platform Admin"}


async def require_platform_admin(request: Request) -> str:
    """Enforce Platform Admin role.

    Reads the X-User-Role header and raises ForbiddenError for any other role.
    Replace with the real JWT dependency once WO-XXX (JWT auth) is complete.
    """
    role = request.headers.get("X-User-Role", "")
    if role not in _PLATFORM_ADMIN_ROLES:
        raise ForbiddenError(
            "User registration requires Platform Admin role.",
            required_permission="user.manage",
            contact_role="platform administrator",
        )
    return role


PlatformAdminDep = Annotated[str, Depends(require_platform_admin)]
UserRepoDep = Annotated[UserRepository, Depends(get_user_repository)]


@router.post(
    "/register",
    response_model=UserResponse,
    status_code=201,
    summary="Register a new user",
    responses={
        201: {"description": "User created successfully"},
        400: {
            "description": "Password policy violation",
            "content": {
                "application/json": {
                    "example": {
                        "detail": "Password does not meet security requirements",
                        "violations": [
                            "Password must be at least 12 characters long",
                            "Password must contain at least one uppercase letter",
                        ],
                    }
                }
            },
        },
        403: {"description": "Platform Admin role required"},
        409: {"description": "Email already registered"},
        422: {"description": "Request validation error"},
    },
)
async def register_user(
    body: UserRegisterRequest,
    _role: PlatformAdminDep,
    user_repo: UserRepoDep,
) -> UserResponse | JSONResponse:
    """Create a new ForgeGuard user with a bcrypt-hashed password.

    **Registration is restricted to Platform Admin role.**

    Password policy (all rules enforced simultaneously):
    - Minimum 12 characters
    - At least one uppercase letter (A–Z)
    - At least one lowercase letter (a–z)
    - At least one digit (0–9)
    - At least one special character

    Returns **201** with the created user on success.
    Returns **400** with a structured violations list if the password fails
    any policy rules.  Returns **409** if the email is already registered.
    """
    violations = validate_password_strength(body.password)
    if violations:
        return JSONResponse(
            status_code=400,
            content={
                "detail": "Password does not meet security requirements",
                "violations": violations,
            },
        )

    service = AuthService(user_repo)
    return await service.register_user(body)
