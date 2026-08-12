"""Integration tests for POST /api/v1/releases/{id}/decide endpoint (WO-051).

Tests cover the full endpoint lifecycle:
    1. Happy path: completed assessment → APPROVE → decision + audit records
    2. Escalated decision flow: critical security finding → Security Reviewer override
    3. Concurrent duplicate prevention: second call returns 409
    4. All error paths: 400 (status, scores), 404, 409

These tests use the real SecurityEscalationService and DecisionEngine but mock
all database dependencies — no testcontainer or running PostgreSQL required.

Run:
    pytest tests/integration/api/test_release_decision_flow.py -v
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch, call

import pytest

from forgeguard.core.permissions import UserRole
from tests.fixtures.release_decisions import (
    ALREADY_DECIDED_ASSESSMENT,
    APPROVE_REQUEST,
    ASSESSMENT_ID_ALREADY_DECIDED,
    ASSESSMENT_ID_COMPLETED,
    ASSESSMENT_ID_WITH_ESCALATION,
    BLOCK_REQUEST,
    COMPLETED_ASSESSMENT,
    COMPLETED_ASSESSMENT_WITH_ESCALATION,
    CONDITIONAL_APPROVE_REQUEST,
    ESCALATION_HEALTH_SCORE_ROW,
    ESCALATION_RISK_SCORE_ROW,
    EXISTING_DECISION_ROW,
    HEALTH_SCORE_ROW,
    RISK_SCORE_ROW,
)


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _mock_request(role: str, user_id: str | None = None) -> MagicMock:
    req = MagicMock()
    req.state = MagicMock()
    req.state.user_role = role
    req.state.user_id = user_id or str(uuid.uuid4())
    return req


def _decision_row(decision: str = "APPROVE", was_escalated: bool = False) -> dict[str, Any]:
    return {
        "id": uuid.uuid4(),
        "release_assessment_id": ASSESSMENT_ID_COMPLETED,
        "health_score_at_decision": Decimal("72.50"),
        "risk_score_at_decision": Decimal("28.00"),
        "decision": decision,
        "decided_by_role": "tech_lead",
        "decided_by": uuid.uuid4(),
        "rationale": "All quality gates passed and risk is acceptable",
        "comment": None,
        "was_escalated": was_escalated,
        "created_at": None,
    }


def _audit_svc() -> MagicMock:
    svc = MagicMock()
    svc.log_event = AsyncMock(return_value={"id": uuid.uuid4()})
    return svc


# ===========================================================================
# Full happy path
# ===========================================================================

class TestHappyPath:
    @pytest.mark.asyncio
    async def test_tech_lead_approve_full_lifecycle(self):
        """Tech Lead submits APPROVE: decision persisted + audit record created."""
        from forgeguard.api.routes.releases import decide_release
        from forgeguard.api.schemas.releases import ReleaseDecisionRequest

        body = ReleaseDecisionRequest(**APPROVE_REQUEST)
        request = _mock_request(UserRole.tech_lead.value)
        pool = MagicMock()
        audit_svc = _audit_svc()

        created_records: list[dict] = []

        async def _capture_create(data: dict) -> dict:
            created_records.append(data)
            return {**data, "id": uuid.uuid4(), "created_at": None}

        with (
            patch("forgeguard.api.routes.releases.ReleaseAssessmentRepository") as mock_ar,
            patch("forgeguard.api.routes.releases.DecisionRepository") as mock_dr,
            patch("forgeguard.api.routes.releases.AssessmentScoreRepository") as mock_sr,
        ):
            mock_ar.return_value.get_by_id = AsyncMock(return_value=COMPLETED_ASSESSMENT)
            mock_dr.return_value.find_by_release_assessment = AsyncMock(return_value=[])
            mock_dr.return_value.create = _capture_create
            mock_sr.return_value.get_score_by_type = AsyncMock(side_effect=lambda _id, t: (
                HEALTH_SCORE_ROW if t == "health" else RISK_SCORE_ROW
            ))

            result = await decide_release(
                id=ASSESSMENT_ID_COMPLETED,
                body=body,
                request=request,
                pool=pool,
                audit_svc=audit_svc,
            )

        # Decision was persisted
        assert len(created_records) == 1
        record = created_records[0]
        assert record["decision"] == "APPROVE"
        assert record["decided_by_role"] == UserRole.tech_lead.value
        assert record["rationale"] == APPROVE_REQUEST["rationale"]
        assert record["was_escalated"] is False

        # Audit record created
        audit_svc.log_event.assert_called_once()
        audit_kwargs = audit_svc.log_event.call_args.kwargs
        assert audit_kwargs["action"] == "release_decision"
        assert audit_kwargs["resource_type"] == "release_decision"

        # Response structure
        assert result.decision == "APPROVE"
        assert result.release_assessment_id == ASSESSMENT_ID_COMPLETED
        assert result.health_score_at_decision == float(HEALTH_SCORE_ROW["overall_score"])
        assert result.risk_score_at_decision == float(RISK_SCORE_ROW["overall_score"])

    @pytest.mark.asyncio
    async def test_block_decision_persisted_correctly(self):
        """BLOCK decision creates a proper release_decisions record."""
        from forgeguard.api.routes.releases import decide_release
        from forgeguard.api.schemas.releases import ReleaseDecisionRequest

        body = ReleaseDecisionRequest(**BLOCK_REQUEST)
        request = _mock_request(UserRole.security_reviewer.value)
        pool = MagicMock()
        audit_svc = _audit_svc()

        captured: list[dict] = []

        async def _capture(data: dict) -> dict:
            captured.append(data)
            return {**data, "id": uuid.uuid4(), "created_at": None}

        with (
            patch("forgeguard.api.routes.releases.ReleaseAssessmentRepository") as mock_ar,
            patch("forgeguard.api.routes.releases.DecisionRepository") as mock_dr,
            patch("forgeguard.api.routes.releases.AssessmentScoreRepository") as mock_sr,
        ):
            mock_ar.return_value.get_by_id = AsyncMock(return_value=COMPLETED_ASSESSMENT)
            mock_dr.return_value.find_by_release_assessment = AsyncMock(return_value=[])
            mock_dr.return_value.create = _capture
            mock_sr.return_value.get_score_by_type = AsyncMock(side_effect=lambda _id, t: (
                HEALTH_SCORE_ROW if t == "health" else RISK_SCORE_ROW
            ))

            result = await decide_release(
                id=ASSESSMENT_ID_COMPLETED,
                body=body,
                request=request,
                pool=pool,
                audit_svc=audit_svc,
            )

        assert result.decision == "BLOCK"
        assert len(captured) == 1
        assert captured[0]["decision"] == "BLOCK"

    @pytest.mark.asyncio
    async def test_comment_stored_when_provided(self):
        """Optional comment is passed through to the decision record."""
        from forgeguard.api.routes.releases import decide_release
        from forgeguard.api.schemas.releases import ReleaseDecisionRequest

        body = ReleaseDecisionRequest(**CONDITIONAL_APPROVE_REQUEST)
        request = _mock_request(UserRole.platform_admin.value)
        pool = MagicMock()
        audit_svc = _audit_svc()

        captured: list[dict] = []

        async def _capture(data: dict) -> dict:
            captured.append(data)
            return {**data, "id": uuid.uuid4(), "created_at": None}

        with (
            patch("forgeguard.api.routes.releases.ReleaseAssessmentRepository") as mock_ar,
            patch("forgeguard.api.routes.releases.DecisionRepository") as mock_dr,
            patch("forgeguard.api.routes.releases.AssessmentScoreRepository") as mock_sr,
        ):
            mock_ar.return_value.get_by_id = AsyncMock(return_value=COMPLETED_ASSESSMENT)
            mock_dr.return_value.find_by_release_assessment = AsyncMock(return_value=[])
            mock_dr.return_value.create = _capture
            mock_sr.return_value.get_score_by_type = AsyncMock(side_effect=lambda _id, t: (
                HEALTH_SCORE_ROW if t == "health" else RISK_SCORE_ROW
            ))

            result = await decide_release(
                id=ASSESSMENT_ID_COMPLETED,
                body=body,
                request=request,
                pool=pool,
                audit_svc=audit_svc,
            )

        assert captured[0]["comment"] == CONDITIONAL_APPROVE_REQUEST["comment"]
        assert result.comment == CONDITIONAL_APPROVE_REQUEST["comment"]


# ===========================================================================
# Escalated decision flow
# ===========================================================================

class TestEscalatedDecisionFlow:
    @pytest.mark.asyncio
    async def test_security_reviewer_can_approve_escalated_assessment(self):
        """Security Reviewer may APPROVE even when was_escalated is True."""
        from forgeguard.api.routes.releases import decide_release
        from forgeguard.api.schemas.releases import ReleaseDecisionRequest

        body = ReleaseDecisionRequest(**APPROVE_REQUEST)
        request = _mock_request(UserRole.security_reviewer.value)
        pool = MagicMock()
        audit_svc = _audit_svc()

        row = _decision_row("APPROVE", was_escalated=True)
        row["release_assessment_id"] = ASSESSMENT_ID_WITH_ESCALATION

        with (
            patch("forgeguard.api.routes.releases.ReleaseAssessmentRepository") as mock_ar,
            patch("forgeguard.api.routes.releases.DecisionRepository") as mock_dr,
            patch("forgeguard.api.routes.releases.AssessmentScoreRepository") as mock_sr,
            patch("forgeguard.api.routes.releases.AuditLogRepository"),
            patch("forgeguard.api.routes.releases.AuditService") as mock_sys_audit,
        ):
            mock_sys_audit.return_value.log_event = AsyncMock(return_value={"id": uuid.uuid4()})
            mock_ar.return_value.get_by_id = AsyncMock(
                return_value=COMPLETED_ASSESSMENT_WITH_ESCALATION
            )
            mock_dr.return_value.find_by_release_assessment = AsyncMock(return_value=[])
            mock_dr.return_value.create = AsyncMock(return_value=row)
            mock_sr.return_value.get_score_by_type = AsyncMock(side_effect=lambda _id, t: (
                ESCALATION_HEALTH_SCORE_ROW if t == "health" else ESCALATION_RISK_SCORE_ROW
            ))

            result = await decide_release(
                id=ASSESSMENT_ID_WITH_ESCALATION,
                body=body,
                request=request,
                pool=pool,
                audit_svc=audit_svc,
            )

        assert result.decision == "APPROVE"
        assert result.was_escalated is True
        assert result.escalation_reasons  # escalation reasons populated

    @pytest.mark.asyncio
    async def test_escalated_assessment_creates_system_audit_record(self):
        """When was_escalated=True, a second SYSTEM audit record is written."""
        from forgeguard.api.routes.releases import decide_release
        from forgeguard.api.schemas.releases import ReleaseDecisionRequest

        body = ReleaseDecisionRequest(**BLOCK_REQUEST)
        request = _mock_request(UserRole.security_reviewer.value)
        pool = MagicMock()
        audit_svc = _audit_svc()

        system_audit_calls: list[dict] = []

        class MockSystemAuditSvc:
            async def log_event(self, **kwargs: Any) -> dict:
                system_audit_calls.append(kwargs)
                return {"id": uuid.uuid4()}

        row = _decision_row("BLOCK", was_escalated=True)

        with (
            patch("forgeguard.api.routes.releases.ReleaseAssessmentRepository") as mock_ar,
            patch("forgeguard.api.routes.releases.DecisionRepository") as mock_dr,
            patch("forgeguard.api.routes.releases.AssessmentScoreRepository") as mock_sr,
            patch("forgeguard.api.routes.releases.AuditLogRepository"),
            patch("forgeguard.api.routes.releases.AuditService", return_value=MockSystemAuditSvc()),
        ):
            mock_ar.return_value.get_by_id = AsyncMock(
                return_value=COMPLETED_ASSESSMENT_WITH_ESCALATION
            )
            mock_dr.return_value.find_by_release_assessment = AsyncMock(return_value=[])
            mock_dr.return_value.create = AsyncMock(return_value=row)
            mock_sr.return_value.get_score_by_type = AsyncMock(side_effect=lambda _id, t: (
                ESCALATION_HEALTH_SCORE_ROW if t == "health" else ESCALATION_RISK_SCORE_ROW
            ))

            await decide_release(
                id=ASSESSMENT_ID_WITH_ESCALATION,
                body=body,
                request=request,
                pool=pool,
                audit_svc=audit_svc,
            )

        # System audit record should be created for escalation event
        system_calls = [c for c in system_audit_calls if c.get("action") == "security_auto_escalation"]
        assert len(system_calls) == 1
        sys_call = system_calls[0]
        from forgeguard.services.decision_engine.escalation_service import SYSTEM_ACTOR_UUID
        assert sys_call["actor_id"] == SYSTEM_ACTOR_UUID

    @pytest.mark.asyncio
    async def test_non_escalated_assessment_has_no_system_audit(self):
        """When was_escalated=False, no system audit record is written."""
        from forgeguard.api.routes.releases import decide_release
        from forgeguard.api.schemas.releases import ReleaseDecisionRequest

        body = ReleaseDecisionRequest(**APPROVE_REQUEST)
        request = _mock_request(UserRole.tech_lead.value)
        pool = MagicMock()
        audit_svc = _audit_svc()

        with (
            patch("forgeguard.api.routes.releases.ReleaseAssessmentRepository") as mock_ar,
            patch("forgeguard.api.routes.releases.DecisionRepository") as mock_dr,
            patch("forgeguard.api.routes.releases.AssessmentScoreRepository") as mock_sr,
            patch("forgeguard.api.routes.releases.AuditLogRepository") as mock_al,
        ):
            mock_ar.return_value.get_by_id = AsyncMock(return_value=COMPLETED_ASSESSMENT)
            mock_dr.return_value.find_by_release_assessment = AsyncMock(return_value=[])
            mock_dr.return_value.create = AsyncMock(return_value=_decision_row("APPROVE"))
            mock_sr.return_value.get_score_by_type = AsyncMock(side_effect=lambda _id, t: (
                HEALTH_SCORE_ROW if t == "health" else RISK_SCORE_ROW
            ))

            await decide_release(
                id=ASSESSMENT_ID_COMPLETED,
                body=body,
                request=request,
                pool=pool,
                audit_svc=audit_svc,
            )

        # AuditLogRepository should not be called (only instantiated for system audit on escalation)
        mock_al.assert_not_called()


# ===========================================================================
# Concurrent decision submission — 409 race condition handling
# ===========================================================================

class TestConcurrentDecisionSubmission:
    @pytest.mark.asyncio
    async def test_second_decision_returns_409_with_existing_id(self):
        """When a decision already exists, endpoint returns 409 with its ID."""
        from fastapi import HTTPException
        from forgeguard.api.routes.releases import decide_release
        from forgeguard.api.schemas.releases import ReleaseDecisionRequest

        body = ReleaseDecisionRequest(**APPROVE_REQUEST)
        request = _mock_request(UserRole.tech_lead.value)
        pool = MagicMock()
        audit_svc = _audit_svc()

        with (
            patch("forgeguard.api.routes.releases.ReleaseAssessmentRepository") as mock_ar,
            patch("forgeguard.api.routes.releases.DecisionRepository") as mock_dr,
            patch("forgeguard.api.routes.releases.AssessmentScoreRepository") as mock_sr,
        ):
            mock_ar.return_value.get_by_id = AsyncMock(return_value=ALREADY_DECIDED_ASSESSMENT)
            mock_dr.return_value.find_by_release_assessment = AsyncMock(
                return_value=[EXISTING_DECISION_ROW]
            )
            mock_sr.return_value.get_score_by_type = AsyncMock(return_value=HEALTH_SCORE_ROW)

            with pytest.raises(HTTPException) as exc_info:
                await decide_release(
                    id=ASSESSMENT_ID_ALREADY_DECIDED,
                    body=body,
                    request=request,
                    pool=pool,
                    audit_svc=audit_svc,
                )

        assert exc_info.value.status_code == 409
        detail = exc_info.value.detail
        assert detail["detail"] == "Decision already exists"
        assert detail["existing_decision_id"] == str(EXISTING_DECISION_ROW["id"])

    @pytest.mark.asyncio
    async def test_decision_repo_not_called_when_duplicate_detected(self):
        """create() is never called on DecisionRepository when duplicate exists."""
        from fastapi import HTTPException
        from forgeguard.api.routes.releases import decide_release
        from forgeguard.api.schemas.releases import ReleaseDecisionRequest

        body = ReleaseDecisionRequest(**APPROVE_REQUEST)
        request = _mock_request(UserRole.tech_lead.value)
        pool = MagicMock()
        audit_svc = _audit_svc()

        with (
            patch("forgeguard.api.routes.releases.ReleaseAssessmentRepository") as mock_ar,
            patch("forgeguard.api.routes.releases.DecisionRepository") as mock_dr,
            patch("forgeguard.api.routes.releases.AssessmentScoreRepository") as mock_sr,
        ):
            mock_ar.return_value.get_by_id = AsyncMock(return_value=ALREADY_DECIDED_ASSESSMENT)
            mock_dr.return_value.find_by_release_assessment = AsyncMock(
                return_value=[EXISTING_DECISION_ROW]
            )
            mock_dr.return_value.create = AsyncMock()
            mock_sr.return_value.get_score_by_type = AsyncMock(return_value=HEALTH_SCORE_ROW)

            with pytest.raises(HTTPException):
                await decide_release(
                    id=ASSESSMENT_ID_ALREADY_DECIDED,
                    body=body,
                    request=request,
                    pool=pool,
                    audit_svc=audit_svc,
                )

        mock_dr.return_value.create.assert_not_called()


# ===========================================================================
# Error response contracts
# ===========================================================================

class TestErrorResponseContracts:
    @pytest.mark.asyncio
    async def test_404_detail_message(self):
        from fastapi import HTTPException
        from forgeguard.api.routes.releases import decide_release
        from forgeguard.api.schemas.releases import ReleaseDecisionRequest

        body = ReleaseDecisionRequest(**APPROVE_REQUEST)
        request = _mock_request(UserRole.tech_lead.value)
        pool = MagicMock()

        with (
            patch("forgeguard.api.routes.releases.ReleaseAssessmentRepository") as mock_ar,
            patch("forgeguard.api.routes.releases.DecisionRepository") as mock_dr,
            patch("forgeguard.api.routes.releases.AssessmentScoreRepository") as mock_sr,
        ):
            mock_ar.return_value.get_by_id = AsyncMock(return_value=None)
            mock_dr.return_value.find_by_release_assessment = AsyncMock(return_value=[])
            mock_sr.return_value.get_score_by_type = AsyncMock(return_value=None)

            with pytest.raises(HTTPException) as exc_info:
                await decide_release(
                    id=uuid.uuid4(),
                    body=body,
                    request=request,
                    pool=pool,
                    audit_svc=_audit_svc(),
                )

        assert exc_info.value.status_code == 404
        assert "not found" in str(exc_info.value.detail).lower()

    @pytest.mark.asyncio
    async def test_403_escalation_includes_role_context(self):
        from fastapi import HTTPException
        from forgeguard.api.routes.releases import decide_release
        from forgeguard.api.schemas.releases import ReleaseDecisionRequest

        body = ReleaseDecisionRequest(**APPROVE_REQUEST)
        request = _mock_request(UserRole.tech_lead.value)
        pool = MagicMock()

        with (
            patch("forgeguard.api.routes.releases.ReleaseAssessmentRepository") as mock_ar,
            patch("forgeguard.api.routes.releases.DecisionRepository") as mock_dr,
            patch("forgeguard.api.routes.releases.AssessmentScoreRepository") as mock_sr,
        ):
            mock_ar.return_value.get_by_id = AsyncMock(
                return_value=COMPLETED_ASSESSMENT_WITH_ESCALATION
            )
            mock_dr.return_value.find_by_release_assessment = AsyncMock(return_value=[])
            mock_sr.return_value.get_score_by_type = AsyncMock(side_effect=lambda _id, t: (
                ESCALATION_HEALTH_SCORE_ROW if t == "health" else ESCALATION_RISK_SCORE_ROW
            ))

            with pytest.raises(HTTPException) as exc_info:
                await decide_release(
                    id=ASSESSMENT_ID_WITH_ESCALATION,
                    body=body,
                    request=request,
                    pool=pool,
                    audit_svc=_audit_svc(),
                )

        assert exc_info.value.status_code == 403
        detail = exc_info.value.detail
        assert "current_role" in detail
        assert detail["current_role"] == UserRole.tech_lead.value

    @pytest.mark.asyncio
    async def test_400_status_includes_field_level_errors(self):
        from fastapi import HTTPException
        from forgeguard.api.routes.releases import decide_release
        from forgeguard.api.schemas.releases import ReleaseDecisionRequest

        body = ReleaseDecisionRequest(**APPROVE_REQUEST)
        request = _mock_request(UserRole.tech_lead.value)
        pool = MagicMock()

        from tests.fixtures.release_decisions import PENDING_ASSESSMENT, ASSESSMENT_ID_PENDING

        with (
            patch("forgeguard.api.routes.releases.ReleaseAssessmentRepository") as mock_ar,
            patch("forgeguard.api.routes.releases.DecisionRepository") as mock_dr,
            patch("forgeguard.api.routes.releases.AssessmentScoreRepository") as mock_sr,
        ):
            mock_ar.return_value.get_by_id = AsyncMock(return_value=PENDING_ASSESSMENT)
            mock_dr.return_value.find_by_release_assessment = AsyncMock(return_value=[])
            mock_sr.return_value.get_score_by_type = AsyncMock(return_value=None)

            with pytest.raises(HTTPException) as exc_info:
                await decide_release(
                    id=ASSESSMENT_ID_PENDING,
                    body=body,
                    request=request,
                    pool=pool,
                    audit_svc=_audit_svc(),
                )

        assert exc_info.value.status_code == 400
        detail = exc_info.value.detail
        assert "errors" in detail
        assert len(detail["errors"]) > 0
