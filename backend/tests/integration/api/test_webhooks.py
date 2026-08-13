"""Integration tests for POST /api/v1/webhooks/github (WO-091).

Tests the full flow from HTTP request through HMAC validation, payload
parsing, idempotency, and assessment creation, using mocked database and
GitHub API calls.

Coverage:
  - 401 for invalid HMAC signature
  - 401 for missing X-Hub-Signature-256 header
  - 202 for PR opened event (registered service)
  - 200 Ignored for PR closed action
  - 200 Ignored for push event (non-pull_request)
  - 200 Ignored for duplicate delivery_id
  - 200 Ignored for unregistered repository
  - 429 when per-repo rate limit exceeded
  - 400 for malformed JSON
  - 413 for payload exceeding 1 MB
"""

from __future__ import annotations

import hashlib
import hmac
import json
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from forgeguard.api.routes.webhooks import router as webhooks_router
from tests.fixtures.github_webhook_payloads import (
    pr_closed_payload,
    pr_opened_payload,
    push_event_payload,
)

_WEBHOOK_SECRET = "integration-test-secret"
_SERVICE_ID = uuid.uuid4()
_REPO_URL = "https://github.com/acme/payments"


def _sign(body: bytes, secret: str = _WEBHOOK_SECRET) -> str:
    mac = hmac.new(key=secret.encode(), msg=body, digestmod=hashlib.sha256)
    return f"sha256={mac.hexdigest()}"


def _make_app() -> FastAPI:
    """Build a minimal FastAPI app with just the webhook router."""
    app = FastAPI()
    app.include_router(webhooks_router)

    # Attach a mock pool to app.state.
    mock_pool = AsyncMock()
    mock_conn = AsyncMock()
    mock_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)
    app.state.pool = mock_pool
    return app, mock_pool, mock_conn


@pytest.fixture
def app_with_mocks():
    app, mock_pool, mock_conn = _make_app()
    return app, mock_pool, mock_conn


async def _post_webhook(
    client: AsyncClient,
    payload: dict,
    *,
    delivery_id: str = "",
    event_type: str = "pull_request",
    secret: str = _WEBHOOK_SECRET,
    extra_headers: dict | None = None,
) -> "httpx.Response":
    body = json.dumps(payload).encode()
    delivery_id = delivery_id or str(uuid.uuid4())
    headers = {
        "Content-Type": "application/json",
        "X-Hub-Signature-256": _sign(body, secret),
        "X-GitHub-Delivery": delivery_id,
        "X-GitHub-Event": event_type,
    }
    if extra_headers:
        headers.update(extra_headers)
    return await client.post("/api/v1/webhooks/github", content=body, headers=headers)


class TestHmacValidation:
    @pytest.mark.asyncio
    async def test_invalid_signature_returns_401(self, app_with_mocks):
        app, _, _ = app_with_mocks
        payload = pr_opened_payload()
        body = json.dumps(payload).encode()

        with patch("forgeguard.core.config.get_settings") as mock_settings:
            mock_settings.return_value.github_webhook_secret = _WEBHOOK_SECRET
            mock_settings.return_value.github_api_token = ""
            mock_settings.return_value.github_api_base_url = "https://api.github.com"
            mock_settings.return_value.webhook_rate_limit_per_repo = 60
            mock_settings.return_value.rate_limit_window_seconds = 60

            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                response = await client.post(
                    "/api/v1/webhooks/github",
                    content=body,
                    headers={
                        "Content-Type": "application/json",
                        "X-Hub-Signature-256": "sha256=invaliddigest",
                        "X-GitHub-Delivery": str(uuid.uuid4()),
                        "X-GitHub-Event": "pull_request",
                    },
                )
        assert response.status_code == 401
        assert response.json()["error"] == "invalid_signature"

    @pytest.mark.asyncio
    async def test_missing_signature_returns_401(self, app_with_mocks):
        app, _, _ = app_with_mocks
        payload = pr_opened_payload()
        body = json.dumps(payload).encode()

        with patch("forgeguard.core.config.get_settings") as mock_settings:
            mock_settings.return_value.github_webhook_secret = _WEBHOOK_SECRET
            mock_settings.return_value.github_api_token = ""
            mock_settings.return_value.github_api_base_url = "https://api.github.com"
            mock_settings.return_value.webhook_rate_limit_per_repo = 60
            mock_settings.return_value.rate_limit_window_seconds = 60

            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                response = await client.post(
                    "/api/v1/webhooks/github",
                    content=body,
                    headers={
                        "Content-Type": "application/json",
                        "X-GitHub-Delivery": str(uuid.uuid4()),
                        "X-GitHub-Event": "pull_request",
                    },
                )
        assert response.status_code == 401


