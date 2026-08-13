"""HMAC-SHA256 webhook signature validation.

Provides:
  - validate_github_signature()  — constant-time HMAC-SHA256 check for the
    X-Hub-Signature-256 header that GitHub sends with every webhook delivery.
  - Per-repository token bucket rate limiting (60 req/min default).

Security requirements enforced here:
  - hmac.compare_digest() is used for constant-time comparison to prevent
    timing attacks.
  - The webhook secret is never logged, included in error responses, or
    stored anywhere beyond the Settings singleton.
  - Payloads larger than 1 MB are rejected before HMAC computation to
    prevent DoS via large payload.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import time
from dataclasses import dataclass, field

import structlog

logger = structlog.get_logger(__name__)

_MAX_PAYLOAD_BYTES = 1_048_576  # 1 MB


# ---------------------------------------------------------------------------
# HMAC validation
# ---------------------------------------------------------------------------

class HMACValidationError(Exception):
    """Raised when signature validation fails."""


class PayloadTooLargeError(Exception):
    """Raised when the payload exceeds _MAX_PAYLOAD_BYTES."""


def validate_github_signature(
    payload_bytes: bytes,
    signature_header: str | None,
    secret: str,
) -> None:
    """Validate the X-Hub-Signature-256 header against the raw payload body.

    Args:
        payload_bytes:    Raw HTTP request body bytes.
        signature_header: Value of the X-Hub-Signature-256 header.
        secret:           GITHUB_WEBHOOK_SECRET (never logged).

    Raises:
        PayloadTooLargeError: If payload exceeds 1 MB.
        HMACValidationError:  If header is missing, malformed, or signature
                              does not match (constant-time comparison).
    """
    if len(payload_bytes) > _MAX_PAYLOAD_BYTES:
        raise PayloadTooLargeError(
            f"Webhook payload size {len(payload_bytes)} exceeds limit of {_MAX_PAYLOAD_BYTES} bytes"
        )

    if not signature_header:
        raise HMACValidationError("Missing X-Hub-Signature-256 header")

    if not signature_header.startswith("sha256="):
        raise HMACValidationError("X-Hub-Signature-256 must begin with 'sha256='")

    received_digest = signature_header[len("sha256="):]

    mac = hmac.new(
        key=secret.encode("utf-8"),
        msg=payload_bytes,
        digestmod=hashlib.sha256,
    )
    expected_digest = mac.hexdigest()

    if not hmac.compare_digest(expected_digest, received_digest):
        raise HMACValidationError("X-Hub-Signature-256 signature mismatch")


# ---------------------------------------------------------------------------
# Per-repository token bucket rate limiter
# ---------------------------------------------------------------------------

@dataclass
class _RepoBucket:
    """Token bucket for one repository full_name."""

    tokens: float
    max_tokens: int
    refill_rate: float
    last_refill: float
    last_accessed: float = field(default_factory=time.monotonic)

    def consume(self) -> tuple[bool, int]:
        now = time.monotonic()
        elapsed = now - self.last_refill
        self.tokens = min(float(self.max_tokens), self.tokens + elapsed * self.refill_rate)
        self.last_refill = now
        self.last_accessed = now
        if self.tokens >= 1.0:
            self.tokens -= 1.0
            return True, 0
        retry_after = max(1, int((1.0 - self.tokens) / self.refill_rate) + 1)
        return False, retry_after


class WebhookRateLimiter:
    """Per-repository token bucket rate limiter for the webhook endpoint.

    Args:
        max_per_minute: Maximum deliveries per minute per repository (default 60).
        window_seconds: Token refill window in seconds (default 60).
    """

    def __init__(self, max_per_minute: int = 60, window_seconds: int = 60) -> None:
        self._max = max_per_minute
        self._window = window_seconds
        self._buckets: dict[str, _RepoBucket] = {}
        self._lock: asyncio.Lock = asyncio.Lock()

    async def check(self, repository: str) -> tuple[bool, int]:
        """Attempt to consume one token for *repository*.

        Returns:
            (True, 0)               — allowed
            (False, retry_after)    — rate limited; retry after N seconds
        """
        async with self._lock:
            self._evict_expired()
            bucket = self._buckets.get(repository)
            if bucket is None:
                refill_rate = self._max / self._window
                bucket = _RepoBucket(
                    tokens=float(self._max),
                    max_tokens=self._max,
                    refill_rate=refill_rate,
                    last_refill=time.monotonic(),
                )
                self._buckets[repository] = bucket
            return bucket.consume()

    def _evict_expired(self) -> None:
        ttl = self._window * 2
        now = time.monotonic()
        expired = [k for k, v in self._buckets.items() if (now - v.last_accessed) > ttl]
        for k in expired:
            del self._buckets[k]


# Module-level singleton — one rate limiter shared across all requests.
_webhook_rate_limiter: WebhookRateLimiter | None = None


def get_webhook_rate_limiter() -> WebhookRateLimiter:
    """Return the module-level WebhookRateLimiter singleton.

    The instance is created lazily on first call so the Settings are read
    after the app is configured (not at import time).
    """
    global _webhook_rate_limiter  # noqa: PLW0603
    if _webhook_rate_limiter is None:
        from forgeguard.core.config import get_settings  # noqa: PLC0415
        settings = get_settings()
        _webhook_rate_limiter = WebhookRateLimiter(
            max_per_minute=settings.webhook_rate_limit_per_repo,
            window_seconds=settings.rate_limit_window_seconds,
        )
    return _webhook_rate_limiter
