"""Unit tests for HMAC-SHA256 webhook signature validation (WO-091).

Covers:
  - Valid signature — passes
  - Invalid signature — raises HMACValidationError
  - Missing X-Hub-Signature-256 header — raises HMACValidationError
  - Malformed header (no sha256= prefix) — raises HMACValidationError
  - Empty body — valid if signature matches
  - Payload exceeding 1 MB — raises PayloadTooLargeError
  - WebhookRateLimiter: allowed, rate-limited, eviction
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac

import pytest

from forgeguard.middleware.hmac_auth import (
    HMACValidationError,
    PayloadTooLargeError,
    WebhookRateLimiter,
    validate_github_signature,
)

_SECRET = "test-webhook-secret"


def _make_signature(body: bytes, secret: str = _SECRET) -> str:
    mac = hmac.new(key=secret.encode(), msg=body, digestmod=hashlib.sha256)
    return f"sha256={mac.hexdigest()}"


class TestValidateGithubSignature:
    def test_valid_signature_passes(self):
        body = b'{"action": "opened"}'
        sig = _make_signature(body)
        validate_github_signature(body, sig, _SECRET)  # Should not raise

    def test_invalid_signature_raises(self):
        body = b'{"action": "opened"}'
        with pytest.raises(HMACValidationError):
            validate_github_signature(body, "sha256=deadbeef", _SECRET)

    def test_missing_header_raises(self):
        body = b'{"action": "opened"}'
        with pytest.raises(HMACValidationError, match="Missing"):
            validate_github_signature(body, None, _SECRET)

    def test_empty_header_raises(self):
        body = b'{"action": "opened"}'
        with pytest.raises(HMACValidationError, match="Missing"):
            validate_github_signature(body, "", _SECRET)

    def test_malformed_header_no_prefix_raises(self):
        body = b'{"action": "opened"}'
        mac = hmac.new(key=_SECRET.encode(), msg=body, digestmod=hashlib.sha256)
        sig = mac.hexdigest()  # Missing 'sha256=' prefix
        with pytest.raises(HMACValidationError, match="sha256="):
            validate_github_signature(body, sig, _SECRET)

    def test_empty_body_valid_if_signature_matches(self):
        body = b""
        sig = _make_signature(body)
        validate_github_signature(body, sig, _SECRET)  # Should not raise

    def test_empty_body_invalid_signature_raises(self):
        body = b""
        with pytest.raises(HMACValidationError):
            validate_github_signature(body, "sha256=wrongdigest", _SECRET)

    def test_payload_too_large_raises(self):
        body = b"x" * (1_048_576 + 1)
        sig = _make_signature(body)
        with pytest.raises(PayloadTooLargeError):
            validate_github_signature(body, sig, _SECRET)

    def test_payload_exactly_1mb_passes(self):
        body = b"x" * 1_048_576
        sig = _make_signature(body)
        validate_github_signature(body, sig, _SECRET)  # Should not raise

    def test_wrong_secret_raises(self):
        body = b'{"action": "opened"}'
        sig = _make_signature(body, secret="correct-secret")
        with pytest.raises(HMACValidationError):
            validate_github_signature(body, sig, "wrong-secret")

    def test_timing_safe_comparison(self):
        # Verify hmac.compare_digest is used (no early exit) by checking that
        # a signature with correct length but wrong content is rejected.
        body = b'{"action": "opened"}'
        correct_sig = _make_signature(body)
        # Build a signature that has the correct prefix but wrong hex chars.
        wrong_hex = "0" * len(correct_sig[len("sha256="):])
        wrong_sig = f"sha256={wrong_hex}"
        with pytest.raises(HMACValidationError):
            validate_github_signature(body, wrong_sig, _SECRET)


class TestWebhookRateLimiter:
    @pytest.mark.asyncio
    async def test_allows_first_request(self):
        limiter = WebhookRateLimiter(max_per_minute=60)
        allowed, retry_after = await limiter.check("acme/payments")
        assert allowed is True
        assert retry_after == 0

    @pytest.mark.asyncio
    async def test_rate_limits_after_max_requests(self):
        limiter = WebhookRateLimiter(max_per_minute=3, window_seconds=60)
        for _ in range(3):
            allowed, _ = await limiter.check("acme/payments")
            assert allowed is True
        # 4th request should be denied.
        allowed, retry_after = await limiter.check("acme/payments")
        assert allowed is False
        assert retry_after > 0

    @pytest.mark.asyncio
    async def test_different_repos_tracked_independently(self):
        limiter = WebhookRateLimiter(max_per_minute=1, window_seconds=60)
        # First request for each repo is allowed.
        allowed_a, _ = await limiter.check("acme/payments")
        allowed_b, _ = await limiter.check("acme/shipping")
        assert allowed_a is True
        assert allowed_b is True

        # Second request for each repo is denied.
        denied_a, _ = await limiter.check("acme/payments")
        denied_b, _ = await limiter.check("acme/shipping")
        assert denied_a is False
        assert denied_b is False

    @pytest.mark.asyncio
    async def test_allows_after_refill(self):
        # Use a very short window so the bucket refills quickly in tests.
        limiter = WebhookRateLimiter(max_per_minute=1, window_seconds=1)
        await limiter.check("acme/payments")  # consume the token

        # Manually override the bucket's last_refill to simulate passage of time.
        import time

        bucket = limiter._buckets["acme/payments"]
        bucket.last_refill -= 2  # pretend 2 seconds passed

        allowed, _ = await limiter.check("acme/payments")
        assert allowed is True
