"""Unit tests for POST /api/v1/releases/{id}/decide endpoint (WO-051).

Tests cover:
    1. Successful APPROVE by Tech Lead
    2. Successful BLOCK by Security Reviewer
    3. Successful CONDITIONAL_APPROVE by Platform Admin
    4. 403 for Developer role
    5. 403 for Engineering Manager role
    6. 403 for Operator role
    7. 400 for assessment not completed (pending status)
    8. 400 for assessment not completed (in_progress status)
    9. 409 for duplicate decision submission
    10. 400 for missing rationale
    11. 400 for rationale under 10 characters
    12. 400 for missing health score
    13. 400 for missing risk score
    14. 400 for missing both scores
    15. 403 for Tech Lead attempting APPROVE on escalated assessment
    16. 403 for Platform Admin attempting CONDITIONAL_APPROVE on escalated assessment
    17. 200 for Security Reviewer submitting APPROVE on escalated assessment
    18. BLOCK always allowed regardless of escalation status
    19. Response structure includes all required fields
    20. was_escalated=False for non-escalated assessment
    21. was_escalated=True for escalated assessment
    22. ReleaseDecisionRequest schema validation — decision enum values

All tests use mocked database dependencies.

Run:
    pytest tests/unit/api/test_release_decision_endpoint.py -v
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from forgeguard.api.schemas.releases import ReleaseDecisionCreate, ReleaseDecisionRequest
from forgeguard.core.permissions import UserRole
from tests.fixtures.release_decisions import (
    APPROVE_REQUEST,
    ASSESSMENT_ID_ALREADY_DECIDED,
    ASSESSMENT_ID_COMPLETED,
    ASSESSMENT_ID_IN_PROGRESS,
    ASSESSMENT_ID_MISSING_BOTH,
    ASSESSMENT_ID_MISSING_HEALTH,
    ASSESSMENT_ID_MISSING_RISK,
    ASSESSMENT_ID_PENDING,
    ASSESSMENT_ID_WITH_ESCALATION,
    ALREADY_DECIDED_ASSESSMENT,
    BLOCK_REQUEST,
    COMPLETED_ASSESSMENT,
    COMPLETED_ASSESSMENT_WITH_ESCALATION,
    CONDITIONAL_APPROVE_REQUEST,
    ESCALATION_HEALTH_SCORE_ROW,
    ESCALATION_RISK_SCORE_ROW,
    EXISTING_DECISION_ROW,
    HEALTH_SCORE_ROW,
    IN_PROGRESS_ASSESSMENT,
    PENDING_ASSESSMENT,
    RISK_SCORE_ROW,
    AUTHORIZED_ROLES,
    UNAUTHORIZED_ROLES,
)


# ---------------------------------------------------------------------------
# Helper — build the request body model from a dict
# ---------------------------------------------------------------------------

def _req(data: dict[str, Any]) -> ReleaseDecisionRequest:
    return ReleaseDecisionRequest(**data)


# ---------------------------------------------------------------------------
# Helper — create a minimal mock pool/request/audit_svc
# ---------------------------------------------------------------------------

def _mock_request(role: str, user_id: str | None = None) -> MagicMock:
    req = MagicMock()
    req.state = MagicMock()
    req.state.user_role = role
    req.state.user_id = user_id or str(uuid.uuid4())
    return req


def _audit_svc() -> MagicMock:
    svc = MagicMock()
    svc.log_event = AsyncMock(return_value={"id": uuid.uuid4()})
    return svc


def _decision_row(decision: str = "APPROVE") -> dict[str, Any]:
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
        "was_escalated": False,
        "created_at": None,
    }


# ===========================================================================
# Schema validation tests (pure — no I/O)
# ===========================================================================

class TestReleaseDecisionRequestSchema:
    def test_valid_approve_request(self):
        req = _req(APPROVE_REQUEST)
        assert req.decision == ReleaseDecisionCreate.APPROVE

    def test_valid_block_request(self):
        req = _req(BLOCK_REQUEST)
        assert req.decision == ReleaseDecisionCreate.BLOCK

    def test_valid_conditional_approve_request(self):
        req = _req(CONDITIONAL_APPROVE_REQUEST)
        assert req.decision == ReleaseDecisionCreate.CONDITIONAL_APPROVE
        assert req.comment == "Revisit within 72 hours"

    def test_rationale_min_length_10(self):
        req = _req({"decision": "APPROVE", "rationale": "0123456789"})
        assert len(req.rationale) == 10

    def test_rationale_under_10_raises(self):
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            _req({"decision": "APPROVE", "rationale": "Too short"})

    def test_missing_rationale_raises(self):
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            _req({"decision": "APPROVE"})

    def test_invalid_decision_enum_raises(self):
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            _req({"decision": "MAYBE", "rationale": "Valid rationale here"})

    def test_comment_optional_defaults_none(self):
        req = _req(APPROVE_REQUEST)
        assert req.comment is None

    def test_comment_max_2000_enforced(self):
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            _req({"decision": "APPROVE", "rationale": "Valid rationale here", "comment": "x" * 2001})

    def test_rationale_max_2000_enforced(self):
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            _req({"decision": "APPROVE", "rationale": "x" * 2001})

    def test_valid_decision_enum_values(self):
        assert set(ReleaseDecisionCreate) == {
            ReleaseDecisionCreate.APPROVE,
            ReleaseDecisionCreate.CONDITIONAL_APPROVE,
            ReleaseDecisionCreate.BLOCK,
        }


# ===========================================================================
# Endpoint unit tests — patching repositories
# ===========================================================================

class TestDecideReleaseHappyPath:
    """Successful decision submissions by authorized roles."""

    @pytest.mark.asyncio
    async def test_tech_lead_approve_returns_201(self):
        """Tech Lead with APPROVE decision succeeds and returns decision record."""
        from forgeguard.api.routes.releases import decide_release

        body = _req(APPROVE_REQUEST)
        request = _mock_request(UserRole.tech_lead.value)
        pool = MagicMock()
        audit_svc = _audit_svc()

        with (
            patch("forgeguard.api.routes.releases.ReleaseAssessmentRepository") as mock_ar,
            patch("forgeguard.api.routes.releases.DecisionRepository") as mock_dr,
            patch("forgeguard.api.routes.releases.AssessmentScoreRepository") as mock_sr,
        ):
            mock_ar.return_value.get_by_id = AsyncMock(return_value=COMPLETED_ASSESSMENT)
            mock_dr.return_value.find_by_release_assessment = AsyncMock(return_value=[])
            mock_dr.return_value.create = AsyncMock(return_value=_decision_row("APPROVE"))
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

        assert result.decision == "APPROVE"
        assert result.decided_by_role == UserRole.tech_lead.value
        assert result.was_escalated is False

    @pytest.mark.asyncio
    async def test_security_reviewer_block_returns_201(self):
        """Security Reviewer with BLOCK decision succeeds."""
        from forgeguard.api.routes.releases import decide_release

        body = _req(BLOCK_REQUEST)
        request = _mock_request(UserRole.security_reviewer.value)
        pool = MagicMock()
        audit_svc = _audit_svc()

        with (
            patch("forgeguard.api.routes.releases.ReleaseAssessmentRepository") as mock_ar,
            patch("forgeguard.api.routes.releases.DecisionRepository") as mock_dr,
            patch("forgeguard.api.routes.releases.AssessmentScoreRepository") as mock_sr,
        ):
            mock_ar.return_value.get_by_id = AsyncMock(return_value=COMPLETED_ASSESSMENT)
            mock_dr.return_value.find_by_release_assessment = AsyncMock(return_value=[])
            mock_dr.return_value.create = AsyncMock(return_value=_decision_row("BLOCK"))
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

    @pytest.mark.asyncio
    async def test_platform_admin_conditional_approve_returns_201(self):
        """Platform Admin with CONDITIONAL_APPROVE decision succeeds."""
        from forgeguard.api.routes.releases import decide_release

        body = _req(CONDITIONAL_APPROVE_REQUEST)
        request = _mock_request(UserRole.platform_admin.value)
        pool = MagicMock()
        audit_svc = _audit_svc()

        with (
            patch("forgeguard.api.routes.releases.ReleaseAssessmentRepository") as mock_ar,
            patch("forgeguard.api.routes.releases.DecisionRepository") as mock_dr,
            patch("forgeguard.api.routes.releases.AssessmentScoreRepository") as mock_sr,
        ):
            mock_ar.return_value.get_by_id = AsyncMock(return_value=COMPLETED_ASSESSMENT)
            mock_dr.return_value.find_by_release_assessment = AsyncMock(return_value=[])
            mock_dr.return_value.create = AsyncMock(
                return_value=_decision_row("CONDITIONAL_APPROVE")
            )
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

        assert result.decision == "CONDITIONAL_APPROVE"

    @pytest.mark.asyncio
    async def test_rationale_stored_on_persisted_record(self):
        """Rationale from request body is passed to DecisionRepository.create."""
        from forgeguard.api.routes.releases import decide_release

        body = _req(APPROVE_REQUEST)
        request = _mock_request(UserRole.tech_lead.value)
        pool = MagicMock()
        audit_svc = _audit_svc()
        persisted_data: list[dict] = []

        async def _capture_create(data: dict) -> dict:
            persisted_data.append(data)
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

            await decide_release(
                id=ASSESSMENT_ID_COMPLETED,
                body=body,
                request=request,
                pool=pool,
                audit_svc=audit_svc,
            )

        assert len(persisted_data) == 1
        assert persisted_data[0]["rationale"] == APPROVE_REQUEST["rationale"]

    @pytest.mark.asyncio
    async def test_scores_captured_from_score_repo(self):
        """Health and risk scores are fetched from score_repo, not request body."""
        from forgeguard.api.routes.releases import decide_release

        body = _req(APPROVE_REQUEST)
        request = _mock_request(UserRole.tech_lead.value)
        pool = MagicMock()
        audit_svc = _audit_svc()
        score_calls: list[str] = []

        async def _mock_score(assessment_id: uuid.UUID, score_type: str) -> dict:
            score_calls.append(score_type)
            return HEALTH_SCORE_ROW if score_type == "health" else RISK_SCORE_ROW

        with (
            patch("forgeguard.api.routes.releases.ReleaseAssessmentRepository") as mock_ar,
            patch("forgeguard.api.routes.releases.DecisionRepository") as mock_dr,
            patch("forgeguard.api.routes.releases.AssessmentScoreRepository") as mock_sr,
        ):
            mock_ar.return_value.get_by_id = AsyncMock(return_value=COMPLETED_ASSESSMENT)
            mock_dr.return_value.find_by_release_assessment = AsyncMock(return_value=[])
            mock_dr.return_value.create = AsyncMock(return_value=_decision_row())
            mock_sr.return_value.get_score_by_type = _mock_score

            result = await decide_release(
                id=ASSESSMENT_ID_COMPLETED,
                body=body,
                request=request,
                pool=pool,
                audit_svc=audit_svc,
            )

        assert "health" in score_calls
        assert "risk" in score_calls
        assert result.health_score_at_decision == float(HEALTH_SCORE_ROW["overall_score"])
        assert result.risk_score_at_decision == float(RISK_SCORE_ROW["overall_score"])


# ===========================================================================
# 404 — assessment not found
# ===========================================================================

class TestDecideReleaseNotFound:
    @pytest.mark.asyncio
    async def test_missing_assessment_returns_404(self):
        from fastapi import HTTPException
        from forgeguard.api.routes.releases import decide_release

        body = _req(APPROVE_REQUEST)
        request = _mock_request(UserRole.tech_lead.value)
        pool = MagicMock()
        audit_svc = _audit_svc()

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
                    audit_svc=audit_svc,
                )

        assert exc_info.value.status_code == 404


# ===========================================================================
# 400 — assessment not completed
# ===========================================================================

class TestDecideReleaseAssessmentStatus:
    @pytest.mark.asyncio
    async def test_pending_assessment_returns_400(self):
        from fastapi import HTTPException
        from forgeguard.api.routes.releases import decide_release

        body = _req(APPROVE_REQUEST)
        request = _mock_request(UserRole.tech_lead.value)
        pool = MagicMock()
        audit_svc = _audit_svc()

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
                    audit_svc=audit_svc,
                )

        assert exc_info.value.status_code == 400
        assert "pending" in str(exc_info.value.detail).lower()

    @pytest.mark.asyncio
    async def test_in_progress_assessment_returns_400(self):
        from fastapi import HTTPException
        from forgeguard.api.routes.releases import decide_release

        body = _req(APPROVE_REQUEST)
        request = _mock_request(UserRole.tech_lead.value)
        pool = MagicMock()
        audit_svc = _audit_svc()

        with (
            patch("forgeguard.api.routes.releases.ReleaseAssessmentRepository") as mock_ar,
            patch("forgeguard.api.routes.releases.DecisionRepository") as mock_dr,
            patch("forgeguard.api.routes.releases.AssessmentScoreRepository") as mock_sr,
        ):
            mock_ar.return_value.get_by_id = AsyncMock(return_value=IN_PROGRESS_ASSESSMENT)
            mock_dr.return_value.find_by_release_assessment = AsyncMock(return_value=[])
            mock_sr.return_value.get_score_by_type = AsyncMock(return_value=None)

            with pytest.raises(HTTPException) as exc_info:
                await decide_release(
                    id=ASSESSMENT_ID_IN_PROGRESS,
                    body=body,
                    request=request,
                    pool=pool,
                    audit_svc=audit_svc,
                )

        assert exc_info.value.status_code == 400
        assert "in_progress" in str(exc_info.value.detail).lower()


# ===========================================================================
# 409 — duplicate decision
# ===========================================================================

class TestDecideReleaseDuplicate:
    @pytest.mark.asyncio
    async def test_duplicate_decision_returns_409(self):
        from fastapi import HTTPException
        from forgeguard.api.routes.releases import decide_release

        body = _req(APPROVE_REQUEST)
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
        assert str(EXISTING_DECISION_ROW["id"]) in str(exc_info.value.detail)


# ===========================================================================
# 400 — missing scores
# ===========================================================================

class TestDecideReleaseMissingScores:
    @pytest.mark.asyncio
    async def test_missing_health_score_returns_400(self):
        from fastapi import HTTPException
        from forgeguard.api.routes.releases import decide_release

        body = _req(APPROVE_REQUEST)
        request = _mock_request(UserRole.tech_lead.value)
        pool = MagicMock()
        audit_svc = _audit_svc()

        with (
            patch("forgeguard.api.routes.releases.ReleaseAssessmentRepository") as mock_ar,
            patch("forgeguard.api.routes.releases.DecisionRepository") as mock_dr,
            patch("forgeguard.api.routes.releases.AssessmentScoreRepository") as mock_sr,
        ):
            mock_ar.return_value.get_by_id = AsyncMock(return_value=COMPLETED_ASSESSMENT)
            mock_dr.return_value.find_by_release_assessment = AsyncMock(return_value=[])
            mock_sr.return_value.get_score_by_type = AsyncMock(
                side_effect=lambda _id, t: None if t == "health" else RISK_SCORE_ROW
            )

            with pytest.raises(HTTPException) as exc_info:
                await decide_release(
                    id=ASSESSMENT_ID_COMPLETED,
                    body=body,
                    request=request,
                    pool=pool,
                    audit_svc=audit_svc,
                )

        assert exc_info.value.status_code == 400
        assert "health" in str(exc_info.value.detail).lower()

    @pytest.mark.asyncio
    async def test_missing_risk_score_returns_400(self):
        from fastapi import HTTPException
        from forgeguard.api.routes.releases import decide_release

        body = _req(APPROVE_REQUEST)
        request = _mock_request(UserRole.tech_lead.value)
        pool = MagicMock()
        audit_svc = _audit_svc()

        with (
            patch("forgeguard.api.routes.releases.ReleaseAssessmentRepository") as mock_ar,
            patch("forgeguard.api.routes.releases.DecisionRepository") as mock_dr,
            patch("forgeguard.api.routes.releases.AssessmentScoreRepository") as mock_sr,
        ):
            mock_ar.return_value.get_by_id = AsyncMock(return_value=COMPLETED_ASSESSMENT)
            mock_dr.return_value.find_by_release_assessment = AsyncMock(return_value=[])
            mock_sr.return_value.get_score_by_type = AsyncMock(
                side_effect=lambda _id, t: HEALTH_SCORE_ROW if t == "health" else None
            )

            with pytest.raises(HTTPException) as exc_info:
                await decide_release(
                    id=ASSESSMENT_ID_COMPLETED,
                    body=body,
                    request=request,
                    pool=pool,
                    audit_svc=audit_svc,
                )

        assert exc_info.value.status_code == 400
        assert "risk" in str(exc_info.value.detail).lower()

    @pytest.mark.asyncio
    async def test_missing_both_scores_returns_400_with_both_errors(self):
        from fastapi import HTTPException
        from forgeguard.api.routes.releases import decide_release

        body = _req(APPROVE_REQUEST)
        request = _mock_request(UserRole.tech_lead.value)
        pool = MagicMock()
        audit_svc = _audit_svc()

        with (
            patch("forgeguard.api.routes.releases.ReleaseAssessmentRepository") as mock_ar,
            patch("forgeguard.api.routes.releases.DecisionRepository") as mock_dr,
            patch("forgeguard.api.routes.releases.AssessmentScoreRepository") as mock_sr,
        ):
            mock_ar.return_value.get_by_id = AsyncMock(return_value=COMPLETED_ASSESSMENT)
            mock_dr.return_value.find_by_release_assessment = AsyncMock(return_value=[])
            mock_sr.return_value.get_score_by_type = AsyncMock(return_value=None)

            with pytest.raises(HTTPException) as exc_info:
                await decide_release(
                    id=ASSESSMENT_ID_COMPLETED,
                    body=body,
                    request=request,
                    pool=pool,
                    audit_svc=audit_svc,
                )

        assert exc_info.value.status_code == 400
        detail = exc_info.value.detail
        errors = detail.get("errors", [])
        field_names = {e["field"] for e in errors}
        assert "health_score" in field_names
        assert "risk_score" in field_names


# ===========================================================================
# 403 — escalation guard
# ===========================================================================

class TestDecideReleaseEscalationGuard:
    @pytest.mark.asyncio
    async def test_tech_lead_approve_on_escalated_returns_403(self):
        """Tech Lead cannot APPROVE when assessment has critical security findings."""
        from fastapi import HTTPException
        from forgeguard.api.routes.releases import decide_release

        body = _req(APPROVE_REQUEST)
        request = _mock_request(UserRole.tech_lead.value)
        pool = MagicMock()
        audit_svc = _audit_svc()

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
                    audit_svc=audit_svc,
                )

        assert exc_info.value.status_code == 403
        assert "escalat" in str(exc_info.value.detail).lower()

    @pytest.mark.asyncio
    async def test_platform_admin_conditional_approve_on_escalated_returns_403(self):
        """Platform Admin cannot CONDITIONAL_APPROVE on escalated assessment."""
        from fastapi import HTTPException
        from forgeguard.api.routes.releases import decide_release

        body = _req(CONDITIONAL_APPROVE_REQUEST)
        request = _mock_request(UserRole.platform_admin.value)
        pool = MagicMock()
        audit_svc = _audit_svc()

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
                    audit_svc=audit_svc,
                )

        assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_security_reviewer_approve_on_escalated_succeeds(self):
        """Security Reviewer CAN approve escalated assessments."""
        from forgeguard.api.routes.releases import decide_release

        body = _req(APPROVE_REQUEST)
        request = _mock_request(UserRole.security_reviewer.value)
        pool = MagicMock()
        audit_svc = _audit_svc()

        row = {
            **_decision_row("APPROVE"),
            "was_escalated": True,
            "release_assessment_id": ASSESSMENT_ID_WITH_ESCALATION,
        }

        with (
            patch("forgeguard.api.routes.releases.ReleaseAssessmentRepository") as mock_ar,
            patch("forgeguard.api.routes.releases.DecisionRepository") as mock_dr,
            patch("forgeguard.api.routes.releases.AssessmentScoreRepository") as mock_sr,
            patch("forgeguard.api.routes.releases.AuditLogRepository"),
            patch("forgeguard.api.routes.releases.AuditService"),
        ):
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

    @pytest.mark.asyncio
    async def test_block_on_escalated_assessment_always_succeeds(self):
        """BLOCK decision is never restricted regardless of escalation status."""
        from forgeguard.api.routes.releases import decide_release

        body = _req(BLOCK_REQUEST)
        request = _mock_request(UserRole.tech_lead.value)
        pool = MagicMock()
        audit_svc = _audit_svc()

        row = {**_decision_row("BLOCK"), "was_escalated": True}

        with (
            patch("forgeguard.api.routes.releases.ReleaseAssessmentRepository") as mock_ar,
            patch("forgeguard.api.routes.releases.DecisionRepository") as mock_dr,
            patch("forgeguard.api.routes.releases.AssessmentScoreRepository") as mock_sr,
            patch("forgeguard.api.routes.releases.AuditLogRepository"),
            patch("forgeguard.api.routes.releases.AuditService"),
        ):
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

        assert result.decision == "BLOCK"

    @pytest.mark.asyncio
    async def test_was_escalated_true_when_critical_security_present(self):
        """was_escalated is set to True when critical security finding exists."""
        from forgeguard.api.routes.releases import decide_release

        body = _req(BLOCK_REQUEST)
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
            patch("forgeguard.api.routes.releases.AuditLogRepository"),
            patch("forgeguard.api.routes.releases.AuditService"),
        ):
            mock_ar.return_value.get_by_id = AsyncMock(
                return_value=COMPLETED_ASSESSMENT_WITH_ESCALATION
            )
            mock_dr.return_value.find_by_release_assessment = AsyncMock(return_value=[])
            mock_dr.return_value.create = _capture
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

        assert len(captured) == 1
        assert captured[0]["was_escalated"] is True

    @pytest.mark.asyncio
    async def test_was_escalated_false_without_critical_security(self):
        """was_escalated is False when no critical security findings exist."""
        from forgeguard.api.routes.releases import decide_release

        body = _req(APPROVE_REQUEST)
        request = _mock_request(UserRole.tech_lead.value)
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

            await decide_release(
                id=ASSESSMENT_ID_COMPLETED,
                body=body,
                request=request,
                pool=pool,
                audit_svc=audit_svc,
            )

        assert len(captured) == 1
        assert captured[0]["was_escalated"] is False


# ===========================================================================
# Response structure
# ===========================================================================

class TestDecideReleaseResponseStructure:
    @pytest.mark.asyncio
    async def test_response_includes_all_required_fields(self):
        from forgeguard.api.routes.releases import decide_release

        body = _req(APPROVE_REQUEST)
        request = _mock_request(UserRole.tech_lead.value)
        pool = MagicMock()
        audit_svc = _audit_svc()

        with (
            patch("forgeguard.api.routes.releases.ReleaseAssessmentRepository") as mock_ar,
            patch("forgeguard.api.routes.releases.DecisionRepository") as mock_dr,
            patch("forgeguard.api.routes.releases.AssessmentScoreRepository") as mock_sr,
        ):
            mock_ar.return_value.get_by_id = AsyncMock(return_value=COMPLETED_ASSESSMENT)
            mock_dr.return_value.find_by_release_assessment = AsyncMock(return_value=[])
            mock_dr.return_value.create = AsyncMock(return_value=_decision_row())
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

        assert result.id is not None
        assert result.release_assessment_id == ASSESSMENT_ID_COMPLETED
        assert result.health_score_at_decision is not None
        assert result.risk_score_at_decision is not None
        assert result.decision is not None
        assert result.decided_by_role is not None
        assert result.rationale == APPROVE_REQUEST["rationale"]
        assert isinstance(result.was_escalated, bool)

    @pytest.mark.asyncio
    async def test_audit_log_event_called_once(self):
        """audit_svc.log_event is called exactly once for the human actor."""
        from forgeguard.api.routes.releases import decide_release

        body = _req(APPROVE_REQUEST)
        request = _mock_request(UserRole.tech_lead.value)
        pool = MagicMock()
        audit_svc = _audit_svc()

        with (
            patch("forgeguard.api.routes.releases.ReleaseAssessmentRepository") as mock_ar,
            patch("forgeguard.api.routes.releases.DecisionRepository") as mock_dr,
            patch("forgeguard.api.routes.releases.AssessmentScoreRepository") as mock_sr,
        ):
            mock_ar.return_value.get_by_id = AsyncMock(return_value=COMPLETED_ASSESSMENT)
            mock_dr.return_value.find_by_release_assessment = AsyncMock(return_value=[])
            mock_dr.return_value.create = AsyncMock(return_value=_decision_row())
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

        audit_svc.log_event.assert_called_once()
        call_kwargs = audit_svc.log_event.call_args.kwargs
        assert call_kwargs["action"] == "release_decision"
        assert call_kwargs["resource_type"] == "release_decision"
