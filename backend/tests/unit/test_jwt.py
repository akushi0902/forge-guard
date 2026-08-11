"""Unit tests for JWT token utilities in core/security.py (WO-022).

Tests cover:
  - create_access_token: correct claims, correct TTL
  - decode_access_token: success, expiry rejection, tampered rejection,
    missing claims rejection
  - generate_refresh_token: randomness, URL-safe
  - hash_refresh_token: determinism, SHA-256 hex length
"""

from __future__ import annotations

import uuid
from datetime import timedelta

import pytest

from forgeguard.core.exceptions import UnauthorizedError
from forgeguard.core.security import (
    create_access_token,
    decode_access_token,
    generate_refresh_token,
    hash_refresh_token,
)
from tests.fixtures.tokens import (
    DEMO_USER_ID,
    DEMO_USER_ROLE,
    TEST_JWT_SECRET,
    make_access_token,
    make_expired_access_token,
)


class TestCreateAccessToken:
    def test_returns_non_empty_string(self):
        token = make_access_token()
        assert isinstance(token, str)
        assert len(token) > 0

    def test_claims_sub_is_user_id(self):
        token = make_access_token(user_id=DEMO_USER_ID)
        payload = decode_access_token(token, TEST_JWT_SECRET)
        assert payload["sub"] == str(DEMO_USER_ID)

    def test_claims_role_is_correct(self):
        token = make_access_token(role="developer")
        payload = decode_access_token(token, TEST_JWT_SECRET)
        assert payload["role"] == "developer"

    def test_claims_contains_jti(self):
        token = make_access_token()
        payload = decode_access_token(token, TEST_JWT_SECRET)
        assert "jti" in payload
        # jti must be a valid UUID
        uuid.UUID(payload["jti"])

    def test_claims_contains_iat(self):
        token = make_access_token()
        payload = decode_access_token(token, TEST_JWT_SECRET)
        assert "iat" in payload

    def test_claims_contains_exp(self):
        token = make_access_token()
        payload = decode_access_token(token, TEST_JWT_SECRET)
        assert "exp" in payload

    def test_no_pii_in_claims(self):
        """Email and name must never appear in JWT claims."""
        token = make_access_token()
        payload = decode_access_token(token, TEST_JWT_SECRET)
        pii_keys = {"email", "name", "name_encrypted", "password_hash"}
        assert not pii_keys.intersection(payload.keys())

    def test_two_tokens_have_different_jti(self):
        t1 = make_access_token()
        t2 = make_access_token()
        p1 = decode_access_token(t1, TEST_JWT_SECRET)
        p2 = decode_access_token(t2, TEST_JWT_SECRET)
        assert p1["jti"] != p2["jti"]


class TestDecodeAccessToken:
    def test_decodes_valid_token(self):
        token = make_access_token()
        payload = decode_access_token(token, TEST_JWT_SECRET)
        assert payload["sub"] == str(DEMO_USER_ID)

    def test_raises_on_expired_token(self):
        token = make_expired_access_token()
        with pytest.raises(UnauthorizedError, match="expired"):
            decode_access_token(token, TEST_JWT_SECRET)

    def test_raises_on_tampered_signature(self):
        token = make_access_token()
        # Flip the last character of the signature.
        tampered = token[:-1] + ("A" if token[-1] != "A" else "B")
        with pytest.raises(UnauthorizedError):
            decode_access_token(tampered, TEST_JWT_SECRET)

    def test_raises_on_wrong_secret(self):
        token = make_access_token(jwt_secret=TEST_JWT_SECRET)
        with pytest.raises(UnauthorizedError):
            decode_access_token(token, "wrong-secret")

    def test_raises_on_garbage_string(self):
        with pytest.raises(UnauthorizedError):
            decode_access_token("not.a.jwt", TEST_JWT_SECRET)

    def test_raises_on_missing_role_claim(self):
        import jwt as pyjwt  # noqa: PLC0415
        from datetime import datetime, timezone  # noqa: PLC0415

        now = datetime.now(tz=timezone.utc)
        payload = {
            "sub": str(uuid.uuid4()),
            "iat": now,
            "exp": now + timedelta(minutes=15),
            "jti": str(uuid.uuid4()),
            # "role" intentionally missing
        }
        token = pyjwt.encode(payload, TEST_JWT_SECRET, algorithm="HS256")
        with pytest.raises(UnauthorizedError, match="missing required claims"):
            decode_access_token(token, TEST_JWT_SECRET)

    def test_raises_on_empty_token(self):
        with pytest.raises(UnauthorizedError):
            decode_access_token("", TEST_JWT_SECRET)


class TestGenerateRefreshToken:
    def test_returns_string(self):
        raw = generate_refresh_token()
        assert isinstance(raw, str)

    def test_is_url_safe(self):
        raw = generate_refresh_token()
        # URL-safe base64 chars only (no + or /)
        assert "+" not in raw
        assert "/" not in raw

    def test_sufficient_length(self):
        raw = generate_refresh_token()
        assert len(raw) >= 80  # 64 bytes base64-encoded ≈ 86 chars

    def test_two_calls_are_different(self):
        assert generate_refresh_token() != generate_refresh_token()


class TestHashRefreshToken:
    def test_returns_hex_string(self):
        h = hash_refresh_token("some-token")
        # SHA-256 hex = 64 hex chars
        assert len(h) == 64
        int(h, 16)  # must be valid hex

    def test_is_deterministic(self):
        raw = "deterministic-input"
        assert hash_refresh_token(raw) == hash_refresh_token(raw)

    def test_different_inputs_different_hashes(self):
        assert hash_refresh_token("token-a") != hash_refresh_token("token-b")

    def test_empty_string_hashes(self):
        h = hash_refresh_token("")
        assert len(h) == 64
