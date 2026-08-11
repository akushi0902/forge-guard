"""Cookie helpers for JWT access and refresh token delivery.

Both tokens are delivered as httpOnly Secure SameSite=Strict cookies to
prevent JavaScript access and CSRF exploitation.

Cookie scoping:
    access_token  — path='/'           (needed by all API routes)
    refresh_token — path='/api/v1/auth' (only sent to the auth sub-path)
"""

from __future__ import annotations

from fastapi import Response

# Cookie names — must match what the frontend and route handlers expect.
ACCESS_TOKEN_COOKIE = "access_token"
REFRESH_TOKEN_COOKIE = "refresh_token"

# Max-age values in seconds.
_ACCESS_MAX_AGE = 15 * 60        # 15 minutes
_REFRESH_MAX_AGE = 7 * 24 * 3600  # 7 days


def set_auth_cookies(
    response: Response,
    *,
    access_token: str,
    refresh_token: str,
) -> None:
    """Attach httpOnly Secure SameSite=Strict cookies for both tokens.

    Args:
        response:      FastAPI response object to set cookies on.
        access_token:  Signed JWT access token string.
        refresh_token: Raw refresh token string (SHA-256 hash stored in DB).
    """
    response.set_cookie(
        key=ACCESS_TOKEN_COOKIE,
        value=access_token,
        httponly=True,
        secure=True,
        samesite="strict",
        path="/",
        max_age=_ACCESS_MAX_AGE,
    )
    response.set_cookie(
        key=REFRESH_TOKEN_COOKIE,
        value=refresh_token,
        httponly=True,
        secure=True,
        samesite="strict",
        path="/api/v1/auth",
        max_age=_REFRESH_MAX_AGE,
    )


def clear_auth_cookies(response: Response) -> None:
    """Remove both auth cookies by setting Max-Age=0 and clearing the value."""
    response.delete_cookie(
        key=ACCESS_TOKEN_COOKIE,
        httponly=True,
        secure=True,
        samesite="strict",
        path="/",
    )
    response.delete_cookie(
        key=REFRESH_TOKEN_COOKIE,
        httponly=True,
        secure=True,
        samesite="strict",
        path="/api/v1/auth",
    )
