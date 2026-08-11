"""Auth endpoints — registration, login, token refresh, and logout.

Routes:
    POST /api/v1/auth/register  — create a new user (Platform Admin only)
    POST /api/v1/auth/login     — authenticate and issue JWT cookies
    POST /api/v1/auth/refresh   — rotate refresh token
    POST /api/v1/auth/logout    — revoke refresh token and clear cookies

Authentication:
    Platform Admin gating for /register via X-User-Role header placeholder.
    Login/refresh/logout use cookies only (no RBAC header required).
"""

from __future__ import annotations

from typing import Annotated

import structlog
from fastapi import APIRouter, Cookie, Depends, Request, Response
from fastapi.responses import JSONResponse

from forgeguard.api.dependencies.auth import CurrentUserDep
from forgeguard.api.schemas.auth import (
    ChangePasswordRequest,
    LoginRequest,
    LoginResponse,
    UserRegisterRequest,
    UserResponse,
)
from forgeguard.core.config import get_settings
from forgeguard.core.cookies import clear_auth_cookies, set_auth_cookies
from forgeguard.core.dependencies import get_refresh_token_repository, get_user_repository
from forgeguard.core.exceptions import BadRequestError, ForbiddenError, UnauthorizedError
from forgeguard.core.security import (
    decode_access_token,
    generate_csrf_token,
    validate_password_strength,
)
from forgeguard.data.repositories.refresh_tokens import RefreshTokenRepository
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
RefreshTokenRepoDep = Annotated[RefreshTokenRepository, Depends(get_refresh_token_repository)]


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


@router.post(
    "/login",
    response_model=LoginResponse,
    status_code=200,
    summary="Authenticate and receive JWT cookies",
    responses={
        200: {"description": "Login successful — tokens set as httpOnly cookies"},
        401: {"description": "Invalid email or password"},
        422: {"description": "Request validation error"},
    },
)
async def login(
    body: LoginRequest,
    response: Response,
    user_repo: UserRepoDep,
    rt_repo: RefreshTokenRepoDep,
) -> LoginResponse:
    """Authenticate a user and set httpOnly Secure JWT cookies.

    On success, sets:
    - ``access_token`` cookie (15-min TTL, path=/)
    - ``refresh_token`` cookie (7-day TTL, path=/api/v1/auth)
    """
    settings = get_settings()
    service = AuthService(user_repo, rt_repo, jwt_secret=settings.jwt_secret_key)
    login_resp, access_token, raw_refresh = await service.authenticate_user(
        body.email, body.password
    )
    set_auth_cookies(response, access_token=access_token, refresh_token=raw_refresh)
    payload = decode_access_token(access_token, settings.jwt_secret_key)
    response.headers["X-CSRF-Token"] = generate_csrf_token(payload["jti"], settings.csrf_secret_key)
    return login_resp


@router.post(
    "/refresh",
    status_code=200,
    summary="Rotate refresh token and issue new JWT cookies",
    responses={
        200: {"description": "Tokens rotated — new cookies set"},
        401: {"description": "Invalid or expired refresh token"},
    },
)
async def refresh(
    response: Response,
    user_repo: UserRepoDep,
    rt_repo: RefreshTokenRepoDep,
    refresh_token: str | None = Cookie(default=None),
) -> dict:
    """Rotate the refresh token cookie and issue a new access token.

    Reads the ``refresh_token`` httpOnly cookie.  On success, replaces both
    cookies with a new token pair.  Token reuse triggers family-wide revocation.
    """
    if not refresh_token:
        raise UnauthorizedError("Invalid or expired refresh token.")
    settings = get_settings()
    service = AuthService(user_repo, rt_repo, jwt_secret=settings.jwt_secret_key)
    new_access, new_refresh = await service.refresh_tokens(refresh_token)
    set_auth_cookies(response, access_token=new_access, refresh_token=new_refresh)
    payload = decode_access_token(new_access, settings.jwt_secret_key)
    response.headers["X-CSRF-Token"] = generate_csrf_token(payload["jti"], settings.csrf_secret_key)
    return {"message": "Token refreshed"}


@router.post(
    "/logout",
    status_code=200,
    summary="Revoke refresh token and clear auth cookies",
    responses={
        200: {"description": "Logged out — cookies cleared"},
    },
)
async def logout(
    response: Response,
    user_repo: UserRepoDep,
    rt_repo: RefreshTokenRepoDep,
    refresh_token: str | None = Cookie(default=None),
) -> dict:
    """Revoke the current refresh token and clear both auth cookies."""
    if refresh_token:
        settings = get_settings()
        service = AuthService(user_repo, rt_repo, jwt_secret=settings.jwt_secret_key)
        await service.logout(refresh_token)
    clear_auth_cookies(response)
    return {"message": "Logged out"}


@router.post(
    "/change-password",
    status_code=200,
    summary="Change password with full session invalidation",
    responses={
        200: {"description": "Password changed; all sessions invalidated"},
        400: {"description": "Wrong current password or new password policy violation"},
        401: {"description": "Authentication required"},
    },
)
async def change_password(
    body: ChangePasswordRequest,
    current_user: CurrentUserDep,
    user_repo: UserRepoDep,
    rt_repo: RefreshTokenRepoDep,
) -> dict:
    """Change the authenticated user's password and revoke all refresh tokens.

    Validates the current password, enforces the password policy on the new
    password, updates the stored hash, and revokes every active refresh token
    for the user so that existing sessions cannot be silently renewed.
    """
    settings = get_settings()
    service = AuthService(user_repo, rt_repo, jwt_secret=settings.jwt_secret_key)
    await service.change_password(
        user_id=current_user.user_id,
        current_password=body.current_password,
        new_password=body.new_password,
    )
    return {"message": "Password changed successfully. All sessions have been invalidated."}
