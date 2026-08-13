"""Authentication edge-case tests (WO-098).

Verifies that ``AuthenticationMiddleware`` correctly enforces JWT requirements
across the full ASGI stack using the httpx ``AsyncClient`` + ``ASGITransport``.

Authentication flow: the middleware reads the ``access_token`` httpOnly cookie
(NOT the ``Authorization`` header).  All 401 cases below omit the cookie or
supply an invalid token.

Run:
    pytest tests/compliance/test_authentication.py -v
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_jwt(
    payload: dict,
    secret: str,
    algorithm: str = "HS256",
) -> str:
    """Sign a raw JWT payload with PyJWT."""
    import jwt  # PyJWT

    return jwt.encode(payload, secret, algorithm=algorithm)


def _base_payload(*, role: str = "developer", secret: str, exp_delta: timedelta | None = None) -> dict:
    """Build a minimal valid JWT payload."""
    if exp_delta is None:
        exp_delta = timedelta(minutes=15)
    now = datetime.now(tz=timezone.utc)
    return {
        "sub": str(uuid.uuid4()),
        "role": role,
        "iat": now,
        "exp": now + exp_delta,
        "jti": str(uuid.uuid4()),
    }


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# A protected endpoint that all authenticated users can reach (service.view)
_PROTECTED_ENDPOINT = "/api/v1/services"

# OPTIONS to a protected endpoint — must succeed without auth
_PREFLIGHT_ENDPOINT = "/api/v1/services"


# ===========================================================================
# 1. Unauthenticated requests
# ===========================================================================

@pytest.mark.unit
class TestUnauthenticated:
    """No ``access_token`` cookie present — all protected endpoints return 401."""

    @pytest.mark.asyncio
    async def test_missing_cookie_returns_401(self, test_client):
        """Request without any cookie returns 401."""
        response = await test_client.get(_PROTECTED_ENDPOINT)
        assert response.status_code == 401
        body = response.json()
        assert "detail" in body

    @pytest.mark.asyncio
    async def test_empty_cookie_value_returns_401(self, test_client):
        """``access_token`` cookie present but empty string returns 401."""
        response = await test_client.get(
            _PROTECTED_ENDPOINT,
            cookies={"access_token": ""},
        )
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_whitespace_cookie_value_returns_401(self, test_client):
        """``access_token`` cookie containing only whitespace returns 401."""
        response = await test_client.get(
            _PROTECTED_ENDPOINT,
            cookies={"access_token": "   "},
        )
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_authorization_header_alone_returns_401(self, test_client, test_settings):
        """Authorization Bearer header (without cookie) does NOT authenticate."""
        token = _make_jwt(_base_payload(secret=test_settings.jwt_secret_key), test_settings.jwt_secret_key)
        response = await test_client.get(
            _PROTECTED_ENDPOINT,
            headers={"Authorization": f"Bearer {token}"},
        )
        # The middleware reads cookies only — header alone must not grant access
        assert response.status_code == 401


# ===========================================================================
# 2. Token expiry
# ===========================================================================

@pytest.mark.unit
class TestTokenExpiry:
    """Expired JWTs must return 401 with an expiry-specific message."""

    @pytest.mark.asyncio
    async def test_expired_token_returns_401(self, test_client, test_settings):
        """JWT with exp in the past returns 401."""
        payload = _base_payload(
            secret=test_settings.jwt_secret_key,
            exp_delta=timedelta(seconds=-1),
        )
        token = _make_jwt(payload, test_settings.jwt_secret_key)
        response = await test_client.get(
            _PROTECTED_ENDPOINT,
            cookies={"access_token": token},
        )
        assert response.status_code == 401
        body = response.json()
        assert "detail" in body
        detail = body["detail"].lower()
        assert "expir" in detail or "expired" in detail or "token" in detail

    @pytest.mark.asyncio
    async def test_far_future_token_is_accepted(self, test_client, test_settings):
        """JWT with a far-future exp is accepted (not 401)."""
        payload = _base_payload(
            secret=test_settings.jwt_secret_key,
            exp_delta=timedelta(days=365),
        )
        token = _make_jwt(payload, test_settings.jwt_secret_key)
        response = await test_client.get(
            _PROTECTED_ENDPOINT,
            cookies={"access_token": token},
        )
        assert response.status_code != 401


# ===========================================================================
# 3. Invalid / tampered tokens
# ===========================================================================

@pytest.mark.unit
class TestInvalidTokens:
    """Malformed, tampered, or wrong-secret JWTs must return 401."""

    @pytest.mark.asyncio
    async def test_wrong_secret_returns_401(self, test_client, test_settings):
        """JWT signed with a different secret returns 401."""
        wrong_secret = "completely-different-secret-key-12345"
        payload = _base_payload(secret=wrong_secret)
        token = _make_jwt(payload, wrong_secret)
        response = await test_client.get(
            _PROTECTED_ENDPOINT,
            cookies={"access_token": token},
        )
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_malformed_jwt_string_returns_401(self, test_client):
        """Random string that is not a JWT returns 401."""
        response = await test_client.get(
            _PROTECTED_ENDPOINT,
            cookies={"access_token": "this.is.not.a.jwt"},
        )
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_truncated_jwt_returns_401(self, test_client, test_settings):
        """JWT with missing signature segment returns 401."""
        payload = _base_payload(secret=test_settings.jwt_secret_key)
        token = _make_jwt(payload, test_settings.jwt_secret_key)
        # Strip the signature part
        truncated = ".".join(token.split(".")[:2])
        response = await test_client.get(
            _PROTECTED_ENDPOINT,
            cookies={"access_token": truncated},
        )
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_tampered_payload_returns_401(self, test_client, test_settings):
        """JWT with modified payload (but original signature) returns 401."""
        import base64

        payload = _base_payload(secret=test_settings.jwt_secret_key)
        token = _make_jwt(payload, test_settings.jwt_secret_key)
        parts = token.split(".")

        # Tamper the payload (b64url of modified JSON)
        import json

        bad_payload = json.dumps({"sub": "attacker", "role": "platform_admin"}).encode()
        # Pad to multiple of 4 for urlsafe_b64decode
        bad_b64 = base64.urlsafe_b64encode(bad_payload).rstrip(b"=").decode()
        tampered = f"{parts[0]}.{bad_b64}.{parts[2]}"

        response = await test_client.get(
            _PROTECTED_ENDPOINT,
            cookies={"access_token": tampered},
        )
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_algorithm_none_attack_returns_401(self, test_client):
        """alg=none attack (unsigned JWT) returns 401."""
        import base64
        import json

        header = base64.urlsafe_b64encode(
            json.dumps({"alg": "none", "typ": "JWT"}).encode()
        ).rstrip(b"=").decode()
        payload = base64.urlsafe_b64encode(
            json.dumps({
                "sub": "attacker",
                "role": "platform_admin",
                "exp": 9999999999,
            }).encode()
        ).rstrip(b"=").decode()
        token = f"{header}.{payload}."

        response = await test_client.get(
            _PROTECTED_ENDPOINT,
            cookies={"access_token": token},
        )
        assert response.status_code == 401


# ===========================================================================
# 4. Missing JWT claims
# ===========================================================================

@pytest.mark.unit
class TestMissingClaims:
    """JWTs missing required claims return 401."""

    @pytest.mark.asyncio
    async def test_missing_sub_claim_returns_401(self, test_client, test_settings):
        """JWT without 'sub' claim returns 401."""
        payload = _base_payload(secret=test_settings.jwt_secret_key)
        del payload["sub"]
        token = _make_jwt(payload, test_settings.jwt_secret_key)
        response = await test_client.get(
            _PROTECTED_ENDPOINT,
            cookies={"access_token": token},
        )
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_missing_role_claim_returns_401_or_403(self, test_client, test_settings):
        """JWT without 'role' claim results in 401 or 403 (no permissions)."""
        payload = _base_payload(secret=test_settings.jwt_secret_key)
        del payload["role"]
        token = _make_jwt(payload, test_settings.jwt_secret_key)
        response = await test_client.get(
            _PROTECTED_ENDPOINT,
            cookies={"access_token": token},
        )
        # Missing role means no permissions — either 401 (auth fails) or 403 (RBAC deny)
        assert response.status_code in (401, 403)

    @pytest.mark.asyncio
    async def test_unknown_role_value_returns_403(self, test_client, test_settings):
        """JWT with a role that doesn't exist in the RBAC matrix returns 403."""
        payload = _base_payload(secret=test_settings.jwt_secret_key)
        payload["role"] = "super_admin_ghost"
        token = _make_jwt(payload, test_settings.jwt_secret_key)
        response = await test_client.get(
            _PROTECTED_ENDPOINT,
            cookies={"access_token": token},
        )
        # Unknown role has no permissions — RBAC middleware denies with 403
        assert response.status_code == 403