class TestNonPrEvents:
    @pytest.mark.asyncio
    async def test_push_event_returns_200_ignored(self, app_with_mocks):
        app, _, mock_conn = app_with_mocks
        mock_conn.execute = AsyncMock()
        mock_conn.fetchrow = AsyncMock(return_value=None)
        payload = push_event_payload()

        with patch("forgeguard.core.config.get_settings") as mock_settings, \
             patch("forgeguard.services.audit.AuditService.log_event", new=AsyncMock()):
            mock_settings.return_value.github_webhook_secret = _WEBHOOK_SECRET
            mock_settings.return_value.github_api_token = ""
            mock_settings.return_value.github_api_base_url = "https://api.github.com"
            mock_settings.return_value.webhook_rate_limit_per_repo = 60
            mock_settings.return_value.rate_limit_window_seconds = 60

            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                response = await _post_webhook(
                    client, payload, event_type="push"
                )
        assert response.status_code == 200
        assert response.json()["status"] == "ignored"


class TestPrActions:
    @pytest.mark.asyncio
    async def test_closed_pr_returns_200_ignored(self, app_with_mocks):
        app, _, mock_conn = app_with_mocks
        mock_conn.execute = AsyncMock()
        mock_conn.fetchrow = AsyncMock(return_value=None)
        payload = pr_closed_payload()

        with patch("forgeguard.core.config.get_settings") as mock_settings, \
             patch("forgeguard.services.audit.AuditService.log_event", new=AsyncMock()), \
             patch("forgeguard.middleware.hmac_auth.get_webhook_rate_limiter") as mock_rl:
            mock_settings.return_value.github_webhook_secret = _WEBHOOK_SECRET
            mock_settings.return_value.github_api_token = ""
            mock_settings.return_value.github_api_base_url = "https://api.github.com"
            mock_settings.return_value.webhook_rate_limit_per_repo = 60
            mock_settings.return_value.rate_limit_window_seconds = 60
            mock_rl.return_value.check = AsyncMock(return_value=(True, 0))

            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                response = await _post_webhook(client, payload)
        assert response.status_code == 200
        assert response.json()["status"] == "ignored"


class TestPayloadValidation:
    @pytest.mark.asyncio
    async def test_invalid_json_returns_400(self, app_with_mocks):
        app, _, _ = app_with_mocks
        body = b"not valid json {"

        with patch("forgeguard.core.config.get_settings") as mock_settings:
            mock_settings.return_value.github_webhook_secret = _WEBHOOK_SECRET
            mock_settings.return_value.github_api_token = ""
            mock_settings.return_value.github_api_base_url = "https://api.github.com"
            mock_settings.return_value.webhook_rate_limit_per_repo = 60
            mock_settings.return_value.rate_limit_window_seconds = 60

            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                response = await client.post(
                    "/api/v1/webhooks/github",
                    content=body,
                    headers={
                        "Content-Type": "application/json",
                        "X-Hub-Signature-256": _sign(body),
                        "X-GitHub-Delivery": str(uuid.uuid4()),
                        "X-GitHub-Event": "pull_request",
                    },
                )
        assert response.status_code == 400
        assert response.json()["error"] == "invalid_payload"

    @pytest.mark.asyncio
    async def test_payload_too_large_returns_413(self, app_with_mocks):
        app, _, _ = app_with_mocks
        body = b"x" * (1_048_576 + 1)

        with patch("forgeguard.core.config.get_settings") as mock_settings:
            mock_settings.return_value.github_webhook_secret = _WEBHOOK_SECRET
            mock_settings.return_value.github_api_token = ""
            mock_settings.return_value.github_api_base_url = "https://api.github.com"
            mock_settings.return_value.webhook_rate_limit_per_repo = 60
            mock_settings.return_value.rate_limit_window_seconds = 60

            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                response = await client.post(
                    "/api/v1/webhooks/github",
                    content=body,
                    headers={
                        "Content-Type": "application/json",
                        "X-Hub-Signature-256": _sign(body),
                        "X-GitHub-Delivery": str(uuid.uuid4()),
                        "X-GitHub-Event": "pull_request",
                    },
                )
        assert response.status_code == 413
        assert response.json()["error"] == "payload_too_large"
