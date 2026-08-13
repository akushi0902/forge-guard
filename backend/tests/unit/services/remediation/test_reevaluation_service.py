"""Unit tests for ReEvaluationService (WO-061).

Coverage:
    - Finding resolved (rule passes): status → remediated, resolved_at set
    - Finding not resolved (rule fails): status → acknowledged, updated guidance generated
    - Excepted finding rejected with 400
    - Already-remediated finding rejected with 409
    - Optimistic lock conflict detected and raised as ConflictError
    - before_health_score null when no prior score exists
    - Audit log always called
    - AI guidance fallback on circuit open

Run:
    pytest tests/unit/services/remediation/test_reevaluation_service.py -v
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from forgeguard.core.exceptions import BadRequestError, ConflictError, NotFoundError
from forgeguard.services.ai_engine.errors import CircuitOpenError
from forgeguard.services.domain.evaluation import EvaluationStatus, RuleEvaluationResult
from forgeguard.services.domain.severity import SeverityLevel

_SERVICE_ID = uuid.UUID("a0000000-0000-0000-0000-000000000001")
_FINDING_ID = uuid.UUID("b0000000-0000-0000-0000-000000000001")
_RULE_ID = uuid.UUID("c0000000-0000-0000-0000-000000000001")


def _finding(status: str = "open", version: int = 1) -> dict[str, Any]:
    return {
        "id": _FINDING_ID,
        "service_id": _SERVICE_ID,
        "policy_rule_id": _RULE_ID,
        "status": status,
        "version": version,
        "severity": "high",
        "dimension": "test_coverage",
        "title": "Coverage too low",
        "description": "Unit test coverage below threshold",
        "evidence": {"data_key": "unit_test_coverage"},
        "resolved_at": None,
        "created_at": datetime(2026, 1, 1, tzinfo=timezone.utc),
    }


def _rule_row(dimension: str = "test_coverage") -> dict[str, Any]:
    return {
        "id": _RULE_ID,
        "name": "Unit test coverage",
        "rule_type": "threshold_gte",
        "threshold_config": {"data_key": "unit_test_coverage", "numeric_value": "80"},
        "severity": "high",
        "weight": Decimal("20"),
        "is_active": True,
        "dimension": dimension,
    }


def _eval_result(passed: bool, rule_id: uuid.UUID = _RULE_ID) -> RuleEvaluationResult:
    return RuleEvaluationResult(
        rule_id=rule_id,
        rule_name="Unit test coverage",
        dimension="test_coverage",
        severity=SeverityLevel.HIGH,
        status=EvaluationStatus.PASS if passed else EvaluationStatus.FAIL,
        actual_value=85.0 if passed else 62.5,
        expected_value=80.0,
        evidence={"data_key": "unit_test_coverage"},
        evaluated_at=datetime.now(tz=timezone.utc),
        weight=Decimal("20"),
    )


def _score_row(overall: float) -> dict[str, Any]:
    return {
        "id": uuid.uuid4(),
        "service_id": _SERVICE_ID,
        "score_type": "health",
        "overall_score": Decimal(str(overall)),
        "created_at": datetime(2026, 1, 1, tzinfo=timezone.utc),
    }


def _make_ai_engine(content: str = "Updated guidance text.") -> MagicMock:
    resp = MagicMock()
    resp.content = content
    resp.confidence_score = 0.85
    ai = MagicMock()
    ai.generate_completion = AsyncMock(return_value=resp)
    return ai


def _make_service(
    *,
    finding_row: dict | None = None,
    rule_rows: list[dict] | None = None,
    eval_results: list | None = None,
    score_row: dict | None = None,
    update_return: dict | None = None,
    ai_engine: Any = None,
):
    from forgeguard.services.remediation.reevaluation_service import ReEvaluationService

    finding_repo = MagicMock()
    finding_repo.get_by_id = AsyncMock(return_value=finding_row)
    finding_repo.update_with_optimistic_lock = AsyncMock(
        return_value=update_return or (finding_row or {})
    )

    policy_repo = MagicMock()
    policy_repo.list_active_rules = AsyncMock(return_value=rule_rows or [])

    score_repo = MagicMock()
    score_repo.get_latest_health_score = AsyncMock(return_value=score_row)
    score_repo.create = AsyncMock(return_value={"id": uuid.uuid4()})

    assessment_repo = MagicMock()
    assessment_repo.create = AsyncMock(return_value={"id": uuid.uuid4()})

    audit_svc = MagicMock()
    audit_svc.log_event = AsyncMock(return_value=None)

    evaluation_engine = MagicMock()
    evaluation_engine.evaluate_rules = AsyncMock(return_value=eval_results or [])

    data_collector = MagicMock()
    data_collector.collect = AsyncMock(return_value={"unit_test_coverage": 85.0})

    svc = ReEvaluationService(
        finding_repo=finding_repo,
        policy_repo=policy_repo,
        score_repo=score_repo,
        assessment_repo=assessment_repo,
        audit_svc=audit_svc,
        ai_engine=ai_engine or _make_ai_engine(),
        evaluation_engine=evaluation_engine,
        data_collector=data_collector,
    )
    return svc, {
        "finding_repo": finding_repo,
        "policy_repo": policy_repo,
        "score_repo": score_repo,
        "assessment_repo": assessment_repo,
        "audit_svc": audit_svc,
        "evaluation_engine": evaluation_engine,
        "data_collector": data_collector,
    }


# ---------------------------------------------------------------------------
# 404 / basic guards
# ---------------------------------------------------------------------------

class TestNotFound:
    @pytest.mark.asyncio
    async def test_404_when_finding_missing(self):
        svc, _ = _make_service(finding_row=None)
        with pytest.raises(NotFoundError):
            await svc.re_evaluate(_FINDING_ID, actor_role="developer")


class TestStatusGuards:
    @pytest.mark.asyncio
    async def test_400_for_excepted_finding(self):
        svc, _ = _make_service(finding_row=_finding(status="exception_granted"))
        with pytest.raises(BadRequestError) as exc_info:
            await svc.re_evaluate(_FINDING_ID, actor_role="developer")
        assert exc_info.value.details["error_code"] == "EXCEPTED_FINDING"

    @pytest.mark.asyncio
    async def test_409_for_remediated_finding(self):
        svc, _ = _make_service(finding_row=_finding(status="remediated"))
        with pytest.raises(ConflictError) as exc_info:
            await svc.re_evaluate(_FINDING_ID, actor_role="developer")
        assert exc_info.value.details["error_code"] == "FINDING_ALREADY_RESOLVED"

    @pytest.mark.asyncio
    async def test_open_finding_proceeds(self):
        rule = _rule_row()
        svc, _ = _make_service(
            finding_row=_finding(status="open"),
            rule_rows=[rule],
            eval_results=[_eval_result(passed=True)],
            score_row=_score_row(60.0),
        )
        result = await svc.re_evaluate(_FINDING_ID, actor_role="developer")
        assert result is not None

    @pytest.mark.asyncio
    async def test_acknowledged_finding_proceeds(self):
        rule = _rule_row()
        svc, _ = _make_service(
            finding_row=_finding(status="acknowledged"),
            rule_rows=[rule],
            eval_results=[_eval_result(passed=False)],
            score_row=_score_row(40.0),
        )
        result = await svc.re_evaluate(_FINDING_ID, actor_role="developer")
        assert result is not None


# ---------------------------------------------------------------------------
# Resolved path (rule passes)
# ---------------------------------------------------------------------------

class TestResolved:
    @pytest.mark.asyncio
    async def test_after_status_is_remediated_on_pass(self):
        rule = _rule_row()
        svc, _ = _make_service(
            finding_row=_finding(status="open"),
            rule_rows=[rule],
            eval_results=[_eval_result(passed=True)],
            score_row=_score_row(70.0),
        )
        result = await svc.re_evaluate(_FINDING_ID, actor_role="developer")
        assert result.after_finding_status == "remediated"

    @pytest.mark.asyncio
    async def test_before_status_captured_correctly(self):
        rule = _rule_row()
        svc, _ = _make_service(
            finding_row=_finding(status="open"),
            rule_rows=[rule],
            eval_results=[_eval_result(passed=True)],
            score_row=_score_row(70.0),
        )
        result = await svc.re_evaluate(_FINDING_ID, actor_role="developer")
        assert result.before_finding_status == "open"

    @pytest.mark.asyncio
    async def test_rule_results_populated(self):
        rule = _rule_row()
        svc, _ = _make_service(
            finding_row=_finding(status="open"),
            rule_rows=[rule],
            eval_results=[_eval_result(passed=True)],
            score_row=_score_row(70.0),
        )
        result = await svc.re_evaluate(_FINDING_ID, actor_role="developer")
        assert len(result.rule_results) == 1
        assert result.rule_results[0].passed is True

    @pytest.mark.asyncio
    async def test_no_updated_guidance_on_resolved(self):
        rule = _rule_row()
        svc, _ = _make_service(
            finding_row=_finding(status="open"),
            rule_rows=[rule],
            eval_results=[_eval_result(passed=True)],
            score_row=_score_row(70.0),
        )
        result = await svc.re_evaluate(_FINDING_ID, actor_role="developer")
        assert result.updated_guidance is None

    @pytest.mark.asyncio
    async def test_optimistic_lock_update_called(self):
        rule = _rule_row()
        svc, mocks = _make_service(
            finding_row=_finding(status="open", version=3),
            rule_rows=[rule],
            eval_results=[_eval_result(passed=True)],
            score_row=_score_row(70.0),
        )
        await svc.re_evaluate(_FINDING_ID, actor_role="developer")
        mocks["finding_repo"].update_with_optimistic_lock.assert_called_once()
        call_args = mocks["finding_repo"].update_with_optimistic_lock.call_args
        assert call_args[0][1] == 3  # expected_version == 3


# ---------------------------------------------------------------------------
# Not-resolved path (rule fails)
# ---------------------------------------------------------------------------

class TestNotResolved:
    @pytest.mark.asyncio
    async def test_after_status_is_acknowledged_when_fails_from_open(self):
        rule = _rule_row()
        svc, _ = _make_service(
            finding_row=_finding(status="open"),
            rule_rows=[rule],
            eval_results=[_eval_result(passed=False)],
            score_row=_score_row(40.0),
        )
        result = await svc.re_evaluate(_FINDING_ID, actor_role="developer")
        assert result.after_finding_status == "acknowledged"

    @pytest.mark.asyncio
    async def test_after_status_stays_acknowledged_when_already_acknowledged(self):
        rule = _rule_row()
        svc, _ = _make_service(
            finding_row=_finding(status="acknowledged"),
            rule_rows=[rule],
            eval_results=[_eval_result(passed=False)],
            score_row=_score_row(40.0),
        )
        result = await svc.re_evaluate(_FINDING_ID, actor_role="developer")
        assert result.after_finding_status == "acknowledged"

    @pytest.mark.asyncio
    async def test_updated_guidance_generated_on_fail(self):
        rule = _rule_row()
        ai = _make_ai_engine("You need to write more tests covering edge cases.")
        svc, _ = _make_service(
            finding_row=_finding(status="open"),
            rule_rows=[rule],
            eval_results=[_eval_result(passed=False)],
            score_row=_score_row(40.0),
            ai_engine=ai,
        )
        result = await svc.re_evaluate(_FINDING_ID, actor_role="developer")
        assert result.updated_guidance is not None
        assert len(result.updated_guidance) > 0

    @pytest.mark.asyncio
    async def test_rule_results_shows_not_passed(self):
        rule = _rule_row()
        svc, _ = _make_service(
            finding_row=_finding(status="open"),
            rule_rows=[rule],
            eval_results=[_eval_result(passed=False)],
            score_row=_score_row(40.0),
        )
        result = await svc.re_evaluate(_FINDING_ID, actor_role="developer")
        assert len(result.rule_results) == 1
        assert result.rule_results[0].passed is False


# ---------------------------------------------------------------------------
# Health Score delta calculation
# ---------------------------------------------------------------------------

class TestScoreDelta:
    @pytest.mark.asyncio
    async def test_score_delta_positive_on_improvement(self):
        rule = _rule_row()
        svc, _ = _make_service(
            finding_row=_finding(status="open"),
            rule_rows=[rule],
            eval_results=[_eval_result(passed=True)],
            score_row=_score_row(60.0),
        )
        result = await svc.re_evaluate(_FINDING_ID, actor_role="developer")
        assert result.after_health_score > result.before_health_score

    @pytest.mark.asyncio
    async def test_score_delta_null_when_no_prior_score(self):
        rule = _rule_row()
        svc, _ = _make_service(
            finding_row=_finding(status="open"),
            rule_rows=[rule],
            eval_results=[_eval_result(passed=True)],
            score_row=None,
        )
        result = await svc.re_evaluate(_FINDING_ID, actor_role="developer")
        assert result.before_health_score is None
        assert result.score_delta is None

    @pytest.mark.asyncio
    async def test_after_health_score_range_0_100(self):
        rule = _rule_row()
        svc, _ = _make_service(
            finding_row=_finding(status="open"),
            rule_rows=[rule],
            eval_results=[_eval_result(passed=True)],
            score_row=_score_row(50.0),
        )
        result = await svc.re_evaluate(_FINDING_ID, actor_role="developer")
        assert 0.0 <= result.after_health_score <= 100.0


# ---------------------------------------------------------------------------
# Optimistic locking
# ---------------------------------------------------------------------------

class TestOptimisticLocking:
    @pytest.mark.asyncio
    async def test_conflict_error_on_version_mismatch(self):
        rule = _rule_row()
        svc, mocks = _make_service(
            finding_row=_finding(status="open", version=1),
            rule_rows=[rule],
            eval_results=[_eval_result(passed=True)],
            score_row=_score_row(60.0),
        )
        mocks["finding_repo"].update_with_optimistic_lock = AsyncMock(
            side_effect=ConflictError(
                "Concurrent re-evaluation in progress",
                details={"error_code": "OPTIMISTIC_LOCK_CONFLICT"},
            )
        )
        with pytest.raises(ConflictError) as exc_info:
            await svc.re_evaluate(_FINDING_ID, actor_role="developer")
        assert exc_info.value.details["error_code"] == "OPTIMISTIC_LOCK_CONFLICT"


# ---------------------------------------------------------------------------
# Audit log
# ---------------------------------------------------------------------------

class TestAuditLog:
    @pytest.mark.asyncio
    async def test_audit_log_called_on_success(self):
        rule = _rule_row()
        svc, mocks = _make_service(
            finding_row=_finding(status="open"),
            rule_rows=[rule],
            eval_results=[_eval_result(passed=True)],
            score_row=_score_row(60.0),
        )
        await svc.re_evaluate(_FINDING_ID, actor_role="developer")
        mocks["audit_svc"].log_event.assert_called_once()

    @pytest.mark.asyncio
    async def test_audit_log_has_correct_action(self):
        rule = _rule_row()
        svc, mocks = _make_service(
            finding_row=_finding(status="open"),
            rule_rows=[rule],
            eval_results=[_eval_result(passed=True)],
            score_row=_score_row(60.0),
        )
        await svc.re_evaluate(_FINDING_ID, actor_role="tech_lead")
        call_kwargs = mocks["audit_svc"].log_event.call_args[1]
        assert call_kwargs["action"] == "finding.re_evaluated"
        assert call_kwargs["actor_role"] == "tech_lead"

    @pytest.mark.asyncio
    async def test_audit_log_called_even_if_persistence_fails(self):
        rule = _rule_row()
        svc, mocks = _make_service(
            finding_row=_finding(status="open"),
            rule_rows=[rule],
            eval_results=[_eval_result(passed=True)],
            score_row=_score_row(60.0),
        )
        mocks["assessment_repo"].create = AsyncMock(side_effect=Exception("DB down"))
        await svc.re_evaluate(_FINDING_ID, actor_role="developer")
        mocks["audit_svc"].log_event.assert_called_once()


# ---------------------------------------------------------------------------
# AI guidance fallback
# ---------------------------------------------------------------------------

class TestAIGuidanceFallback:
    @pytest.mark.asyncio
    async def test_circuit_open_returns_none_guidance(self):
        rule = _rule_row()
        ai = MagicMock()
        ai.generate_completion = AsyncMock(
            side_effect=CircuitOpenError(state="open")
        )
        svc, _ = _make_service(
            finding_row=_finding(status="open"),
            rule_rows=[rule],
            eval_results=[_eval_result(passed=False)],
            score_row=_score_row(40.0),
            ai_engine=ai,
        )
        result = await svc.re_evaluate(_FINDING_ID, actor_role="developer")
        # Response still returned, guidance is None when AI unavailable
        assert result is not None
        assert result.updated_guidance is None

    @pytest.mark.asyncio
    async def test_connection_error_returns_none_guidance(self):
        rule = _rule_row()
        ai = MagicMock()
        ai.generate_completion = AsyncMock(
            side_effect=ConnectionError("refused")
        )
        svc, _ = _make_service(
            finding_row=_finding(status="open"),
            rule_rows=[rule],
            eval_results=[_eval_result(passed=False)],
            score_row=_score_row(40.0),
            ai_engine=ai,
        )
        result = await svc.re_evaluate(_FINDING_ID, actor_role="developer")
        assert result is not None
        assert result.updated_guidance is None
