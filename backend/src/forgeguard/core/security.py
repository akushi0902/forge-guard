"""Password hashing, JWT token utilities, and strength validation.

Security guarantees:
    - Raw passwords are NEVER stored, logged, or returned.
    - All hashing uses bcrypt with cost factor 12.
    - Verification uses bcrypt.checkpw which is constant-time.
    - JWT access tokens are signed HS256; secret loaded from env only.
    - Refresh tokens are stored only as SHA-256 hex digests in the DB.
    - Raw refresh tokens exist only in httpOnly cookies.

Password policy (enforced by :func:`validate_password_strength`):
    - Minimum 12 characters.
    - At least one uppercase letter (A-Z).
    - At least one lowercase letter (a-z).
    - At least one digit (0-9).
    - At least one special character from the recognised symbol set.
"""

from __future__ import annotations

import hashlib
import re
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import bcrypt
import jwt as pyjwt

# Special characters recognised by the password policy.
_SPECIAL_RE = re.compile(r"[!@#$%^&*()\-_=+\[\]{}|;:'\",.<>?/\\`~]")
_UPPERCASE_RE = re.compile(r"[A-Z]")
_LOWERCASE_RE = re.compile(r"[a-z]")
_DIGIT_RE = re.compile(r"\d")

_BCRYPT_ROUNDS: int = 12

# ---------------------------------------------------------------------------
# JWT configuration
# ---------------------------------------------------------------------------

ACCESS_TOKEN_TTL: timedelta = timedelta(minutes=15)
REFRESH_TOKEN_TTL: timedelta = timedelta(days=7)
_JWT_ALGORITHM = "HS256"

# Required claims in access tokens — used by decode_access_token validation.
_REQUIRED_CLAIMS = frozenset({"sub", "role", "exp", "iat", "jti"})


# ---------------------------------------------------------------------------
# JWT token functions
# ---------------------------------------------------------------------------


def create_access_token(
    user_id: uuid.UUID,
    role: str,
    *,
    jwt_secret: str,
    expires_delta: timedelta = ACCESS_TOKEN_TTL,
) -> str:
    """Create a signed HS256 JWT access token.

    Claims are minimal to avoid PII in tokens: sub, role, exp, iat, jti only.

    Args:
        user_id:       The user's UUID (stored as string in ``sub`` claim).
        role:          The user's ForgeGuard persona role string.
        jwt_secret:    HMAC signing secret (from ``JWT_SECRET_KEY`` env var).
        expires_delta: Token lifetime; defaults to 15 minutes.

    Returns:
        Signed JWT string.
    """
    now = datetime.now(tz=timezone.utc)
    payload: dict[str, Any] = {
        "sub": str(user_id),
        "role": role,
        "iat": now,
        "exp": now + expires_delta,
        "jti": str(uuid.uuid4()),
    }
    return pyjwt.encode(payload, jwt_secret, algorithm=_JWT_ALGORITHM)


def decode_access_token(token: str, jwt_secret: str) -> dict[str, Any]:
    """Decode and validate a signed JWT access token.

    Args:
        token:      The raw JWT string from the cookie or Authorization header.
        jwt_secret: HMAC signing secret (must match the key used to sign).

    Returns:
        Decoded payload dict (sub, role, exp, iat, jti).

    Raises:
        UnauthorizedError: If the token is expired, tampered, or missing
            required claims.
    """
    from forgeguard.core.exceptions import UnauthorizedError  # noqa: PLC0415

    try:
        payload: dict[str, Any] = pyjwt.decode(
            token, jwt_secret, algorithms=[_JWT_ALGORITHM]
        )
    except pyjwt.ExpiredSignatureError:
        raise UnauthorizedError("Access token has expired.")
    except pyjwt.InvalidTokenError as exc:
        raise UnauthorizedError(f"Invalid access token: {exc}")

    missing = _REQUIRED_CLAIMS - payload.keys()
    if missing:
        raise UnauthorizedError(
            f"Access token is missing required claims: {', '.join(sorted(missing))}"
        )
    return payload


# ---------------------------------------------------------------------------
# Refresh token functions
# ---------------------------------------------------------------------------


def generate_refresh_token() -> str:
    """Generate a cryptographically secure URL-safe refresh token (64 bytes)."""
    return secrets.token_urlsafe(64)


def hash_refresh_token(raw_token: str) -> str:
    """Return the SHA-256 hex digest of *raw_token*.

    This is the value stored in the database — the raw token is never persisted.
    """
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Password functions
# ---------------------------------------------------------------------------


def hash_password(plain: str) -> str:
    """Hash *plain* using bcrypt with cost factor 12.

    Args:
        plain: The raw password string (never stored after this call).

    Returns:
        A 60-character bcrypt hash string suitable for storage.
    """
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt(rounds=_BCRYPT_ROUNDS)).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    """Return True if *plain* matches the stored *hashed* password.

    Comparison is constant-time (bcrypt.checkpw) to resist timing attacks.

    Args:
        plain:  The raw password provided by the user at login.
        hashed: The stored bcrypt hash from the database.
    """
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except Exception:
        return False


def validate_password_strength(plain: str) -> list[str]:
    """Check *plain* against the ForgeGuard password policy.

    Args:
        plain: The raw password to validate.

    Returns:
        A list of human-readable violation strings.  An empty list means the
        password satisfies all rules and may be hashed for storage.

    Examples::

        validate_password_strength("short")
        # → ["Password must be at least 12 characters long",
        #     "Password must contain at least one digit",
        #     "Password must contain at least one special character"]

        validate_password_strength("Str0ng!Password")
        # → []
    """
    violations: list[str] = []

    if len(plain) < 12:
        violations.append("Password must be at least 12 characters long")
    if not _UPPERCASE_RE.search(plain):
        violations.append("Password must contain at least one uppercase letter")
    if not _LOWERCASE_RE.search(plain):
        violations.append("Password must contain at least one lowercase letter")
    if not _DIGIT_RE.search(plain):
        violations.append("Password must contain at least one digit")
    if not _SPECIAL_RE.search(plain):
        violations.append("Password must contain at least one special character")

    return violations
