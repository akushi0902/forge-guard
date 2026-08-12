"""Unit tests for CombinedDecisionViewService (WO-052).

Tests cover:
    1. APPROVE scenario — all fields populated, no conditions
    2. CONDITIONAL_APPROVE — conditions derived from HIGH severity findings
    3. BLOCK scenario — scoring-driven, no escalation
    4. Escalated assessment — critical security finding overrides APPROVE → BLOCK
    5. Pre-decision state (no human decision yet) — decision_record is None
    6. Post-decision state — decision_record populated with human reviewer data
    7. Zero findings — empty findings_summary, no conditions
    8. No scores — scoring_incomplete=True, default BLOCK recommendation
    9. Findings grouped by severity with correct counts
    10. Findings truncated at _MAX_PER_SEVERITY (50) per group

All tests use mocked repositories — no database or network I/O.

Run:
    pytest tests/unit/services/decision_engine/test_decision_view_service.py -v
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

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
    HUMAN_DECISION_BLOCK,
    RISK_APPROVE,
    RISK_BLOCK,
    RISK_CONDITIONAL,
    RISK_ESCALATED,
    RISK_ZERO,
    HIGH_CODE_QUALITY_FINDING,
    HIGH_DEPENDENCY_FINDING,
    CRITICAL_SECURITY_FINDING,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_service(
    assessment: dict | None,
    health: dict | None,
    risk: dict | None,
    decisions: list[dict],
) -> "CombinedDecisionViewService":
    from forgeguard.services.decision_engine.decision_view_service import (
        CombinedDecisionViewService,
    )

    assessment_repo = MagicMock()
    assessment_repo.get_by_id = AsyncMock(return_value=assessment)

    score_repo = MagicMock()
    score_repo.get_score_by_type = AsyncMock(
        side_effect=lambda _id, t: health if t == "health" else risk
    )

    decision_repo = MagicMock()
    decision_repo.find_by_release_assessment = AsyncMock(return_value=decisions)

    return CombinedDecisionViewService(assessment_repo, score_repo, decision_repo)


# ===========================================================================
# 1. Returns None when assessment does not exist
# ===========================================================================

class TestAssessmentNotFound:
    @pytest.mark.asyncio
    async def test_returns_none_for_missing_assessment(self):
        svc = _make_service(None, None, None, [])
        result = await svc.get_combined_view(uuid.uuid4())
        assert result is None


# ===========================================================================
# 2. APPROVE scenario
# ===========================================================================

class TestApproveScenario:
    @pytest.mark.asyncio
    async def test_recommendation_is_approve(self):
        svc = _make_service(ASSESSMENT_APPROVE, HEALTH_APPROVE, RISK_APPROVE, [])
        result = await svc.get_combined_view(ASSESS_APPROVE)
        assert result is not None
        assert result.system_recommendation.decision == "APPROVE"

    @pytest.mark.asyncio
    async def test_health_breakdown_populated(self):
        svc = _make_service(ASSESSMENT_APPROVE, HEALTH_APPROVE, RISK_APPROVE, [])
        result = await svc.get_combined_view(ASSESS_APPROVE)
        assert result.health_score is not None
        assert result.health_score.overall == pytest.approx(80.0)

    @pytest.mark.asyncio
    async def test_risk_breakdown_populated(self):
        svc = _make_service(ASSESSMENT_APPROVE, HEALTH_APPROVE, RISK_APPROVE, [])
        result = await svc.get_combined_view(ASSESS_APPROVE)
        assert result.risk_score is not None
        assert result.risk_score.overall == pytest.approx(20.0)

    @pytest.mark.asyncio
    async def test_conditions_is_none_for_approve(self):
        svc = _make_service(ASSESSMENT_APPROVE, HEALTH_APPROVE, RISK_APPROVE, [])
        result = await svc.get_combined_view(ASSESS_APPROVE)
        assert result.conditions is None

    @pytest.mark.asyncio
    async def test_escalation_not_triggered(self):
        svc = _make_service(ASSESSMENT_APPROVE, HEALTH_APPROVE, RISK_APPROVE, [])
        result = await svc.get_combined_view(ASSESS_APPROVE)
        assert result.escalation.is_escalated is False

    @pytest.mark.asyncio
    async def test_scoring_complete(self):
        svc = _make_service(ASSESSMENT_APPROVE, HEALTH_APPROVE, RISK_APPROVE, [])
        result = await svc.get_combined_view(ASSESS_APPROVE)
        assert result.scoring_incomplete is False


# ===========================================================================
# 3. CONDITIONAL_APPROVE scenario
# ===========================================================================

class TestConditionalApproveScenario:
    @pytest.mark.asyncio
    async def test_recommendation_is_conditional_approve(self):
        svc = _make_service(ASSESSMENT_CONDITIONAL, HEALTH_CONDITIONAL, RISK_CONDITIONAL, [])
        result = await svc.get_combined_view(ASSESS_CONDITIONAL)
        assert result is not None
        assert result.system_recommendation.decision == "CONDITIONAL_APPROVE"

    @pytest.mark.asyncio
    async def test_conditions_populated_from_high_findings(self):
        svc = _make_service(ASSESSMENT_CONDITIONAL, HEALTH_CONDITIONAL, RISK_CONDITIONAL, [])
        result = await svc.get_combined_view(ASSESS_CONDITIONAL)
        assert result.conditions is not None
        assert len(result.conditions) >= 1

    @pytest.mark.asyncio
    async def test_conditions_reference_high_severity_finding_ids(self):
        svc = _make_service(ASSESSMENT_CONDITIONAL, HEALTH_CONDITIONAL, RISK_CONDITIONAL, [])
        result = await svc.get_combined_view(ASSESS_CONDITIONAL)
        condition_ids = {str(c.source_finding_id) for c in result.conditions}
        assert HIGH_CODE_QUALITY_FINDING["id"] in condition_ids or HIGH_DEPENDENCY_FINDING["id"] in condition_ids

    @pytest.mark.asyncio
    async def test_findings_total_correct(self):
        svc = _make_service(ASSESSMENT_CONDITIONAL, HEALTH_CONDITIONAL, RISK_CONDITIONAL, [])
        result = await svc.get_combined_view(ASSESS_CONDITIONAL)
        # 2 high + 1 medium
        assert result.findings_summary.total == 3

    @pytest.mark.asyncio
    async def test_high_count_correct(self):
        svc = _make_service(ASSESSMENT_CONDITIONAL, HEALTH_CONDITIONAL, RISK_CONDITIONAL, [])
        result = await svc.get_combined_view(ASSESS_CONDITIONAL)
        assert result.findings_summary.by_severity["high"].count == 2


# ===========================================================================
# 4. BLOCK scenario (score-driven)
# ===========================================================================

class TestBlockScenario:
    @pytest.mark.asyncio
    async def test_recommendation_is_block(self):
        svc = _make_service(ASSESSMENT_BLOCK, HEALTH_BLOCK, RISK_BLOCK, [])
        result = await svc.get_combined_view(ASSESS_BLOCK)
        assert result is not None
        assert result.system_recommendation.decision == "BLOCK"

    @pytest.mark.asyncio
    async def test_conditions_is_none_for_block(self):
        svc = _make_service(ASSESSMENT_BLOCK, HEALTH_BLOCK, RISK_BLOCK, [])
        result = await svc.get_combined_view(ASSESS_BLOCK)
        assert result.conditions is None

    @pytest.mark.asyncio
    async def test_escalation_not_triggered_for_score_block(self):
        svc = _make_service(ASSESSMENT_BLOCK, HEALTH_BLOCK, RISK_BLOCK, [])
        result = await svc.get_combined_view(ASSESS_BLOCK)
        assert result.escalation.is_escalated is False


# ===========================================================================
# 5. Escalated scenario
# ===========================================================================

class TestEscalatedScenario:
    @pytest.mark.asyncio
    async def test_recommendation_is_block_despite_high_scores(self):
        svc = _make_service(ASSESSMENT_ESCALATED, HEALTH_ESCALATED, RISK_ESCALATED, [])
        result = await svc.get_combined_view(ASSESS_ESCALATED)
        assert result is not None
        assert result.system_recommendation.decision == "BLOCK"

    @pytest.mark.asyncio
    async def test_is_escalated_true(self):
        svc = _make_service(ASSESSMENT_ESCALATED, HEALTH_ESCALATED, RISK_ESCALATED, [])
        result = await svc.get_combined_view(ASSESS_ESCALATED)
        assert result.escalation.is_escalated is True

    @pytest.mark.asyncio
    async def test_escalation_reasons_populated(self):
        svc = _make_service(ASSESSMENT_ESCALATED, HEALTH_ESCALATED, RISK_ESCALATED, [])
        result = await svc.get_combined_view(ASSESS_ESCALATED)
        assert result.escalation.reasons is not None
        assert len(result.escalation.reasons) >= 1

    @pytest.mark.asyncio
    async def test_escalation_reason_contains_critical_finding_id(self):
        svc = _make_service(ASSESSMENT_ESCALATED, HEALTH_ESCALATED, RISK_ESCALATED, [])
        result = await svc.get_combined_view(ASSESS_ESCALATED)
        reason_ids = {r["finding_id"] for r in result.escalation.reasons}
        assert CRITICAL_SECURITY_FINDING["id"] in reason_ids


# ===========================================================================
# 6. Pre-decision state (no human decision yet)
# ===========================================================================

class TestPreDecisionState:
    @pytest.mark.asyncio
    async def test_decision_record_is_none(self):
        svc = _make_service(ASSESSMENT_APPROVE, HEALTH_APPROVE, RISK_APPROVE, [])
        result = await svc.get_combined_view(ASSESS_APPROVE)
        assert result.decision_record is None

    @pytest.mark.asyncio
    async def test_system_recommendation_still_computed(self):
        svc = _make_service(ASSESSMENT_APPROVE, HEALTH_APPROVE, RISK_APPROVE, [])
        result = await svc.get_combined_view(ASSESS_APPROVE)
        assert result.system_recommendation.decision is not None


# ===========================================================================
# 7. Post-decision state (human decision submitted)
# ===========================================================================

class TestPostDecisionState:
    @pytest.mark.asyncio
    async def test_decision_record_populated(self):
        svc = _make_service(ASSESSMENT_APPROVE, HEALTH_APPROVE, RISK_APPROVE, [HUMAN_DECISION_APPROVE])
        result = await svc.get_combined_view(ASSESS_APPROVE)
        assert result.decision_record is not None

    @pytest.mark.asyncio
    async def test_decision_record_has_correct_decision(self):
        svc = _make_service(ASSESSMENT_APPROVE, HEALTH_APPROVE, RISK_APPROVE, [HUMAN_DECISION_APPROVE])
        result = await svc.get_combined_view(ASSESS_APPROVE)
        assert result.decision_record.decision == "APPROVE"

    @pytest.mark.asyncio
    async def test_decision_record_has_reviewer_identity(self):
        svc = _make_service(ASSESSMENT_APPROVE, HEALTH_APPROVE, RISK_APPROVE, [HUMAN_DECISION_APPROVE])
        result = await svc.get_combined_view(ASSESS_APPROVE)
        assert result.decision_record.decided_by_role == "tech_lead"

    @pytest.mark.asyncio
    async def test_decision_record_has_rationale(self):
        svc = _make_service(ASSESSMENT_APPROVE, HEALTH_APPROVE, RISK_APPROVE, [HUMAN_DECISION_APPROVE])
        result = await svc.get_combined_view(ASSESS_APPROVE)
        assert result.decision_record.rationale == HUMAN_DECISION_APPROVE["rationale"]

    @pytest.mark.asyncio
    async def test_system_recommendation_present_alongside_human_decision(self):
        svc = _make_service(ASSESSMENT_APPROVE, HEALTH_APPROVE, RISK_APPROVE, [HUMAN_DECISION_APPROVE])
        result = await svc.get_combined_view(ASSESS_APPROVE)
        assert result.system_recommendation.decision is not None
        assert result.decision_record is not None


# ===========================================================================
# 8. Zero findings
# ===========================================================================

class TestZeroFindings:
    @pytest.mark.asyncio
    async def test_findings_total_is_zero(self):
        svc = _make_service(ASSESSMENT_ZERO_FINDINGS, HEALTH_ZERO, RISK_ZERO, [])
        result = await svc.get_combined_view(ASSESS_ZERO_FINDINGS)
        assert result.findings_summary.total == 0

    @pytest.mark.asyncio
    async def test_all_severity_counts_zero(self):
        svc = _make_service(ASSESSMENT_ZERO_FINDINGS, HEALTH_ZERO, RISK_ZERO, [])
        result = await svc.get_combined_view(ASSESS_ZERO_FINDINGS)
        for sev in ("critical", "high", "medium", "low"):
            assert result.findings_summary.by_severity[sev].count == 0

    @pytest.mark.asyncio
    async def test_no_escalation_with_zero_findings(self):
        svc = _make_service(ASSESSMENT_ZERO_FINDINGS, HEALTH_ZERO, RISK_ZERO, [])
        result = await svc.get_combined_view(ASSESS_ZERO_FINDINGS)
        assert result.escalation.is_escalated is False


# ===========================================================================
# 9. No scores (scoring_incomplete)
# ===========================================================================

class TestNoScores:
    @pytest.mark.asyncio
    async def test_scoring_incomplete_true(self):
        svc = _make_service(ASSESSMENT_NO_SCORES, None, None, [])
        result = await svc.get_combined_view(ASSESS_NO_SCORES)
        assert result.scoring_incomplete is True

    @pytest.mark.asyncio
    async def test_scoring_incomplete_reason_set(self):
        svc = _make_service(ASSESSMENT_NO_SCORES, None, None, [])
        result = await svc.get_combined_view(ASSESS_NO_SCORES)
        assert result.scoring_incomplete_reason is not None
        assert len(result.scoring_incomplete_reason) > 0

    @pytest.mark.asyncio
    async def test_default_block_recommendation_when_no_scores(self):
        svc = _make_service(ASSESSMENT_NO_SCORES, None, None, [])
        result = await svc.get_combined_view(ASSESS_NO_SCORES)
        assert result.system_recommendation.decision == "BLOCK"

    @pytest.mark.asyncio
    async def test_health_score_is_none_when_missing(self):
        svc = _make_service(ASSESSMENT_NO_SCORES, None, None, [])
        result = await svc.get_combined_view(ASSESS_NO_SCORES)
        assert result.health_score is None

    @pytest.mark.asyncio
    async def test_risk_score_is_none_when_missing(self):
        svc = _make_service(ASSESSMENT_NO_SCORES, None, None, [])
        result = await svc.get_combined_view(ASSESS_NO_SCORES)
        assert result.risk_score is None


# ===========================================================================
# 10. Large finding sets — truncation at MAX_PER_SEVERITY
# ===========================================================================

class TestLargeFindingSets:
    @pytest.mark.asyncio
    async def test_findings_truncated_at_50_per_severity(self):
        import json
        from tests.fixtures.decision_views import _base_assessment, ASSESS_APPROVE

        # Create 80 high-severity findings
        many_findings = [
            {
                "id": str(uuid.uuid4()),
                "title": f"Finding {i}",
                "severity": "high",
                "dimension": "security",
                "explanation": "Auto-generated",
                "business_impact": "",
                "remediation_steps": [],
                "confidence_score": 0.8,
                "source": "static_analysis",
            }
            for i in range(80)
        ]
        assessment = {
            **ASSESSMENT_APPROVE,
            "change_analysis": json.dumps({"findings": many_findings, "summary": {}}),
        }

        svc = _make_service(assessment, HEALTH_APPROVE, RISK_APPROVE, [])
        result = await svc.get_combined_view(ASSESS_APPROVE)

        # Count should reflect all 80, but items list capped at 50
        assert result.findings_summary.by_severity["high"].count == 80
        assert len(result.findings_summary.by_severity["high"].items) == 50

    @pytest.mark.asyncio
    async def test_total_count_includes_all_findings_above_limit(self):
        import json

        many_findings = [
            {
                "id": str(uuid.uuid4()),
                "title": f"High finding {i}",
                "severity": "high",
                "dimension": "code_quality",
                "explanation": None,
                "business_impact": "",
                "remediation_steps": [],
                "confidence_score": 0.7,
                "source": "static_analysis",
            }
            for i in range(60)
        ] + [
            {
                "id": str(uuid.uuid4()),
                "title": f"Critical finding {i}",
                "severity": "critical",
                "dimension": "security",
                "explanation": None,
                "business_impact": "",
                "remediation_steps": [],
                "confidence_score": 0.95,
                "source": "static_analysis",
            }
            for i in range(10)
        ]
        assessment = {
            **ASSESSMENT_APPROVE,
            "change_analysis": json.dumps({"findings": many_findings, "summary": {}}),
        }

        svc = _make_service(assessment, HEALTH_APPROVE, RISK_APPROVE, [])
        result = await svc.get_combined_view(ASSESS_APPROVE)

        assert result.findings_summary.total == 70
        assert result.findings_summary.by_severity["high"].count == 60
        assert result.findings_summary.by_severity["critical"].count == 10


# ===========================================================================
# 11. Assessment metadata in response
# ===========================================================================

class TestAssessmentMetadata:
    @pytest.mark.asyncio
    async def test_assessment_id_matches(self):
        svc = _make_service(ASSESSMENT_APPROVE, HEALTH_APPROVE, RISK_APPROVE, [])
        result = await svc.get_combined_view(ASSESS_APPROVE)
        assert str(result.assessment.id) == str(ASSESS_APPROVE)

    @pytest.mark.asyncio
    async def test_assessment_status_present(self):
        svc = _make_service(ASSESSMENT_APPROVE, HEALTH_APPROVE, RISK_APPROVE, [])
        result = await svc.get_combined_view(ASSESS_APPROVE)
        assert result.assessment.status == "completed"

    @pytest.mark.asyncio
    async def test_commit_sha_present(self):
        svc = _make_service(ASSESSMENT_APPROVE, HEALTH_APPROVE, RISK_APPROVE, [])
        result = await svc.get_combined_view(ASSESS_APPROVE)
        assert result.assessment.commit_sha == "a" * 40
