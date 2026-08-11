"""JWT and refresh token fixtures for auth tests (WO-022).

Provides:
  - TEST_JWT_SECRET: deterministic signing key for tests
  - make_access_token(): generate a pre-signed test access token
  - make_expired_access_token(): generate an already-expired token
  - make_refresh_token_hash(): deterministic hash for seed data
  - DEMO_USER_*: pre-hashed credential constants from the seed data
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from forgeguard.core.security import (
    create_access_token,
    generate_refresh_token,
    hash_refresh_token,
)

# ---------------------------------------------------------------------------
# Test signing key — never used in production.
# ---------------------------------------------------------------------------

TEST_JWT_SECRET = "test-jwt-secret-key-for-unit-tests-only-never-production"

# ---------------------------------------------------------------------------
# Pre-generated demo UUIDs (match identity_fixtures.sql seed data).
# ---------------------------------------------------------------------------

DEMO_USER_ID = uuid.UUID("a0000000-0000-0000-0000-000000000001")
DEMO_USER_EMAIL = "admin@forgeguard.demo"
DEMO_USER_ROLE = "platform_admin"

# ---------------------------------------------------------------------------
# Token factory helpers
# ---------------------------------------------------------------------------


def make_access_token(
    *,
    user_id: uuid.UUID = DEMO_USER_ID,
    role: str = DEMO_USER_ROLE,
    jwt_secret: str = TEST_JWT_SECRET,
    expires_delta: timedelta = timedelta(minutes=15),
) -> str:
    """Return a valid signed access token for tests."""
    return create_access_token(
        user_id=user_id,
        role=role,
        jwt_secret=jwt_secret,
        expires_delta=expires_delta,
    )


def make_expired_access_token(
    *,
    user_id: uuid.UUID = DEMO_USER_ID,
    role: str = DEMO_USER_ROLE,
    jwt_secret: str = TEST_JWT_SECRET,
) -> str:
    """Return a token that is already past its expiry timestamp."""
    return make_access_token(
        user_id=user_id,
        role=role,
        jwt_secret=jwt_secret,
        expires_delta=timedelta(seconds=-1),
    )


def make_raw_refresh_token() -> str:
    """Return a new random raw refresh token."""
    return generate_refresh_token()


def make_refresh_token_hash(raw: str | None = None) -> str:
    """Return the SHA-256 hash of a raw refresh token.

    If *raw* is None, generates a fresh token and hashes it.
    """
    raw = raw or generate_refresh_token()
    return hash_refresh_token(raw)


def make_refresh_token_row(
    *,
    id: uuid.UUID | None = None,
    user_id: uuid.UUID = DEMO_USER_ID,
    token_hash: str | None = None,
    revoked_at: datetime | None = None,
    replaced_by_id: uuid.UUID | None = None,
    expires_delta: timedelta = timedelta(days=7),
) -> dict:
    """Return a dict that mimics a refresh_tokens DB row."""
    raw = make_raw_refresh_token()
    return {
        "id": id or uuid.uuid4(),
        "user_id": user_id,
        "token_hash": token_hash or hash_refresh_token(raw),
        "expires_at": datetime.now(tz=timezone.utc) + expires_delta,
        "created_at": datetime.now(tz=timezone.utc),
        "revoked_at": revoked_at,
        "replaced_by_id": replaced_by_id,
    }
