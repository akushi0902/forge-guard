"""Unit tests for ForgeWorkflowHttpAdapter (WO-092).

Coverage targets (>=80%):
    - successful workflow trigger
    - fallback on API failure (4xx, 5xx, timeout, connection error)
    - circuit breaker OPEN → immediate fallback
    - role mapping: CONDITIONAL_APPROVE → tech_lead, BLOCK → tech_lead,
      BLOCK + CRITICAL/SECURITY → security_reviewer
    - security escalation routing
    - status polling: terminal state updates, 404 → timed_out
    - timeout 24h exceeded → timed_out + platform_admin fallback
    - audit log records emitted
    - APPROVE decision → no workflow
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tests.fixtures.forge_workflow_responses import (
    STATUS_APPROVED,
    STATUS_REJECTED,
    STATUS_TIMED_OUT,
    STATUS_NOT_FOUND_BODY,
    TRIGGER_SUCCESS_RESPONSE,
    WORKFLOW_ID,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_adapter(*, base_url="https://forge.example.com", api_key="test-key", circuit_breaker=None):
    from forgeguard.services.ai_engine.circuit_breaker import CircuitBreaker
    from forgeguard.services.forge_workflow import ForgeWorkflowHttpAdapter

    cb = circuit_breaker or CircuitBreaker(
        failure_threshold=5,
        window_seconds=60,
        recovery_timeout=30,
    )
    return ForgeWorkflowHttpAdapter(base_url=base_url, api_key=api_key, circuit_breaker=cb)


def _make_mock_response(status_code: int, json_body: dict):
    resp = MagicMock()
    resp.status_code = status_code
    resp.is_success = 200 <= status_code < 300
    resp.json.return_value = json_body
    return resp


def _make_mock_audit():
    audit = AsyncMock()
    audit.log_event = AsyncMock(return_value=None)
    return audit


def _make_mock_decision_repo():
    repo = AsyncMock()
    repo.update_workflow_status = AsyncMock(return_value=None)
    repo.list_active_workflows = AsyncMock(return_value=[])
    return repo


# ---------------------------------------------------------------------------
# determine_reviewer_role
# ---------------------------------------------------------------------------


class TestDetermineReviewerRole:
    def test_conditional_approve_routes_to_tech_lead(self):
        from forgeguard.services.forge_workflow import ForgeWorkflowAdapter

        assert ForgeWorkflowAdapter.determine_reviewer_role("CONDITIONAL_APPROVE") == "tech_lead"

    def test_block_routes_to_tech_lead(self):
        from forgeguard.services.forge_workflow import ForgeWorkflowAdapter

        assert ForgeWorkflowAdapter.determine_reviewer_role("BLOCK") == "tech_lead"

    def test_approve_defaults_to_tech_lead(self):
        from forgeguard.services.forge_workflow import ForgeWorkflowAdapter

        assert ForgeWorkflowAdapter.determine_reviewer_role("APPROVE") == "tech_lead"

    def test_block_with_critical_security_routes_to_security_reviewer(self):
        from forgeguard.services.forge_workflow import ForgeWorkflowAdapter

        findings = [{"severity": "CRITICAL", "dimension": "SECURITY"}]
        with patch(
            "forgeguard.services.domain.severity.SeverityClassifier.is_escalation_required",
            return_value=True,
        ):
            result = ForgeWorkflowAdapter.determine_reviewer_role("BLOCK", findings=findings)
        assert result == "security_reviewer"

    def test_block_with_non_critical_finding_stays_tech_lead(self):
        from forgeguard.services.forge_workflow import ForgeWorkflowAdapter

        findings = [{"severity": "HIGH", "dimension": "SECURITY"}]
        with patch(
            "forgeguard.services.domain.severity.SeverityClassifier.is_escalation_required",
            return_value=False,
        ):
            result = ForgeWorkflowAdapter.determine_reviewer_role("BLOCK", findings=findings)
        assert result == "tech_lead"

    def test_empty_findings_block_stays_tech_lead(self):
        from forgeguard.services.forge_workflow import ForgeWorkflowAdapter

        result = ForgeWorkflowAdapter.determine_reviewer_role("BLOCK", findings=[])
        assert result == "tech_lead"


# ---------------------------------------------------------------------------
# trigger_workflow: success
# ---------------------------------------------------------------------------


class TestTriggerWorkflowSuccess:
    @pytest.mark.asyncio
    async def test_success_returns_trigger_response(self):
        adapter = _make_adapter()
        audit = _make_mock_audit()

        mock_resp = _make_mock_response(200, TRIGGER_SUCCESS_RESPONSE)

        with patch.object(adapter, "_client") as mock_client_ctx:
            mock_client = AsyncMock()
            mock_client_ctx.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client_ctx.return_value.__aexit__ = AsyncMock(return_value=False)

            with patch.object(adapter._cb, "call", new=AsyncMock(return_value=mock_resp)):
                result = await adapter.trigger_workflow(
                    decision_id=uuid.uuid4(),
                    assessment_id=uuid.uuid4(),
                    decision="CONDITIONAL_APPROVE",
                    reviewer_role="tech_lead",
                    context={"service_id": "svc-1"},
                    audit_svc=audit,
                )

        assert result is not None
        assert result.get("workflow_id") == WORKFLOW_ID
        assert result.get("status") == "pending"

    @pytest.mark.asyncio
    async def test_success_logs_audit_event(self):
        adapter = _make_adapter()
        audit = _make_mock_audit()

        mock_resp = _make_mock_response(200, TRIGGER_SUCCESS_RESPONSE)

        with patch.object(adapter, "_client"):
            with patch.object(adapter._cb, "call", new=AsyncMock(return_value=mock_resp)):
                await adapter.trigger_workflow(
                    decision_id=uuid.uuid4(),
                    assessment_id=uuid.uuid4(),
                    decision="BLOCK",
                    reviewer_role="tech_lead",
                    context={},
                    audit_svc=audit,
                )

        audit.log_event.assert_awaited_once()
        call_kwargs = audit.log_event.call_args.kwargs
        assert call_kwargs.get("action") == "workflow_triggered"
        assert call_kwargs.get("resource_type") == "release_decision"


# ---------------------------------------------------------------------------
# trigger_workflow: fallback paths
# ---------------------------------------------------------------------------


class TestTriggerWorkflowFallback:
    @pytest.mark.asyncio
    async def test_4xx_activates_fallback(self):
        adapter = _make_adapter()
        audit = _make_mock_audit()

        mock_resp = _make_mock_response(400, {"error": "Bad Request"})

        with patch.object(adapter, "_client"):
            with patch.object(adapter._cb, "call", new=AsyncMock(return_value=mock_resp)):
                with patch.object(adapter, "activate_fallback", new=AsyncMock()) as mock_fallback:
                    result = await adapter.trigger_workflow(
                        decision_id=uuid.uuid4(),
                        assessment_id=uuid.uuid4(),
                        decision="BLOCK",
                        reviewer_role="tech_lead",
                        context={},
                        audit_svc=audit,
                    )

        assert result is None
        mock_fallback.assert_awaited_once()
        assert "http_400" in mock_fallback.call_args.kwargs["reason"]

    @pytest.mark.asyncio
    async def test_timeout_activates_fallback(self):
        import httpx

        adapter = _make_adapter()
        audit = _make_mock_audit()

        with patch.object(adapter, "_client"):
            with patch.object(
                adapter._cb,
                "call",
                side_effect=httpx.TimeoutException("timed out"),
            ):
                with patch.object(adapter, "activate_fallback", new=AsyncMock()) as mock_fallback:
                    result = await adapter.trigger_workflow(
                        decision_id=uuid.uuid4(),
                        assessment_id=uuid.uuid4(),
                        decision="BLOCK",
                        reviewer_role="tech_lead",
                        context={},
                    )

        assert result is None
        mock_fallback.assert_awaited_once()
        assert mock_fallback.call_args.kwargs["reason"] == "timeout"

    @pytest.mark.asyncio
    async def test_circuit_open_activates_fallback(self):
        from forgeguard.services.ai_engine.errors import CircuitOpenError

        adapter = _make_adapter()

        with patch.object(
            adapter._cb,
            "call",
            side_effect=CircuitOpenError(state="OPEN", message="circuit is open"),
        ):
            with patch.object(adapter, "activate_fallback", new=AsyncMock()) as mock_fallback:
                result = await adapter.trigger_workflow(
                    decision_id=uuid.uuid4(),
                    assessment_id=uuid.uuid4(),
                    decision="CONDITIONAL_APPROVE",
                    reviewer_role="tech_lead",
                    context={},
                )

        assert result is None
        mock_fallback.assert_awaited_once()
        assert mock_fallback.call_args.kwargs["reason"] == "circuit_open"

    @pytest.mark.asyncio
    async def test_5xx_retries_then_fallback(self):
        adapter = _make_adapter()
        mock_5xx = _make_mock_response(503, {"error": "Service Unavailable"})

        with patch.object(adapter, "_client"):
            with patch.object(
                adapter._cb,
                "call",
                new=AsyncMock(return_value=mock_5xx),
            ):
                with patch.object(adapter, "activate_fallback", new=AsyncMock()) as mock_fallback:
                    result = await adapter.trigger_workflow(
                        decision_id=uuid.uuid4(),
                        assessment_id=uuid.uuid4(),
                        decision="BLOCK",
                        reviewer_role="tech_lead",
                        context={},
                    )

        assert result is None
        mock_fallback.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_connection_error_activates_fallback(self):
        adapter = _make_adapter()

        with patch.object(
            adapter._cb,
            "call",
            side_effect=Exception("connection refused"),
        ):
            with patch.object(adapter, "activate_fallback", new=AsyncMock()) as mock_fallback:
                result = await adapter.trigger_workflow(
                    decision_id=uuid.uuid4(),
                    assessment_id=uuid.uuid4(),
                    decision="BLOCK",
                    reviewer_role="tech_lead",
                    context={},
                )

        assert result is None
        mock_fallback.assert_awaited_once()
        assert mock_fallback.call_args.kwargs["reason"] == "connection_error"


# ---------------------------------------------------------------------------
# get_workflow_status
# ---------------------------------------------------------------------------


class TestGetWorkflowStatus:
    @pytest.mark.asyncio
    async def test_returns_approved_status(self):
        adapter = _make_adapter()
        mock_resp = _make_mock_response(200, STATUS_APPROVED)

        with patch.object(adapter, "_client"):
            with patch.object(adapter._cb, "call", new=AsyncMock(return_value=mock_resp)):
                result = await adapter.get_workflow_status(WORKFLOW_ID)

        assert result is not None
        assert result["status"] == "approved"

    @pytest.mark.asyncio
    async def test_404_returns_timed_out(self):
        adapter = _make_adapter()
        mock_resp = _make_mock_response(404, STATUS_NOT_FOUND_BODY)

        with patch.object(adapter, "_client"):
            with patch.object(adapter._cb, "call", new=AsyncMock(return_value=mock_resp)):
                result = await adapter.get_workflow_status(WORKFLOW_ID)

        assert result is not None
        assert result["status"] == "timed_out"

    @pytest.mark.asyncio
    async def test_circuit_open_returns_none(self):
        from forgeguard.services.ai_engine.errors import CircuitOpenError

        adapter = _make_adapter()

        with patch.object(
            adapter._cb,
            "call",
            side_effect=CircuitOpenError(state="OPEN", message="open"),
        ):
            result = await adapter.get_workflow_status(WORKFLOW_ID)

        assert result is None

    @pytest.mark.asyncio
    async def test_5xx_returns_none(self):
        adapter = _make_adapter()
        mock_resp = _make_mock_response(500, {})

        with patch.object(adapter, "_client"):
            with patch.object(adapter._cb, "call", new=AsyncMock(return_value=mock_resp)):
                result = await adapter.get_workflow_status(WORKFLOW_ID)

        assert result is None


# ---------------------------------------------------------------------------
# activate_fallback
# ---------------------------------------------------------------------------


class TestActivateFallback:
    @pytest.mark.asyncio
    async def test_fallback_logs_audit_event(self):
        adapter = _make_adapter()
        audit = _make_mock_audit()

        await adapter.activate_fallback(
            decision_id=uuid.uuid4(),
            assessment_id=uuid.uuid4(),
            target_role="security_reviewer",
            context={"service_id": "svc-1"},
            reason="circuit_open",
            audit_svc=audit,
        )

        audit.log_event.assert_awaited_once()
        call_kwargs = audit.log_event.call_args.kwargs
        assert call_kwargs.get("action") == "workflow_fallback_activated"
        assert call_kwargs.get("resource_type") == "release_decision"
        after = call_kwargs.get("after_state", {})
        assert after.get("routing_method") == "dashboard_fallback"
        assert after.get("reason") == "circuit_open"
        assert after.get("target_role") == "security_reviewer"

    @pytest.mark.asyncio
    async def test_fallback_works_without_audit_svc(self):
        adapter = _make_adapter()
        await adapter.activate_fallback(
            decision_id=uuid.uuid4(),
            assessment_id=uuid.uuid4(),
            target_role="tech_lead",
            context={},
            reason="timeout",
            audit_svc=None,
        )


# ---------------------------------------------------------------------------
# trigger_workflow_for_decision
# ---------------------------------------------------------------------------


class TestTriggerWorkflowForDecision:
    @pytest.mark.asyncio
    async def test_approve_skips_workflow(self):
        from forgeguard.services.forge_workflow import trigger_workflow_for_decision

        adapter = MagicMock()
        adapter.trigger_workflow = AsyncMock(return_value=None)
        repo = _make_mock_decision_repo()
        audit = _make_mock_audit()

        await trigger_workflow_for_decision(
            adapter=adapter,
            decision_repo=repo,
            decision_id=uuid.uuid4(),
            assessment_id=uuid.uuid4(),
            decision="APPROVE",
            findings=[],
            context={},
            audit_svc=audit,
        )

        adapter.trigger_workflow.assert_not_called()

    @pytest.mark.asyncio
    async def test_block_triggers_workflow_and_updates_repo(self):
        from forgeguard.services.forge_workflow import trigger_workflow_for_decision

        adapter = MagicMock()
        adapter.trigger_workflow = AsyncMock(return_value=TRIGGER_SUCCESS_RESPONSE)
        adapter.determine_reviewer_role = MagicMock(return_value="tech_lead")
        repo = _make_mock_decision_repo()
        audit = _make_mock_audit()

        decision_id = uuid.uuid4()
        await trigger_workflow_for_decision(
            adapter=adapter,
            decision_repo=repo,
            decision_id=decision_id,
            assessment_id=uuid.uuid4(),
            decision="BLOCK",
            findings=[],
            context={},
            audit_svc=audit,
        )

        adapter.trigger_workflow.assert_awaited_once()
        repo.update_workflow_status.assert_awaited_once()
        call_kwargs = repo.update_workflow_status.call_args.kwargs
        assert call_kwargs.get("routing_method") == "forge_workflow"
        assert call_kwargs.get("workflow_status") == "pending"

    @pytest.mark.asyncio
    async def test_fallback_sets_routing_method_dashboard_fallback(self):
        from forgeguard.services.forge_workflow import trigger_workflow_for_decision

        adapter = MagicMock()
        adapter.trigger_workflow = AsyncMock(return_value=None)
        adapter.activate_fallback = AsyncMock()
        repo = _make_mock_decision_repo()

        await trigger_workflow_for_decision(
            adapter=adapter,
            decision_repo=repo,
            decision_id=uuid.uuid4(),
            assessment_id=uuid.uuid4(),
            decision="CONDITIONAL_APPROVE",
            findings=[],
            context={},
        )

        repo.update_workflow_status.assert_awaited_once()
        call_kwargs = repo.update_workflow_status.call_args.kwargs
        assert call_kwargs.get("routing_method") == "dashboard_fallback"


# ---------------------------------------------------------------------------
# poll_active_workflows
# ---------------------------------------------------------------------------


class TestPollActiveWorkflows:
    @pytest.mark.asyncio
    async def test_no_active_workflows_exits_early(self):
        from forgeguard.services.forge_workflow import poll_active_workflows

        adapter = MagicMock()
        adapter.get_workflow_status = AsyncMock()
        repo = _make_mock_decision_repo()
        repo.list_active_workflows = AsyncMock(return_value=[])

        await poll_active_workflows(adapter=adapter, decision_repo=repo)

        adapter.get_workflow_status.assert_not_called()

    @pytest.mark.asyncio
    async def test_approved_status_updates_repo(self):
        from forgeguard.services.forge_workflow import poll_active_workflows

        decision_id = uuid.uuid4()
        assessment_id = uuid.uuid4()
        active_rows = [
            {
                "id": decision_id,
                "release_assessment_id": assessment_id,
                "workflow_id": WORKFLOW_ID,
                "routing_method": "forge_workflow",
                "workflow_status": "pending",
                "workflow_timeout_at": datetime.now(timezone.utc) + timedelta(hours=20),
            }
        ]

        adapter = MagicMock()
        adapter.get_workflow_status = AsyncMock(return_value=STATUS_APPROVED)
        adapter.activate_fallback = AsyncMock()
        repo = _make_mock_decision_repo()
        repo.list_active_workflows = AsyncMock(return_value=active_rows)
        audit = _make_mock_audit()

        await poll_active_workflows(adapter=adapter, decision_repo=repo, audit_svc=audit)

        repo.update_workflow_status.assert_awaited_once()
        call_kwargs = repo.update_workflow_status.call_args.kwargs
        assert call_kwargs.get("workflow_status") == "approved"
        audit.log_event.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_timed_out_activates_fallback(self):
        from forgeguard.services.forge_workflow import poll_active_workflows

        decision_id = uuid.uuid4()
        assessment_id = uuid.uuid4()
        active_rows = [
            {
                "id": decision_id,
                "release_assessment_id": assessment_id,
                "workflow_id": WORKFLOW_ID,
                "routing_method": "forge_workflow",
                "workflow_status": "pending",
                "workflow_timeout_at": datetime.now(timezone.utc) + timedelta(hours=20),
            }
        ]

        adapter = MagicMock()
        adapter.get_workflow_status = AsyncMock(return_value=STATUS_TIMED_OUT)
        adapter.activate_fallback = AsyncMock()
        repo = _make_mock_decision_repo()
        repo.list_active_workflows = AsyncMock(return_value=active_rows)
        audit = _make_mock_audit()

        await poll_active_workflows(adapter=adapter, decision_repo=repo, audit_svc=audit)

        repo.update_workflow_status.assert_awaited_once()
        adapter.activate_fallback.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_24h_timeout_marks_timed_out_without_poll(self):
        from forgeguard.services.forge_workflow import poll_active_workflows

        decision_id = uuid.uuid4()
        assessment_id = uuid.uuid4()
        # workflow_timeout_at already in the past
        active_rows = [
            {
                "id": decision_id,
                "release_assessment_id": assessment_id,
                "workflow_id": WORKFLOW_ID,
                "routing_method": "forge_workflow",
                "workflow_status": "pending",
                "workflow_timeout_at": datetime.now(timezone.utc) - timedelta(hours=1),
            }
        ]

        adapter = MagicMock()
        adapter.get_workflow_status = AsyncMock()
        adapter.activate_fallback = AsyncMock()
        repo = _make_mock_decision_repo()
        repo.list_active_workflows = AsyncMock(return_value=active_rows)

        await poll_active_workflows(adapter=adapter, decision_repo=repo)

        # Should NOT call get_workflow_status — timeout detected before polling.
        adapter.get_workflow_status.assert_not_called()
        repo.update_workflow_status.assert_awaited_once()
        adapter.activate_fallback.assert_awaited_once()
        assert adapter.activate_fallback.call_args.kwargs["reason"] == "timeout_24h"