# ===========================================================================
# 5. 401 response body schema
# ===========================================================================

@pytest.mark.unit
class TestAuthErrorResponseSchema:
    """401 responses must contain structured, non-leaking error bodies."""

    @pytest.mark.asyncio
    async def test_401_body_has_detail_field(self, test_client):
        """401 response body contains a 'detail' field."""
        response = await test_client.get(_PROTECTED_ENDPOINT)
        assert response.status_code == 401
        body = response.json()
        assert "detail" in body
        assert isinstance(body["detail"], str)
        assert len(body["detail"]) > 0

    @pytest.mark.asyncio
    async def test_401_body_does_not_leak_internals(self, test_client):
        """401 response body contains no stack traces or SQL fragments."""
        response = await test_client.get(_PROTECTED_ENDPOINT)
        assert response.status_code == 401
        body_str = response.text.lower()
        assert "traceback" not in body_str
        assert "sqlalchemy" not in body_str
        assert "database" not in body_str
        assert "exception" not in body_str

    @pytest.mark.asyncio
    async def test_expired_token_401_mentions_token_or_expiry(self, test_client, test_settings):
        """401 for expired token has an informative detail message."""
        payload = _base_payload(
            secret=test_settings.jwt_secret_key,
            exp_delta=timedelta(seconds=-60),
        )
        token = _make_jwt(payload, test_settings.jwt_secret_key)
        response = await test_client.get(
            _PROTECTED_ENDPOINT,
            cookies={"access_token": token},
        )
        assert response.status_code == 401
        detail = response.json().get("detail", "").lower()
        assert any(word in detail for word in ("expir", "token", "authenticat"))


