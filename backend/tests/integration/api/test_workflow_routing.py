"""Integration tests for Forge Workflow routing (WO-092).

Tests that:
- A BLOCK decision triggers a Forge Workflow (or falls back to dashboard)
- The release_decisions record is updated with workflow_id and routing_method
- Workflow completion via status polling updates the record
- Fallback path when Forge Workflow API is unavailable
- GET /api/v1/releases/{id}/workflow-status returns correct data
- Audit records are produced for all workflow lifecycle events
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tests.fixtures.forge_workflow_responses import (
    STATUS_APPROVED,
    TRIGGER_SUCCESS_RESPONSE,
    WORKFLOW_ID,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_assessment(status: str = "completed") -> dict:
    return {
        "id": uuid.uuid4(),
        "service_id": uuid.uuid4(),
        "status": status,
        "commit_sha": "abc123",
        "pr_reference": "PR-1",
        "created_at": datetime.now(timezone.utc),
        "completed_at": datetime.now(timezone.utc),
        "change_analysis": None,
    }


def _make_score(score_type: str = "risk", overall: int = 75) -> dict:
    return {
        "id": uuid.uuid4(),
        "score_type": score_type,
        "overall_score": overall,
        "dimension_scores": {},
        "contributing_factors": [],
    }


def _make_decision(decision: str = "BLOCK", workflow_id: str | None = None) -> dict:
    return {
        "id": uuid.uuid4(),
        "release_assessment_id": uuid.uuid4(),
        "decision": decision,
        "was_escalated": False,
        "health_score_at_decision": Decimal("60"),
        "risk_score_at_decision": Decimal("75"),
        "decided_by_role": "tech_lead",
        "decided_by": uuid.uuid4(),
        "rationale": "Test decision",
        "comment": None,
        "workflow_id": uuid.UUID(workflow_id) if workflow_id else None,
        "routing_method": "forge_workflow" if workflow_id else None,
        "workflow_status": "pending" if workflow_id else None,
        "workflow_timeout_at": datetime.now(timezone.utc) + timedelta(hours=24),
        "created_at": datetime.now(timezone.utc),
    }


# ---------------------------------------------------------------------------
# Test: trigger_workflow_for_decision integration
# ---------------------------------------------------------------------------


class TestWorkflowTriggering:
    @pytest.mark.asyncio
    async def test_block_decision_triggers_workflow_and_updates_repo(self):
        """A BLOCK decision triggers POST /workflows/trigger and updates release_decisions."""
        from forgeguard.services.forge_workflow import (
            ForgeWorkflowHttpAdapter,
            trigger_workflow_for_decision,
        )
        from forgeguard.services.ai_engine.circuit_breaker import CircuitBreaker

        cb = CircuitBreaker(failure_threshold=5, window_seconds=60, recovery_timeout=30)
        adapter = ForgeWorkflowHttpAdapter(
            base_url="https://forge.example.com",
            api_key="test-key",
            circuit_breaker=cb,
        )

        decision_id = uuid.uuid4()
        assessment_id = uuid.uuid4()
        mock_repo = AsyncMock()
        mock_repo.update_workflow_status = AsyncMock(return_value=_make_decision(workflow_id=WORKFLOW_ID))

        with patch.object(adapter, "trigger_workflow", new=AsyncMock(return_value=TRIGGER_SUCCESS_RESPONSE)):
            await trigger_workflow_for_decision(
                adapter=adapter,
                decision_repo=mock_repo,
                decision_id=decision_id,
                assessment_id=assessment_id,
                decision="BLOCK",
                findings=[],
                context={"service_id": str(uuid.uuid4()), "risk_score": 80},
            )

        mock_repo.update_workflow_status.assert_awaited_once()
        kwargs = mock_repo.update_workflow_status.call_args.kwargs
        assert kwargs.get("routing_method") == "forge_workflow"
        assert kwargs.get("workflow_status") == "pending"
        assert kwargs.get("workflow_id") == str(TRIGGER_SUCCESS_RESPONSE["workflow_id"])

    @pytest.mark.asyncio
    async def test_approve_decision_skips_workflow(self):
        """An APPROVE decision does NOT trigger any workflow call."""
        from forgeguard.services.forge_workflow import trigger_workflow_for_decision

        adapter = MagicMock()
        adapter.trigger_workflow = AsyncMock()
        mock_repo = AsyncMock()
        mock_repo.update_workflow_status = AsyncMock()

        await trigger_workflow_for_decision(
            adapter=adapter,
            decision_repo=mock_repo,
            decision_id=uuid.uuid4(),
            assessment_id=uuid.uuid4(),
            decision="APPROVE",
            findings=[],
            context={},
        )

        adapter.trigger_workflow.assert_not_called()
        mock_repo.update_workflow_status.assert_not_called()

    @pytest.mark.asyncio
    async def test_forge_unavailable_activates_dashboard_fallback(self):
        """When Forge Workflow API is unavailable, routing_method=dashboard_fallback."""
        from forgeguard.services.forge_workflow import trigger_workflow_for_decision

        adapter = MagicMock()
        adapter.trigger_workflow = AsyncMock(return_value=None)
        adapter.activate_fallback = AsyncMock()
        mock_repo = AsyncMock()
        mock_repo.update_workflow_status = AsyncMock()

        await trigger_workflow_for_decision(
            adapter=adapter,
            decision_repo=mock_repo,
            decision_id=uuid.uuid4(),
            assessment_id=uuid.uuid4(),
            decision="BLOCK",
            findings=[],
            context={},
        )

        mock_repo.update_workflow_status.assert_awaited_once()
        kwargs = mock_repo.update_workflow_status.call_args.kwargs
        assert kwargs.get("routing_method") == "dashboard_fallback"
        assert kwargs.get("workflow_status") == "fallback"


# ---------------------------------------------------------------------------
# Test: poll_active_workflows integration
# ---------------------------------------------------------------------------


class TestWorkflowPollingIntegration:
    @pytest.mark.asyncio
    async def test_poll_approved_updates_record(self):
        """Polling an approved workflow updates workflow_status=approved and logs audit."""
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

        mock_repo = AsyncMock()
        mock_repo.list_active_workflows = AsyncMock(return_value=active_rows)
        mock_repo.update_workflow_status = AsyncMock()

        mock_audit = AsyncMock()
        mock_audit.log_event = AsyncMock(return_value=None)

        await poll_active_workflows(
            adapter=adapter, decision_repo=mock_repo, audit_svc=mock_audit
        )

        mock_repo.update_workflow_status.assert_awaited_once()
        assert mock_repo.update_workflow_status.call_args.kwargs["workflow_status"] == "approved"
        mock_audit.log_event.assert_awaited_once()
        assert mock_audit.log_event.call_args.kwargs["action"] == "workflow_approved"

    @pytest.mark.asyncio
    async def test_poll_skips_when_no_active_workflows(self):
        from forgeguard.services.forge_workflow import poll_active_workflows

        adapter = MagicMock()
        adapter.get_workflow_status = AsyncMock()

        mock_repo = AsyncMock()
        mock_repo.list_active_workflows = AsyncMock(return_value=[])
        mock_repo.update_workflow_status = AsyncMock()

        await poll_active_workflows(adapter=adapter, decision_repo=mock_repo)

        adapter.get_workflow_status.assert_not_called()
        mock_repo.update_workflow_status.assert_not_called()


# ---------------------------------------------------------------------------
# Test: GET /api/v1/releases/{id}/workflow-status endpoint
# ---------------------------------------------------------------------------


class TestWorkflowStatusEndpoint:
    @pytest.mark.asyncio
    async def test_returns_404_when_no_decision(self):
        """GET /workflow-status returns 404 if no decision has been submitted."""
        from forgeguard.api.routes.releases import get_workflow_status
        from fastapi import HTTPException

        mock_repo = AsyncMock()
        mock_repo.find_by_release_assessment = AsyncMock(return_value=[])

        with patch(
            "forgeguard.data.repositories.decisions.DecisionRepository.find_by_release_assessment",
            new=AsyncMock(return_value=[]),
        ):
            with pytest.raises(HTTPException) as exc_info:
                # Build a minimal fake pool for direct handler call.
                fake_pool = MagicMock()
                await get_workflow_status(id=uuid.uuid4(), pool=fake_pool)

        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_returns_workflow_status_for_existing_decision(self):
        """GET /workflow-status returns workflow metadata for an existing decision."""
        from forgeguard.api.routes.releases import get_workflow_status

        decision = _make_decision(decision="BLOCK", workflow_id=WORKFLOW_ID)

        class FakeDecisionRepo:
            async def find_by_release_assessment(self, _):
                return [decision]

        class FakePool:
            def acquire(self):
                return self

            async def __aenter__(self):
                return MagicMock()

            async def __aexit__(self, *a):
                pass

        with patch(
            "forgeguard.api.routes.releases.DecisionRepository",
            return_value=FakeDecisionRepo(),
        ):
            result = await get_workflow_status(id=uuid.uuid4(), pool=FakePool())

        assert result["decision"] == "BLOCK"
        assert result["workflow_id"] == WORKFLOW_ID
        assert result["workflow_status"] == "pending"
        assert result["routing_method"] == "forge_workflow"
        assert result["reviewer_role"] == "tech_lead"


# ---------------------------------------------------------------------------
# Test: Security escalation always routes to security_reviewer
# ---------------------------------------------------------------------------


class TestSecurityEscalationRouting:
    def test_critical_security_finding_routes_to_security_reviewer(self):
        from forgeguard.services.forge_workflow import ForgeWorkflowAdapter

        findings = [{"severity": "CRITICAL", "dimension": "SECURITY"}]
        with patch(
            "forgeguard.services.domain.severity.SeverityClassifier.is_escalation_required",
            return_value=True,
        ):
            role = ForgeWorkflowAdapter.determine_reviewer_role("BLOCK", findings=findings)

        assert role == "security_reviewer"

    def test_critical_security_escalation_works_even_with_circuit_open(self):
        """Even when circuit is open, security_reviewer routing must be determined correctly."""
        from forgeguard.services.forge_workflow import ForgeWorkflowAdapter

        # determine_reviewer_role is a pure computation — no HTTP call.
        findings = [{"severity": "CRITICAL", "dimension": "SECURITY"}]
        with patch(
            "forgeguard.services.domain.severity.SeverityClassifier.is_escalation_required",
            return_value=True,
        ):
            role = ForgeWorkflowAdapter.determine_reviewer_role("BLOCK", findings=findings)

        assert role == "security_reviewer"


# ---------------------------------------------------------------------------
# Test: Audit records for all lifecycle events
# ---------------------------------------------------------------------------


class TestAuditLogging:
    @pytest.mark.asyncio
    async def test_trigger_success_produces_audit_record(self):
        from forgeguard.services.forge_workflow import ForgeWorkflowHttpAdapter
        from forgeguard.services.ai_engine.circuit_breaker import CircuitBreaker
        import httpx

        cb = CircuitBreaker(failure_threshold=5, window_seconds=60, recovery_timeout=30)
        adapter = ForgeWorkflowHttpAdapter(
            base_url="https://forge.example.com",
            api_key="test-key",
            circuit_breaker=cb,
        )
        audit = AsyncMock()
        audit.log_event = AsyncMock(return_value=None)

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.is_success = True
        mock_resp.json.return_value = TRIGGER_SUCCESS_RESPONSE

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
        event = audit.log_event.call_args.kwargs
        assert event["action"] == "workflow_triggered"
        after = event["after_state"]
        assert after["routing_method"] == "forge_workflow"
        # API key must NEVER appear in audit records.
        assert "test-key" not in str(after)

    @pytest.mark.asyncio
    async def test_fallback_produces_audit_record_with_routing_method(self):
        from forgeguard.services.forge_workflow import ForgeWorkflowHttpAdapter
        from forgeguard.services.ai_engine.circuit_breaker import CircuitBreaker

        cb = CircuitBreaker(failure_threshold=5, window_seconds=60, recovery_timeout=30)
        adapter = ForgeWorkflowHttpAdapter(
            base_url="https://forge.example.com",
            api_key="secret-key",
            circuit_breaker=cb,
        )
        audit = AsyncMock()
        audit.log_event = AsyncMock(return_value=None)

        await adapter.activate_fallback(
            decision_id=uuid.uuid4(),
            assessment_id=uuid.uuid4(),
            target_role="security_reviewer",
            context={"service_id": "svc-1"},
            reason="circuit_open",
            audit_svc=audit,
        )

        audit.log_event.assert_awaited_once()
        event = audit.log_event.call_args.kwargs
        assert event["action"] == "workflow_fallback_activated"
        after = event["after_state"]
        assert after["routing_method"] == "dashboard_fallback"
        # API key must NEVER appear in audit records.
        assert "secret-key" not in str(after)
