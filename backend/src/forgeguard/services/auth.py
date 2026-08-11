"""AuthService: orchestrates user registration, login, and token management."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Optional

import structlog

from forgeguard.api.schemas.auth import LoginResponse, UserRegisterRequest, UserResponse
from forgeguard.core.exceptions import ConflictError, UnauthorizedError
from forgeguard.core.security import (
    REFRESH_TOKEN_TTL,
    create_access_token,
    generate_refresh_token,
    hash_password,
    hash_refresh_token,
    verify_password,
)
from forgeguard.data.repositories.users import UserRepository

if TYPE_CHECKING:
    from forgeguard.data.repositories.refresh_tokens import RefreshTokenRepository

logger = structlog.get_logger(__name__)

# Generic message used for ALL login failures to prevent user enumeration.
_INVALID_CREDENTIALS_MSG = "Invalid email or password."


class AuthService:
    """Domain service for authentication operations.

    Args:
        user_repo:         Injected UserRepository (async, asyncpg-backed).
        refresh_token_repo: Injected RefreshTokenRepository; required for
                            login, refresh, and logout operations.
        jwt_secret:        HMAC signing secret from Settings.jwt_secret_key.
    """

    def __init__(
        self,
        user_repo: UserRepository,
        refresh_token_repo: Optional["RefreshTokenRepository"] = None,
        jwt_secret: str = "",
    ) -> None:
        self._repo = user_repo
        self._rt_repo = refresh_token_repo
        self._jwt_secret = jwt_secret

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

    # ------------------------------------------------------------------
    # Login / token issuance
    # ------------------------------------------------------------------

    async def authenticate_user(
        self, email: str, password: str
    ) -> tuple[LoginResponse, str, str]:
        """Validate credentials and issue an access + refresh token pair.

        Returns a 3-tuple: (LoginResponse, access_token, raw_refresh_token).
        The raw refresh token must be delivered via httpOnly cookie — never
        returned in the response body.

        Raises:
            UnauthorizedError: For any credential or account state failure,
                always with the generic message to prevent enumeration.
        """
        assert self._rt_repo is not None, "refresh_token_repo required for login"

        # Fetch user — timing-safe: always hash even for non-existent users.
        user = await self._repo.find_by_email(email)

        # Run verify_password even when user is None to equalise timing.
        candidate_hash = user["password_hash"] if user else "$2b$12$" + "x" * 53
        is_valid = verify_password(password, candidate_hash)

        if not user or not is_valid:
            logger.warning(
                "auth.login.failed",
                reason="invalid_credentials",
                email_domain=email.split("@")[-1] if "@" in email else "unknown",
            )
            raise UnauthorizedError(_INVALID_CREDENTIALS_MSG)

        if not user.get("is_active", True):
            logger.warning("auth.login.failed", reason="inactive_account", user_id=str(user["id"]))
            raise UnauthorizedError(_INVALID_CREDENTIALS_MSG)

        locked_until = user.get("locked_until")
        if locked_until is not None:
            if isinstance(locked_until, datetime):
                if locked_until.tzinfo is None:
                    locked_until = locked_until.replace(tzinfo=timezone.utc)
                if locked_until > datetime.now(tz=timezone.utc):
                    logger.warning(
                        "auth.login.failed",
                        reason="account_locked",
                        user_id=str(user["id"]),
                    )
                    raise UnauthorizedError("Account is temporarily locked. Please try again later.")

        access_token = create_access_token(
            user_id=user["id"],
            role=user["role"],
            jwt_secret=self._jwt_secret,
        )
        raw_refresh = generate_refresh_token()
        token_hash = hash_refresh_token(raw_refresh)
        expires_at = datetime.now(tz=timezone.utc) + REFRESH_TOKEN_TTL

        await self._rt_repo.create(
            user_id=uuid.UUID(str(user["id"])),
            token_hash=token_hash,
            expires_at=expires_at,
        )

        name_decoded = self._decode_name(user.get("name_encrypted"))

        logger.info(
            "auth.login.success",
            user_id=str(user["id"]),
            role=user["role"],
        )

        return (
            LoginResponse(
                id=user["id"],
                email=user["email"],
                name=name_decoded,
                role=user["role"],
                is_active=user["is_active"],
                created_at=user["created_at"],
            ),
            access_token,
            raw_refresh,
        )

    # ------------------------------------------------------------------
    # Token refresh (rotation)
    # ------------------------------------------------------------------

    async def refresh_tokens(
        self, raw_refresh_token: str
    ) -> tuple[str, str]:
        """Rotate a refresh token and issue a new access + refresh pair.

        Implements refresh token rotation:
          1. Look up the token hash in the DB.
          2. If found but already revoked → reuse detected → revoke entire family.
          3. If not found or expired → reject with 401.
          4. If valid → issue new pair, revoke old token with replaced_by_id link.

        Returns:
            (new_access_token, new_raw_refresh_token)

        Raises:
            UnauthorizedError: If the token is invalid, expired, or reused.
        """
        assert self._rt_repo is not None, "refresh_token_repo required for refresh"

        token_hash = hash_refresh_token(raw_refresh_token)

        # Check if token exists at all (including revoked).
        existing = await self._rt_repo.get_by_hash(token_hash)

        if existing is None:
            raise UnauthorizedError("Invalid or expired refresh token.")

        if existing.get("revoked_at") is not None:
            # Reuse detected — revoke the entire token family.
            user_id = uuid.UUID(str(existing["user_id"]))
            logger.warning(
                "auth.refresh.reuse_detected",
                user_id=str(user_id),
                token_id=str(existing["id"]),
            )
            await self._rt_repo.revoke_all_for_user(user_id)
            raise UnauthorizedError("Invalid or expired refresh token.")

        # Check expiry.
        expires_at = existing["expires_at"]
        if isinstance(expires_at, datetime):
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=timezone.utc)
            if expires_at <= datetime.now(tz=timezone.utc):
                raise UnauthorizedError("Invalid or expired refresh token.")

        # Fetch the user to build the new access token.
        user_id = uuid.UUID(str(existing["user_id"]))
        user = await self._repo.get_by_id(user_id)
        if user is None or not user.get("is_active", True):
            await self._rt_repo.revoke(uuid.UUID(str(existing["id"])))
            raise UnauthorizedError("Invalid or expired refresh token.")

        # Issue new token pair.
        new_access = create_access_token(
            user_id=user_id,
            role=user["role"],
            jwt_secret=self._jwt_secret,
        )
        new_raw_refresh = generate_refresh_token()
        new_hash = hash_refresh_token(new_raw_refresh)
        new_expires_at = datetime.now(tz=timezone.utc) + REFRESH_TOKEN_TTL

        new_row = await self._rt_repo.create(
            user_id=user_id,
            token_hash=new_hash,
            expires_at=new_expires_at,
        )

        # Revoke old token, link to new one.
        await self._rt_repo.revoke(
            uuid.UUID(str(existing["id"])),
            replaced_by_id=uuid.UUID(str(new_row["id"])),
        )

        logger.info("auth.refresh.success", user_id=str(user_id))
        return new_access, new_raw_refresh

    # ------------------------------------------------------------------
    # Logout
    # ------------------------------------------------------------------

    async def logout(self, raw_refresh_token: str) -> None:
        """Revoke the current refresh token on logout.

        If the token is not found (already cleared or expired), this is a
        no-op — the caller should clear cookies regardless.
        """
        assert self._rt_repo is not None, "refresh_token_repo required for logout"

        token_hash = hash_refresh_token(raw_refresh_token)
        existing = await self._rt_repo.get_by_hash(token_hash)
        if existing is not None and existing.get("revoked_at") is None:
            await self._rt_repo.revoke(uuid.UUID(str(existing["id"])))
            logger.info("auth.logout.success", user_id=str(existing["user_id"]))

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _decode_name(raw: Any) -> Optional[str]:
        if isinstance(raw, (bytes, memoryview)):
            return bytes(raw).decode("utf-8", errors="replace")
        if isinstance(raw, str):
            return raw
        return None
