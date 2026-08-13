"""Request and response schemas for auth endpoints (registration, login)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from pydantic import Field, field_validator

from forgeguard.core.permissions import UserRole
from forgeguard.core.validation import EmailField, ForgeGuardBaseModel


class LoginRequest(ForgeGuardBaseModel):
    """Payload for POST /api/v1/auth/login."""

    email: EmailField
    password: str = Field(min_length=1, description="User password.")

    @field_validator("email", mode="before")
    @classmethod
    def _lowercase_email(cls, v: object) -> object:
        if isinstance(v, str):
            return v.lower()
        return v


class LoginResponse(ForgeGuardBaseModel):
    """Success body returned by POST /api/v1/auth/login.

    Does not include password_hash or name_encrypted bytes.
    Tokens are delivered via Set-Cookie headers, not in this body.
    """

    model_config = {  # type: ignore[assignment]
        "strict": True,
        "extra": "ignore",
        "frozen": False,
        "str_strip_whitespace": True,
        "populate_by_name": True,
    }

    id: uuid.UUID
    email: str
    name: Optional[str] = Field(default=None)
    role: str
    is_active: bool
    created_at: datetime


class UserRegisterRequest(ForgeGuardBaseModel):
    """Payload for POST /api/v1/auth/register.

    All string fields inherit whitespace-stripping from ForgeGuardBaseModel.
    The password field is NOT validated for strength here — strength checking
    happens in the route handler so that ALL violations are returned at once
    in a structured list rather than as a single Pydantic error.
    """

    email: EmailField
    name: str = Field(
        min_length=1,
        max_length=255,
        description="Display name of the new user (max 255 characters).",
    )
    password: str = Field(
        min_length=1,
        description="Raw password.  Must satisfy the ForgeGuard password policy.",
    )
    role: UserRole = Field(
        description=(
            "One of the six ForgeGuard personas: developer, tech_lead, "
            "security_reviewer, platform_admin, engineering_manager, operator."
        )
    )

    @field_validator("email", mode="before")
    @classmethod
    def _lowercase_email(cls, v: object) -> object:
        if isinstance(v, str):
            return v.lower()
        return v


class ChangePasswordRequest(ForgeGuardBaseModel):
    """Payload for POST /api/v1/auth/change-password."""

    current_password: str = Field(
        min_length=1,
        description="The user's current password for verification.",
    )
    new_password: str = Field(
        min_length=1,
        description="The desired new password (must satisfy the password policy).",
    )


class UserResponse(ForgeGuardBaseModel):
    """Representation of a User record returned to callers.

    Never includes password_hash or name_encrypted bytes — only the decoded
    display name is returned.
    """

    model_config = {  # type: ignore[assignment]
        "strict": True,
        "extra": "ignore",   # rows from asyncpg contain extra DB columns
        "frozen": False,
        "str_strip_whitespace": True,
        "populate_by_name": True,
    }

    id: uuid.UUID
    email: str
    name: Optional[str] = Field(default=None, description="Display name (decoded from storage).")
    role: str
    is_active: bool
    created_at: datetime
