"""FastAPI dependency for JWT access-token authentication.

Provides :func:`get_current_user` which reads the ``access_token`` httpOnly
cookie, decodes and validates the JWT, and returns a :class:`CurrentUser`
dataclass with the caller's identity.

Usage::

    from forgeguard.api.dependencies.auth import CurrentUserDep

    @router.get("/me")
    async def get_me(current_user: CurrentUserDep) -> dict:
        return {"user_id": str(current_user.user_id), "role": current_user.role}
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Annotated

from fastapi import Cookie, Depends

from forgeguard.core.config import Settings, get_settings
from forgeguard.core.exceptions import UnauthorizedError
from forgeguard.core.security import decode_access_token


@dataclass(frozen=True)
class CurrentUser:
    """Identity extracted from a validated JWT access token.

    Attributes:
        user_id: The authenticated user's UUID (from the ``sub`` claim).
        role:    The user's ForgeGuard persona role (from the ``role`` claim).
    """

    user_id: uuid.UUID
    role: str


async def get_current_user(
    settings: Annotated[Settings, Depends(get_settings)],
    access_token: str | None = Cookie(default=None),
) -> CurrentUser:
    """Validate the JWT access-token cookie and return the caller's identity.

    Reads the ``access_token`` httpOnly cookie set by the login endpoint.
    Decodes and validates the JWT signature, expiry, and required claims.

    Args:
        settings:     Application settings (for ``jwt_secret_key``).
        access_token: Value of the ``access_token`` cookie (injected by FastAPI).

    Returns:
        :class:`CurrentUser` with ``user_id`` and ``role``.

    Raises:
        UnauthorizedError (→ HTTP 401): If the cookie is absent, the token
            is expired, the signature is invalid, or required claims are missing.
    """
    if not access_token:
        raise UnauthorizedError("Authentication required.")

    payload = decode_access_token(access_token, settings.jwt_secret_key)

    try:
        user_id = uuid.UUID(payload["sub"])
    except (KeyError, ValueError):
        raise UnauthorizedError("Invalid access token: malformed subject claim.")

    role: str = payload.get("role", "")
    return CurrentUser(user_id=user_id, role=role)


#: Typed ``Annotated`` alias for use in route function signatures.
CurrentUserDep = Annotated[CurrentUser, Depends(get_current_user)]