# ===========================================================================
# 6. CORS OPTIONS preflight bypass
# ===========================================================================

@pytest.mark.unit
class TestCorsOptionsBypass:
    """CORS preflight OPTIONS requests must bypass authentication entirely."""

    @pytest.mark.asyncio
    async def test_options_to_protected_endpoint_not_blocked(self, test_client):
        """OPTIONS request to a protected endpoint returns 200/204, not 401/403."""
        response = await test_client.options(_PROTECTED_ENDPOINT)
        assert response.status_code not in (401, 403)

    @pytest.mark.asyncio
    async def test_options_to_admin_endpoint_not_blocked(self, test_client):
        """OPTIONS request to /api/v1/admin/rbac/users returns 200/204, not 401/403."""
        response = await test_client.options("/api/v1/admin/rbac/users")
        assert response.status_code not in (401, 403)

    @pytest.mark.asyncio
    async def test_options_to_policy_endpoint_not_blocked(self, test_client):
        """OPTIONS preflight to POST /api/v1/policies not blocked by auth or RBAC."""
        response = await test_client.options("/api/v1/policies")
        assert response.status_code not in (401, 403)

    @pytest.mark.asyncio
    async def test_public_paths_require_no_auth(self, test_client):
        """Public endpoints (webhook) are accessible without any cookie."""
        response = await test_client.get("/api/v1/health")
        # Health check is a public path — no 401
        assert response.status_code != 401

    @pytest.mark.asyncio
    async def test_valid_token_returns_non_401(self, test_client, test_settings):
        """Valid JWT in the access_token cookie is accepted (sanity check)."""
        import jwt as pyjwt

        payload = _base_payload(secret=test_settings.jwt_secret_key)
        token = pyjwt.encode(payload, test_settings.jwt_secret_key, algorithm="HS256")
        response = await test_client.get(
            _PROTECTED_ENDPOINT,
            cookies={"access_token": token},
        )
        # May be 200, 404, 422 — anything but 401 means auth passed
        assert response.status_code != 401
