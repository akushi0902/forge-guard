"""AuthService: orchestrates user registration and credential management."""

from __future__ import annotations

import uuid

import structlog

from forgeguard.api.schemas.auth import UserRegisterRequest, UserResponse
from forgeguard.core.exceptions import ConflictError
from forgeguard.core.security import hash_password
from forgeguard.data.repositories.users import UserRepository

logger = structlog.get_logger(__name__)


class AuthService:
    """Domain service for authentication operations.

    Args:
        user_repo: Injected UserRepository (async, asyncpg-backed).
    """

    def __init__(self, user_repo: UserRepository) -> None:
        self._repo = user_repo

    async def register_user(self, request: UserRegisterRequest) -> UserResponse:
        """Create a new user account.

        Preconditions:
            - Password strength has already been validated by the caller.
              (route handler checks and returns 400 with a violations list.)
            - ``request.email`` is lowercase-normalised (EmailField validator).

        Args:
            request: Validated registration payload.

        Returns:
            UserResponse with the persisted user's public fields.

        Raises:
            ConflictError: if ``request.email`` is already registered.
        """
        existing = await self._repo.find_by_email(request.email)
        if existing is not None:
            logger.warning(
                "auth.register.duplicate_email",
                email_domain=request.email.split("@")[-1],
            )
            raise ConflictError("User with this email already exists")

        password_hash = hash_password(request.password)

        name_bytes: bytes | None = (
            request.name.encode("utf-8") if request.name else None
        )

        row = await self._repo.create({
            "id": uuid.uuid4(),
            "email": request.email,
            "name_encrypted": name_bytes,
            "password_hash": password_hash,
            "role": request.role.value,
            "is_active": True,
            "failed_login_attempts": 0,
            "locked_until": None,
        })

        logger.info(
            "auth.register.success",
            role=request.role.value,
            email_domain=request.email.split("@")[-1],
        )

        name_decoded: str | None = None
        raw_name = row.get("name_encrypted")
        if isinstance(raw_name, (bytes, memoryview)):
            name_decoded = bytes(raw_name).decode("utf-8", errors="replace")
        elif isinstance(raw_name, str):
            name_decoded = raw_name

        return UserResponse(
            id=row["id"],
            email=row["email"],
            name=name_decoded,
            role=row["role"],
            is_active=row["is_active"],
            created_at=row["created_at"],
        )
