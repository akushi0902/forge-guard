"""Unit tests for WebhookProcessor and parse_pr_payload (WO-091).

Covers:
  - parse_pr_payload: valid payload, all tracked actions, missing fields
  - WebhookProcessor.check_idempotency: returns False for new, True for duplicate
  - WebhookProcessor.record_received / mark_processed / mark_ignored
  - WebhookProcessor.lookup_service: match and no-match
  - WebhookProcessor.create_assessment: inserts with trigger_type='github_webhook'
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from forgeguard.services.webhook import (
    TRACKED_PR_ACTIONS,
    WebhookParseError,
    WebhookProcessor,
    parse_pr_payload,
)
from tests.fixtures.github_webhook_payloads import (
    malformed_payload,
    pr_closed_payload,
    pr_labeled_payload,
    pr_opened_payload,
    pr_reopened_payload,
    pr_synchronize_payload,
)


# ---------------------------------------------------------------------------
# parse_pr_payload
# ---------------------------------------------------------------------------

class TestParsePrPayload:
    def test_opened_payload(self):
        data = parse_pr_payload(pr_opened_payload())
        assert data["action"] == "opened"
        assert data["repository"] == "acme/payments"
        assert data["owner"] == "acme"
        assert data["repo"] == "payments"
        assert data["pr_number"] == 42
        assert data["head_sha"] == "abc1234567890abcdef1234567890abcdef12345"
        assert "html_url" in data
        assert "repo_html_url" in data

    def test_synchronize_payload(self):
        data = parse_pr_payload(pr_synchronize_payload())
        assert data["action"] == "synchronize"

    def test_reopened_payload(self):
        data = parse_pr_payload(pr_reopened_payload())
        assert data["action"] == "reopened"

    def test_closed_payload(self):
        data = parse_pr_payload(pr_closed_payload())
        assert data["action"] == "closed"
        assert data["action"] not in TRACKED_PR_ACTIONS

    def test_labeled_payload(self):
        data = parse_pr_payload(pr_labeled_payload())
        assert data["action"] == "labeled"
        assert data["action"] not in TRACKED_PR_ACTIONS

    def test_missing_pull_request_key_raises(self):
        payload = {"action": "opened", "repository": {}}
        with pytest.raises(WebhookParseError):
            parse_pr_payload(payload)

    def test_missing_repository_key_raises(self):
        with pytest.raises(WebhookParseError):
            parse_pr_payload(malformed_payload())

    def test_missing_head_sha_raises(self):
        payload = pr_opened_payload()
        del payload["pull_request"]["head"]["sha"]
        with pytest.raises(WebhookParseError):
            parse_pr_payload(payload)

    def test_tracked_pr_actions_set(self):
        assert "opened" in TRACKED_PR_ACTIONS
        assert "synchronize" in TRACKED_PR_ACTIONS
        assert "reopened" in TRACKED_PR_ACTIONS
        assert "closed" not in TRACKED_PR_ACTIONS
        assert "labeled" not in TRACKED_PR_ACTIONS


# ---------------------------------------------------------------------------
# WebhookProcessor helpers
# ---------------------------------------------------------------------------

def _make_processor() -> tuple[WebhookProcessor, AsyncMock, AsyncMock]:
    """Return (processor, mock_pool, mock_audit) for unit tests."""
    mock_pool = AsyncMock()
    mock_conn = AsyncMock()
    mock_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)

    mock_audit = AsyncMock()
    mock_audit.log_event = AsyncMock()

    processor = WebhookProcessor(mock_pool, mock_audit)
    return processor, mock_pool, mock_audit


class TestCheckIdempotency:
    @pytest.mark.asyncio
    async def test_returns_false_for_new_delivery(self):
        processor, mock_pool, _ = _make_processor()
        mock_conn = mock_pool.acquire.return_value.__aenter__.return_value
        mock_conn.fetchrow.return_value = None  # No existing record

        result = await processor.check_idempotency("new-delivery-id")
        assert result is False

    @pytest.mark.asyncio
    async def test_returns_true_for_duplicate_delivery(self):
        processor, mock_pool, _ = _make_processor()
        mock_conn = mock_pool.acquire.return_value.__aenter__.return_value
        mock_conn.fetchrow.return_value = {
            "id": str(uuid.uuid4()),
            "processing_status": "processed",
        }

        result = await processor.check_idempotency("existing-delivery-id")
        assert result is True


class TestRecordReceived:
    @pytest.mark.asyncio
    async def test_inserts_record_and_logs_audit(self):
        processor, mock_pool, mock_audit = _make_processor()
        mock_conn = mock_pool.acquire.return_value.__aenter__.return_value
        mock_conn.execute = AsyncMock()

        event_id = await processor.record_received(
            delivery_id="test-delivery-123",
            event_type="pull_request",
            repository="acme/payments",
            payload_summary={"action": "opened"},
        )

        assert isinstance(event_id, uuid.UUID)
        mock_conn.execute.assert_called_once()
        mock_audit.log_event.assert_called_once()
        call_kwargs = mock_audit.log_event.call_args.kwargs
        assert call_kwargs["action"] == "webhook_received"
        assert call_kwargs["resource_type"] == "webhook_event"


class TestMarkProcessed:
    @pytest.mark.asyncio
    async def test_updates_status_and_assessment_id(self):
        processor, mock_pool, _ = _make_processor()
        mock_conn = mock_pool.acquire.return_value.__aenter__.return_value
        mock_conn.execute = AsyncMock()

        event_id = uuid.uuid4()
        assessment_id = uuid.uuid4()
        await processor.mark_processed(event_id, assessment_id=assessment_id)

        mock_conn.execute.assert_called_once()
        args = mock_conn.execute.call_args.args
        assert "UPDATE webhook_events" in args[0]


class TestMarkIgnored:
    @pytest.mark.asyncio
    async def test_updates_status_and_logs_audit(self):
        processor, mock_pool, mock_audit = _make_processor()
        mock_conn = mock_pool.acquire.return_value.__aenter__.return_value
        mock_conn.execute = AsyncMock()

        event_id = uuid.uuid4()
        await processor.mark_ignored(event_id, "not a PR event")

        mock_conn.execute.assert_called_once()
        mock_audit.log_event.assert_called_once()
        call_kwargs = mock_audit.log_event.call_args.kwargs
        assert call_kwargs["action"] == "webhook_ignored"


class TestLookupService:
    @pytest.mark.asyncio
    async def test_returns_service_on_exact_match(self):
        processor, mock_pool, _ = _make_processor()
        mock_conn = mock_pool.acquire.return_value.__aenter__.return_value
        service_id = uuid.uuid4()
        mock_conn.fetchrow.return_value = {"id": service_id, "name": "payments-service"}

        result = await processor.lookup_service("https://github.com/acme/payments")

        assert result is not None
        assert result["name"] == "payments-service"

    @pytest.mark.asyncio
    async def test_returns_none_when_no_match(self):
        processor, mock_pool, _ = _make_processor()
        mock_conn = mock_pool.acquire.return_value.__aenter__.return_value
        mock_conn.fetchrow.return_value = None

        result = await processor.lookup_service("https://github.com/acme/unregistered")

        assert result is None

    @pytest.mark.asyncio
    async def test_uses_exact_match_not_partial(self):
        processor, mock_pool, _ = _make_processor()
        mock_conn = mock_pool.acquire.return_value.__aenter__.return_value
        mock_conn.fetchrow.return_value = None

        # Partial URL should not match
        await processor.lookup_service("https://github.com/acme")
        call_args = mock_conn.fetchrow.call_args
        # The WHERE clause should use = not LIKE
        assert "= $1" in call_args.args[0]


class TestCreateAssessment:
    @pytest.mark.asyncio
    async def test_inserts_with_webhook_trigger_type(self):
        processor, mock_pool, mock_audit = _make_processor()
        mock_conn = mock_pool.acquire.return_value.__aenter__.return_value
        mock_conn.execute = AsyncMock()

        service_id = uuid.uuid4()
        assessment_id = await processor.create_assessment(
            service_id=service_id,
            commit_sha="abc1234",
            pr_reference="https://github.com/acme/payments/pull/42",
        )

        assert isinstance(assessment_id, uuid.UUID)
        mock_conn.execute.assert_called_once()
        sql = mock_conn.execute.call_args.args[0]
        assert "github_webhook" in sql

        mock_audit.log_event.assert_called_once()
        call_kwargs = mock_audit.log_event.call_args.kwargs
        assert call_kwargs["action"] == "assessment_triggered"
        assert call_kwargs["details"]["trigger_type"] == "github_webhook"
