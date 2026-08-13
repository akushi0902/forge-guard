"""Integration tests for GET /api/v1/releases/{id}/decision endpoint (WO-052).

Tests cover:
    1. Full response structure validation against schema for APPROVE scenario
    2. Full response structure for CONDITIONAL_APPROVE with conditions
    3. Full response structure for BLOCK scenario
    4. Escalated assessment response (was_escalated=True in escalation info)
    5. 404 for non-existent assessment ID
    6. Response includes system_recommendation in pre-decision state
    7. Response includes decision_record in post-decision state
    8. Response time assertion for assessments with many findings (< 500ms)
    9. All severity groups present in findings_summary.by_severity
    10. Scoring incomplete flag when scores missing

These tests mock all database dependencies — no running PostgreSQL required.

Run:
    pytest tests/integration/api/test_decision_view_endpoint.py -v
"""

from __future__ import annotations

import time
import uuid
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tests.fixtures.decision_views import (
    ASSESS_APPROVE,
    ASSESS_BLOCK,
    ASSESS_CONDITIONAL,
    ASSESS_ESCALATED,
    ASSESS_NO_SCORES,
    ASSESS_ZERO_FINDINGS,
    ASSESSMENT_APPROVE,
    ASSESSMENT_BLOCK,
    ASSESSMENT_CONDITIONAL,
    ASSESSMENT_ESCALATED,
    ASSESSMENT_NO_SCORES,
    ASSESSMENT_ZERO_FINDINGS,
    HEALTH_APPROVE,
    HEALTH_BLOCK,
    HEALTH_CONDITIONAL,
    HEALTH_ESCALATED,
    HEALTH_ZERO,
    HUMAN_DECISION_APPROVE,
    RISK_APPROVE,
    RISK_BLOCK,
    RISK_CONDITIONAL,
    RISK_ESCALATED,
    RISK_ZERO,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _pool_mock() -> MagicMock:
    return MagicMock()


def _make_request(role: str = "tech_lead") -> MagicMock:
    req = MagicMock()
    req.state = MagicMock()
    req.state.user_role = role
    req.state.user_id = str(uuid.uuid4())
    return req


async def _call_endpoint(
    assessment_id: uuid.UUID,
    assessment: dict | None,
    health: dict | None,
    risk: dict | None,
    decisions: list[dict],
) -> Any:
    from forgeguard.api.routes.releases import get_release_decision_view

    pool = _pool_mock()

    with (
        patch("forgeguard.api.routes.releases.ReleaseAssessmentRepository") as mock_ar,
        patch("forgeguard.api.routes.releases.AssessmentScoreRepository") as mock_sr,
        patch("forgeguard.api.routes.releases.DecisionRepository") as mock_dr,
    ):
        mock_ar.return_value.get_by_id = AsyncMock(return_value=assessment)
        mock_sr.return_value.get_score_by_type = AsyncMock(
            side_effect=lambda _id, t: health if t == "health" else risk
        )
        mock_dr.return_value.find_by_release_assessment = AsyncMock(return_value=decisions)

        return await get_release_decision_view(id=assessment_id, pool=pool)


# ===========================================================================
# 1. Full response structure — APPROVE
# ===========================================================================

class TestResponseStructureApprove:
    @pytest.mark.asyncio
    async def test_response_has_assessment_key(self):
        result = await _call_endpoint(ASSESS_APPROVE, ASSESSMENT_APPROVE, HEALTH_APPROVE, RISK_APPROVE, [])
        assert "assessment" in result

    @pytest.mark.asyncio
    async def test_response_has_system_recommendation(self):
        result = await _call_endpoint(ASSESS_APPROVE, ASSESSMENT_APPROVE, HEALTH_APPROVE, RISK_APPROVE, [])
        assert "system_recommendation" in result
        assert result["system_recommendation"]["decision"] == "APPROVE"

    @pytest.mark.asyncio
    async def test_response_has_health_score(self):
        result = await _call_endpoint(ASSESS_APPROVE, ASSESSMENT_APPROVE, HEALTH_APPROVE, RISK_APPROVE, [])
        assert "health_score" in result
        assert result["health_score"]["overall"] == pytest.approx(80.0)

    @pytest.mark.asyncio
    async def test_response_has_risk_score(self):
        result = await _call_endpoint(ASSESS_APPROVE, ASSESSMENT_APPROVE, HEALTH_APPROVE, RISK_APPROVE, [])
        assert "risk_score" in result
        assert result["risk_score"]["overall"] == pytest.approx(20.0)

    @pytest.mark.asyncio
    async def test_response_has_findings_summary(self):
        result = await _call_endpoint(ASSESS_APPROVE, ASSESSMENT_APPROVE, HEALTH_APPROVE, RISK_APPROVE, [])
        assert "findings_summary" in result
        assert "total" in result["findings_summary"]
        assert "by_severity" in result["findings_summary"]

    @pytest.mark.asyncio
    async def test_response_has_escalation_info(self):
        result = await _call_endpoint(ASSESS_APPROVE, ASSESSMENT_APPROVE, HEALTH_APPROVE, RISK_APPROVE, [])
        assert "escalation" in result
        assert result["escalation"]["is_escalated"] is False

    @pytest.mark.asyncio
    async def test_decision_record_null_for_pre_decision(self):
        result = await _call_endpoint(ASSESS_APPROVE, ASSESSMENT_APPROVE, HEALTH_APPROVE, RISK_APPROVE, [])
        assert result["decision_record"] is None

    @pytest.mark.asyncio
    async def test_all_severity_groups_present(self):
        result = await _call_endpoint(ASSESS_APPROVE, ASSESSMENT_APPROVE, HEALTH_APPROVE, RISK_APPROVE, [])
        by_severity = result["findings_summary"]["by_severity"]
        for sev in ("critical", "high", "medium", "low"):
            assert sev in by_severity


# ===========================================================================
# 2. CONDITIONAL_APPROVE with conditions
# ===========================================================================

class TestResponseStructureConditional:
    @pytest.mark.asyncio
    async def test_recommendation_is_conditional_approve(self):
        result = await _call_endpoint(
            ASSESS_CONDITIONAL, ASSESSMENT_CONDITIONAL,
            HEALTH_CONDITIONAL, RISK_CONDITIONAL, []
        )
        assert result["system_recommendation"]["decision"] == "CONDITIONAL_APPROVE"

    @pytest.mark.asyncio
    async def test_conditions_array_present(self):
        result = await _call_endpoint(
            ASSESS_CONDITIONAL, ASSESSMENT_CONDITIONAL,
            HEALTH_CONDITIONAL, RISK_CONDITIONAL, []
        )
        assert result["conditions"] is not None
        assert len(result["conditions"]) >= 1

    @pytest.mark.asyncio
    async def test_condition_items_have_required_fields(self):
        result = await _call_endpoint(
            ASSESS_CONDITIONAL, ASSESSMENT_CONDITIONAL,
            HEALTH_CONDITIONAL, RISK_CONDITIONAL, []
        )
        for cond in result["conditions"]:
            assert "condition" in cond
            assert "source_finding_id" in cond


# ===========================================================================
# 3. BLOCK scenario
# ===========================================================================

class TestResponseStructureBlock:
    @pytest.mark.asyncio
    async def test_recommendation_is_block(self):
        result = await _call_endpoint(ASSESS_BLOCK, ASSESSMENT_BLOCK, HEALTH_BLOCK, RISK_BLOCK, [])
        assert result["system_recommendation"]["decision"] == "BLOCK"

    @pytest.mark.asyncio
    async def test_conditions_null_for_block(self):
        result = await _call_endpoint(ASSESS_BLOCK, ASSESSMENT_BLOCK, HEALTH_BLOCK, RISK_BLOCK, [])
        assert result["conditions"] is None


# ===========================================================================
# 4. Escalated assessment
# ===========================================================================

class TestEscalatedResponse:
    @pytest.mark.asyncio
    async def test_is_escalated_true(self):
        result = await _call_endpoint(
            ASSESS_ESCALATED, ASSESSMENT_ESCALATED,
            HEALTH_ESCALATED, RISK_ESCALATED, []
        )
        assert result["escalation"]["is_escalated"] is True

    @pytest.mark.asyncio
    async def test_recommendation_overridden_to_block(self):
        result = await _call_endpoint(
            ASSESS_ESCALATED, ASSESSMENT_ESCALATED,
            HEALTH_ESCALATED, RISK_ESCALATED, []
        )
        assert result["system_recommendation"]["decision"] == "BLOCK"

    @pytest.mark.asyncio
    async def test_escalation_reasons_populated(self):
        result = await _call_endpoint(
            ASSESS_ESCALATED, ASSESSMENT_ESCALATED,
            HEALTH_ESCALATED, RISK_ESCALATED, []
        )
        assert result["escalation"]["reasons"] is not None
        assert len(result["escalation"]["reasons"]) >= 1


# ===========================================================================
# 5. 404 for non-existent assessment
# ===========================================================================

class TestNotFound:
    @pytest.mark.asyncio
    async def test_raises_404_for_unknown_assessment(self):
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            await _call_endpoint(uuid.uuid4(), None, None, None, [])

        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_404_detail_message(self):
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            await _call_endpoint(uuid.uuid4(), None, None, None, [])

        assert "not found" in str(exc_info.value.detail).lower()


# ===========================================================================
# 6. Post-decision state (human decision record present)
# ===========================================================================

class TestPostDecisionResponse:
    @pytest.mark.asyncio
    async def test_decision_record_present(self):
        result = await _call_endpoint(
            ASSESS_APPROVE, ASSESSMENT_APPROVE, HEALTH_APPROVE, RISK_APPROVE,
            [HUMAN_DECISION_APPROVE]
        )
        assert result["decision_record"] is not None

    @pytest.mark.asyncio
    async def test_decision_record_has_decided_by_role(self):
        result = await _call_endpoint(
            ASSESS_APPROVE, ASSESSMENT_APPROVE, HEALTH_APPROVE, RISK_APPROVE,
            [HUMAN_DECISION_APPROVE]
        )
        assert result["decision_record"]["decided_by_role"] == "tech_lead"

    @pytest.mark.asyncio
    async def test_decision_record_has_rationale(self):
        result = await _call_endpoint(
            ASSESS_APPROVE, ASSESSMENT_APPROVE, HEALTH_APPROVE, RISK_APPROVE,
            [HUMAN_DECISION_APPROVE]
        )
        assert result["decision_record"]["rationale"] is not None

    @pytest.mark.asyncio
    async def test_system_recommendation_present_alongside_decision(self):
        result = await _call_endpoint(
            ASSESS_APPROVE, ASSESSMENT_APPROVE, HEALTH_APPROVE, RISK_APPROVE,
            [HUMAN_DECISION_APPROVE]
        )
        assert result["system_recommendation"] is not None
        assert result["decision_record"] is not None


# ===========================================================================
# 7. Response time assertion (< 500ms for 50 findings)
# ===========================================================================

class TestResponseTime:
    @pytest.mark.asyncio
    async def test_response_under_500ms_with_50_findings(self):
        import json

        findings_50 = [
            {
                "id": str(uuid.uuid4()),
                "title": f"Finding {i}",
                "severity": "high" if i % 4 == 0 else "medium",
                "dimension": "code_quality",
                "explanation": "Detected by static analysis",
                "business_impact": "",
                "remediation_steps": [],
                "confidence_score": 0.8,
                "source": "static_analysis",
            }
            for i in range(50)
        ]
        assessment = {
            **ASSESSMENT_APPROVE,
            "change_analysis": json.dumps({"findings": findings_50, "summary": {}}),
        }

        start = time.perf_counter()
        await _call_endpoint(ASSESS_APPROVE, assessment, HEALTH_APPROVE, RISK_APPROVE, [])
        elapsed_ms = (time.perf_counter() - start) * 1000

        assert elapsed_ms < 500, f"Response took {elapsed_ms:.1f}ms, expected < 500ms"


# ===========================================================================
# 8. Scoring incomplete
# ===========================================================================

class TestScoringIncomplete:
    @pytest.mark.asyncio
    async def test_scoring_incomplete_flag_when_no_scores(self):
        result = await _call_endpoint(ASSESS_NO_SCORES, ASSESSMENT_NO_SCORES, None, None, [])
        assert result["scoring_incomplete"] is True

    @pytest.mark.asyncio
    async def test_scoring_incomplete_reason_populated(self):
        result = await _call_endpoint(ASSESS_NO_SCORES, ASSESSMENT_NO_SCORES, None, None, [])
        assert result["scoring_incomplete_reason"] is not None

    @pytest.mark.asyncio
    async def test_health_score_null_when_missing(self):
        result = await _call_endpoint(ASSESS_NO_SCORES, ASSESSMENT_NO_SCORES, None, None, [])
        assert result["health_score"] is None

    @pytest.mark.asyncio
    async def test_risk_score_null_when_missing(self):
        result = await _call_endpoint(ASSESS_NO_SCORES, ASSESSMENT_NO_SCORES, None, None, [])
        assert result["risk_score"] is None
