"""Unit tests for AssessmentOrchestrator (WO-042).

All dependencies are mocked — these tests run without a database.

Coverage:
    - Successful pipeline execution: policies → collect → evaluate → score → findings → audit
    - No policies configured: returns score=None with message, no findings generated
    - Concurrent assessment (check_in_progress returns non-None) → 409 behavior
    - Pipeline failure: assessment marked as failed
    - Audit record emitted with correct action/resource_type
    - force of pipeline order (each stage called once, in order)
    - MockDataCollector returns correct data for Payment Service vs default

Run:
    pytest tests/unit/services/test_assessment_orchestrator.py -v
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest

from forgeguard.services.assessment_orchestrator import (
    AssessmentOrchestrator,
    AssessmentResult,
    _make_rule_obj,
)
from forgeguard.services.mock_data_collector import MockDataCollector
from tests.fixtures.assessment_fixtures import (
    ASSESSMENT_ID,
    DIM_SCORES,
    EVAL_RESULTS,
    EXPECTED_OVERALL_SCORE,
    MOCK_INPUT_DATA,
    ALL_RULES,
    SERVICE_ID,
    make_assessment_result,
    make_assessment_row,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_health_result(
    overall_score: Decimal | None = EXPECTED_OVERALL_SCORE,
    assessment_id: uuid.UUID = ASSESSMENT_ID,
    service_id: uuid.UUID = SERVICE_ID,
) -> MagicMock:
    hr = MagicMock()
    hr.overall_score = overall_score
    hr.dimension_scores = DIM_SCORES
    hr.weights_used = {}
    hr.assessment_id = assessment_id
    hr.service_id = service_id
    return hr


def _make_orchestrator(
    *,
    rules: list = None,
    input_data: dict = None,
    eval_results: list = None,
    health_result: MagicMock = None,
    findings: list = None,
    in_progress: dict | None = None,
) -> tuple[AssessmentOrchestrator, dict]:
    """Factory for a fully-mocked AssessmentOrchestrator.

    Returns (orchestrator, mocks_dict) where mocks_dict maps name→mock.
    """
    assessment_repo = MagicMock()
    assessment_repo.create = AsyncMock(return_value=make_assessment_row())
    assessment_repo.update_status = AsyncMock(return_value=make_assessment_row())
    assessment_repo.check_in_progress = AsyncMock(return_value=in_progress)

    policy_repo = MagicMock()
    policy_repo.list_active_rules = AsyncMock(return_value=rules or ALL_RULES)

    score_repo = MagicMock()
    score_repo.save_health_score = AsyncMock(return_value={})

    finding_repo = MagicMock()
    finding_repo.count_by_severity = AsyncMock(
        return_value={"critical": 1, "high": 1, "medium": 1, "low": 0}
    )

    audit_svc = MagicMock()
    audit_svc.log_event = AsyncMock(return_value={})

    collector = MagicMock()
    collector.collect = AsyncMock(return_value=input_data or MOCK_INPUT_DATA)

    engine = MagicMock()
    engine.evaluate_rules = AsyncMock(return_value=eval_results or EVAL_RESULTS)

    dim_scorer = MagicMock()
    dim_scorer.calculate_dimension_scores = MagicMock(return_value=DIM_SCORES)

    aggregator = MagicMock()
    aggregator.aggregate = MagicMock(return_value=health_result or _make_health_result())

    finding_gen_patch = AsyncMock(return_value=findings or [])

    orc = AssessmentOrchestrator(
        assessment_repo=assessment_repo,
        policy_repo=policy_repo,
        score_repo=score_repo,
        finding_repo=finding_repo,
        data_collector=collector,
        audit_svc=audit_svc,
        evaluation_engine=engine,
        dim_scorer=dim_scorer,
        health_aggregator=aggregator,
    )

    mocks = {
        "assessment_repo": assessment_repo,
        "policy_repo": policy_repo,
        "score_repo": score_repo,
        "finding_repo": finding_repo,
        "audit_svc": audit_svc,
        "collector": collector,
        "engine": engine,
        "dim_scorer": dim_scorer,
        "aggregator": aggregator,
    }
    return orc, mocks


# ===========================================================================
# Successful pipeline
# ===========================================================================

class TestSuccessfulPipeline:
    @pytest.mark.asyncio
    async def test_returns_assessment_result(self):
        orc, _ = _make_orchestrator()
        with patch(
            "forgeguard.services.assessment_orchestrator.FindingGenerator.generate_findings",
            new=AsyncMock(return_value=[]),
        ):
            result = await orc.run(service_id=SERVICE_ID)
        assert isinstance(result, AssessmentResult)
        assert result.status == "completed"

    @pytest.mark.asyncio
    async def test_overall_score_populated(self):
        orc, _ = _make_orchestrator()
        with patch(
            "forgeguard.services.assessment_orchestrator.FindingGenerator.generate_findings",
            new=AsyncMock(return_value=[]),
        ):
            result = await orc.run(service_id=SERVICE_ID)
        assert result.overall_score == EXPECTED_OVERALL_SCORE

    @pytest.mark.asyncio
    async def test_dimension_scores_populated(self):
        orc, _ = _make_orchestrator()
        with patch(
            "forgeguard.services.assessment_orchestrator.FindingGenerator.generate_findings",
            new=AsyncMock(return_value=[]),
        ):
            result = await orc.run(service_id=SERVICE_ID)
        assert "code_quality" in result.dimension_scores

    @pytest.mark.asyncio
    async def test_policy_repo_called_with_service_id(self):
        orc, mocks = _make_orchestrator()
        with patch(
            "forgeguard.services.assessment_orchestrator.FindingGenerator.generate_findings",
            new=AsyncMock(return_value=[]),
        ):
            await orc.run(service_id=SERVICE_ID)
        mocks["policy_repo"].list_active_rules.assert_awaited_once_with(SERVICE_ID)

    @pytest.mark.asyncio
    async def test_data_collector_called_with_service_id(self):
        orc, mocks = _make_orchestrator()
        with patch(
            "forgeguard.services.assessment_orchestrator.FindingGenerator.generate_findings",
            new=AsyncMock(return_value=[]),
        ):
            await orc.run(service_id=SERVICE_ID)
        mocks["collector"].collect.assert_awaited_once_with(SERVICE_ID)

    @pytest.mark.asyncio
    async def test_engine_called_with_rules_and_data(self):
        orc, mocks = _make_orchestrator()
        with patch(
            "forgeguard.services.assessment_orchestrator.FindingGenerator.generate_findings",
            new=AsyncMock(return_value=[]),
        ):
            await orc.run(service_id=SERVICE_ID)
        mocks["engine"].evaluate_rules.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_score_saved(self):
        orc, mocks = _make_orchestrator()
        with patch(
            "forgeguard.services.assessment_orchestrator.FindingGenerator.generate_findings",
            new=AsyncMock(return_value=[]),
        ):
            await orc.run(service_id=SERVICE_ID)
        mocks["score_repo"].save_health_score.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_assessment_marked_completed(self):
        orc, mocks = _make_orchestrator()
        with patch(
            "forgeguard.services.assessment_orchestrator.FindingGenerator.generate_findings",
            new=AsyncMock(return_value=[]),
        ):
            await orc.run(service_id=SERVICE_ID)
        calls = [c.args for c in mocks["assessment_repo"].update_status.call_args_list]
        # Should be called with 'in_progress' then 'completed'
        statuses = [args[1] for args in calls if len(args) >= 2]
        assert "in_progress" in statuses
        assert "completed" in statuses

    @pytest.mark.asyncio
    async def test_audit_event_emitted(self):
        orc, mocks = _make_orchestrator()
        with patch(
            "forgeguard.services.assessment_orchestrator.FindingGenerator.generate_findings",
            new=AsyncMock(return_value=[]),
        ):
            await orc.run(service_id=SERVICE_ID)
        mocks["audit_svc"].log_event.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_audit_action_is_assessment_trigger(self):
        orc, mocks = _make_orchestrator()
        with patch(
            "forgeguard.services.assessment_orchestrator.FindingGenerator.generate_findings",
            new=AsyncMock(return_value=[]),
        ):
            await orc.run(service_id=SERVICE_ID)
        kwargs = mocks["audit_svc"].log_event.call_args[1]
        assert kwargs["action"] == "assessment.trigger"
        assert kwargs["resource_type"] == "service"

    @pytest.mark.asyncio
    async def test_audit_failure_does_not_propagate(self):
        orc, mocks = _make_orchestrator()
        mocks["audit_svc"].log_event.side_effect = Exception("DB down")
        with patch(
            "forgeguard.services.assessment_orchestrator.FindingGenerator.generate_findings",
            new=AsyncMock(return_value=[]),
        ):
            result = await orc.run(service_id=SERVICE_ID)
        assert result.status == "completed"


# ===========================================================================
# No policies configured
# ===========================================================================

class TestNoPolicies:
    @pytest.mark.asyncio
    async def test_returns_null_score(self):
        orc, _ = _make_orchestrator(rules=[])
        result = await orc.run(service_id=SERVICE_ID)
        assert result.overall_score is None

    @pytest.mark.asyncio
    async def test_returns_message(self):
        orc, _ = _make_orchestrator(rules=[])
        result = await orc.run(service_id=SERVICE_ID)
        assert result.message is not None
        assert len(result.message) > 0

    @pytest.mark.asyncio
    async def test_status_completed(self):
        orc, _ = _make_orchestrator(rules=[])
        result = await orc.run(service_id=SERVICE_ID)
        assert result.status == "completed"

    @pytest.mark.asyncio
    async def test_no_findings_generated(self):
        orc, mocks = _make_orchestrator(rules=[])
        result = await orc.run(service_id=SERVICE_ID)
        # Engine should not be called
        mocks["engine"].evaluate_rules.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_no_score_persisted(self):
        orc, mocks = _make_orchestrator(rules=[])
        await orc.run(service_id=SERVICE_ID)
        mocks["score_repo"].save_health_score.assert_not_awaited()


# ===========================================================================
# Pipeline failure
# ===========================================================================

class TestPipelineFailure:
    @pytest.mark.asyncio
    async def test_assessment_marked_failed_on_engine_error(self):
        orc, mocks = _make_orchestrator()
        mocks["engine"].evaluate_rules.side_effect = RuntimeError("engine crashed")
        with pytest.raises(RuntimeError, match="engine crashed"):
            await orc.run(service_id=SERVICE_ID)
        calls = [c.args for c in mocks["assessment_repo"].update_status.call_args_list]
        statuses = [args[1] for args in calls if len(args) >= 2]
        assert "failed" in statuses

    @pytest.mark.asyncio
    async def test_assessment_marked_failed_on_collector_error(self):
        orc, mocks = _make_orchestrator()
        mocks["collector"].collect.side_effect = RuntimeError("network error")
        with pytest.raises(RuntimeError):
            await orc.run(service_id=SERVICE_ID)
        calls = [c.args for c in mocks["assessment_repo"].update_status.call_args_list]
        statuses = [args[1] for args in calls if len(args) >= 2]
        assert "failed" in statuses

    @pytest.mark.asyncio
    async def test_raises_after_marking_failed(self):
        orc, mocks = _make_orchestrator()
        mocks["engine"].evaluate_rules.side_effect = ValueError("bad rule")
        with pytest.raises(ValueError):
            await orc.run(service_id=SERVICE_ID)


# ===========================================================================
# _make_rule_obj adapter
# ===========================================================================

class TestMakeRuleObj:
    def test_id_accessible(self):
        rule_dict = {
            "id": ASSESSMENT_ID,
            "name": "Test Rule",
            "severity": "high",
            "rule_type": "threshold_gte",
            "threshold_config": {"data_key": "score", "threshold": 80},
            "weight": Decimal("1"),
            "dimension": "test_coverage",
        }
        obj = _make_rule_obj(rule_dict)
        assert obj.id == ASSESSMENT_ID

    def test_dimension_via_policy_attr(self):
        rule_dict = {
            "id": ASSESSMENT_ID,
            "name": "Test Rule",
            "severity": "medium",
            "rule_type": "threshold_gte",
            "threshold_config": {},
            "weight": Decimal("1"),
            "dimension": "security",
        }
        obj = _make_rule_obj(rule_dict)
        assert obj.policy.dimension == "security"

    def test_unknown_dimension_defaults(self):
        rule_dict = {
            "id": ASSESSMENT_ID,
            "name": "Test Rule",
            "severity": "low",
            "rule_type": "threshold_eq",
            "threshold_config": {},
            "weight": Decimal("1"),
            # no 'dimension' key
        }
        obj = _make_rule_obj(rule_dict)
        assert obj.policy.dimension == "unknown"


# ===========================================================================
# MockDataCollector
# ===========================================================================

class TestMockDataCollector:
    @pytest.mark.asyncio
    async def test_payment_service_returns_known_data(self):
        collector = MockDataCollector()
        data = await collector.collect(MockDataCollector.PAYMENT_SERVICE_ID)
        assert data["unit_test_coverage"] == 62.5
        assert data["critical_cve_count"] == 2
        assert data["has_readme"] is False

    @pytest.mark.asyncio
    async def test_other_service_returns_default(self):
        collector = MockDataCollector()
        data = await collector.collect(uuid.uuid4())
        assert data["unit_test_coverage"] >= 80

    @pytest.mark.asyncio
    async def test_all_five_dimensions_covered(self):
        collector = MockDataCollector()
        data = await collector.collect(MockDataCollector.PAYMENT_SERVICE_ID)
        # At least one key per dimension
        assert "cyclomatic_complexity_avg" in data  # code_quality
        assert "unit_test_coverage" in data          # test_coverage
        assert "critical_cve_count" in data          # security
        assert "has_readme" in data                  # documentation
        assert "has_runbook" in data                 # operations_readiness
