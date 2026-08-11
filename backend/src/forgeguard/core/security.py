"""Password hashing and strength validation utilities.

Security guarantees:
    - Raw passwords are NEVER stored, logged, or returned.
    - All hashing uses bcrypt with cost factor 12.
    - Verification uses bcrypt.checkpw which is constant-time.

Password policy (enforced by :func:`validate_password_strength`):
    - Minimum 12 characters.
    - At least one uppercase letter (A-Z).
    - At least one lowercase letter (a-z).
    - At least one digit (0-9).
    - At least one special character from the recognised symbol set.
"""

from __future__ import annotations

import re

import bcrypt

# Special characters recognised by the password policy.
_SPECIAL_RE = re.compile(r"[!@#$%^&*()\-_=+\[\]{}|;:'\",.<>?/\\`~]")
_UPPERCASE_RE = re.compile(r"[A-Z]")
_LOWERCASE_RE = re.compile(r"[a-z]")
_DIGIT_RE = re.compile(r"\d")

_BCRYPT_ROUNDS: int = 12


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
