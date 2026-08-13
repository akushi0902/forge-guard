"""Unit tests for DemoEvaluationService (WO-056).

All external dependencies (PolicyRepository, ServiceRepository, AIEngineService,
RuleEvaluationEngine, etc.) are mocked so no database or LLM is required.

Coverage:
    - Correct orchestration sequence (collect → evaluate → score → explain → persist → audit)
    - Health Score calculation for known inputs (deterministic weighted-aggregate)
    - Template fallback activation when AIEngine raises CircuitOpenError
    - Template fallback activation when AIEngine raises generic Exception
    - 404 when Payment Service not found in DB
    - 422 when no policy rules seeded
    - Audit log is always called (even on persistence failure)
    - Dimension scoring with 0-weight rules
    - All-pass scenario produces Health Score of 100

Run:
    pytest tests/unit/services/test_demo_evaluation.py -v
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from forgeguard.services.ai_engine.errors import CircuitOpenError
from forgeguard.services.domain.evaluation import EvaluationStatus, RuleEvaluationResult
from forgeguard.services.domain.severity import SeverityLevel

# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------

_PAYMENT_SERVICE_ID = uuid.UUID("d0000000-0000-0000-0000-000000000001")


def _service_row(**kwargs) -> dict[str, Any]:
    return {
        "id": _PAYMENT_SERVICE_ID,
        "name": "Payment Service",
        "is_demo": True,
        **kwargs,
    }


def _rule_row(
    name: str,
    dimension: str,
    data_key: str,
    severity: str = "high",
    weight: float = 10.0,
) -> dict[str, Any]:
    return {
        "id": uuid.uuid4(),
        "name": name,
        "rule_type": "threshold_gte",
        "threshold_config": {"data_key": data_key, "numeric_value": "80"},
        "severity": severity,
        "weight": Decimal(str(weight)),
        "is_active": True,
        "dimension": dimension,
    }


def _eval_result(
    rule_row: dict[str, Any],
    passed: bool,
    actual: float = 60.0,
) -> RuleEvaluationResult:
    return RuleEvaluationResult(
        rule_id=rule_row["id"],
        rule_name=rule_row["name"],
        dimension=rule_row["dimension"],
        severity=SeverityLevel(rule_row["severity"]),
        status=EvaluationStatus.PASS if passed else EvaluationStatus.FAIL,
        actual_value=actual,
        expected_value=80.0,
        evidence={"data_key": rule_row["threshold_config"]["data_key"]},
        evaluated_at=datetime.now(tz=timezone.utc),
        weight=rule_row["weight"],
    )


def _make_ai_engine(content: str = "AI explanation", confidence: float = 0.9) -> MagicMock:
    resp = MagicMock()
    resp.content = content
    resp.confidence_score = confidence
    ai = MagicMock()
    ai.generate_completion = AsyncMock(return_value=resp)
    return ai


def _make_service(
    *,
    service_row: dict | None = None,
    rule_rows: list[dict] | None = None,
    eval_results: list[RuleEvaluationResult] | None = None,
    ai_engine: Any = None,
):
    from forgeguard.services.demo_evaluation import DemoEvaluationService

    policy_repo = MagicMock()
    policy_repo.list_active_rules = AsyncMock(return_value=rule_rows or [])

    service_repo = MagicMock()
    service_repo.get_by_id = AsyncMock(return_value=service_row)

    assessment_repo = MagicMock()
    assessment_repo.create = AsyncMock(return_value={"id": uuid.uuid4()})

    score_repo = MagicMock()
    score_repo.create = AsyncMock(return_value={"id": uuid.uuid4()})

    finding_repo = MagicMock()
    finding_repo.create = AsyncMock(return_value={"id": uuid.uuid4()})

    remediation_repo = MagicMock()
    remediation_repo.create = AsyncMock(return_value={"id": uuid.uuid4()})

    audit_repo = MagicMock()
    audit_repo.insert = AsyncMock(return_value={"id": uuid.uuid4()})

    data_collector = MagicMock()
    data_collector.collect = AsyncMock(return_value={"unit_test_coverage": 62.5})

    evaluation_engine = MagicMock()
    evaluation_engine.evaluate_rules = AsyncMock(return_value=eval_results or [])

    return DemoEvaluationService(
        policy_repo=policy_repo,
        service_repo=service_repo,
        assessment_repo=assessment_repo,
        score_repo=score_repo,
        finding_repo=finding_repo,
        remediation_repo=remediation_repo,
        audit_repo=audit_repo,
        ai_engine=ai_engine or _make_ai_engine(),
        data_collector=data_collector,
        evaluation_engine=evaluation_engine,
    ), {
        "policy_repo": policy_repo,
        "service_repo": service_repo,
        "assessment_repo": assessment_repo,
        "score_repo": score_repo,
        "finding_repo": finding_repo,
        "remediation_repo": remediation_repo,
        "audit_repo": audit_repo,
        "data_collector": data_collector,
        "evaluation_engine": evaluation_engine,
    }


# ---------------------------------------------------------------------------
# Orchestration sequence tests
# ---------------------------------------------------------------------------

class TestOrchestrationSequence:
    @pytest.mark.asyncio
    async def test_calls_service_repo(self):
        rule = _rule_row("coverage", "test_coverage", "unit_test_coverage")
        eval_res = [_eval_result(rule, passed=True)]
        svc, mocks = _make_service(
            service_row=_service_row(),
            rule_rows=[rule],
            eval_results=eval_res,
        )
        await svc.evaluate_payment_service(actor_role="developer")
        mocks["service_repo"].get_by_id.assert_called_once_with(_PAYMENT_SERVICE_ID)

    @pytest.mark.asyncio
    async def test_calls_data_collector(self):
        rule = _rule_row("coverage", "test_coverage", "unit_test_coverage")
        svc, mocks = _make_service(
            service_row=_service_row(),
            rule_rows=[rule],
            eval_results=[_eval_result(rule, passed=True)],
        )
        await svc.evaluate_payment_service(actor_role="developer")
        mocks["data_collector"].collect.assert_called_once_with(_PAYMENT_SERVICE_ID)

    @pytest.mark.asyncio
    async def test_calls_policy_repo(self):
        svc, mocks = _make_service(
            service_row=_service_row(),
            rule_rows=[_rule_row("x", "security", "dep")],
            eval_results=[_eval_result(_rule_row("x", "security", "dep"), passed=True)],
        )
        await svc.evaluate_payment_service(actor_role="developer")
        mocks["policy_repo"].list_active_rules.assert_called_once()

    @pytest.mark.asyncio
    async def test_calls_evaluation_engine(self):
        rule = _rule_row("coverage", "test_coverage", "unit_test_coverage")
        svc, mocks = _make_service(
            service_row=_service_row(),
            rule_rows=[rule],
            eval_results=[_eval_result(rule, passed=False)],
        )
        await svc.evaluate_payment_service(actor_role="developer")
        mocks["evaluation_engine"].evaluate_rules.assert_called_once()

    @pytest.mark.asyncio
    async def test_calls_assessment_repo_on_persist(self):
        rule = _rule_row("coverage", "test_coverage", "unit_test_coverage")
        svc, mocks = _make_service(
            service_row=_service_row(),
            rule_rows=[rule],
            eval_results=[_eval_result(rule, passed=True)],
        )
        await svc.evaluate_payment_service(actor_role="developer")
        mocks["assessment_repo"].create.assert_called_once()

    @pytest.mark.asyncio
    async def test_calls_audit_repo(self):
        rule = _rule_row("coverage", "test_coverage", "unit_test_coverage")
        svc, mocks = _make_service(
            service_row=_service_row(),
            rule_rows=[rule],
            eval_results=[_eval_result(rule, passed=True)],
        )
        await svc.evaluate_payment_service(actor_role="developer")
        mocks["audit_repo"].insert.assert_called_once()

    @pytest.mark.asyncio
    async def test_audit_log_actor_role(self):
        rule = _rule_row("coverage", "test_coverage", "unit_test_coverage")
        svc, mocks = _make_service(
            service_row=_service_row(),
            rule_rows=[rule],
            eval_results=[_eval_result(rule, passed=True)],
        )
        await svc.evaluate_payment_service(actor_role="security_reviewer")
        call_args = mocks["audit_repo"].insert.call_args[0][0]
        assert call_args["actor_role"] == "security_reviewer"
        assert call_args["action"] == "demo_evaluation_triggered"

    @pytest.mark.asyncio
    async def test_finding_repo_called_for_each_violation(self):
        rules = [
            _rule_row("cov", "test_coverage", "unit_test_coverage"),
            _rule_row("sec", "security", "critical_cve_count"),
        ]
        eval_res = [_eval_result(r, passed=False) for r in rules]
        svc, mocks = _make_service(
            service_row=_service_row(),
            rule_rows=rules,
            eval_results=eval_res,
        )
        await svc.evaluate_payment_service(actor_role="developer")
        assert mocks["finding_repo"].create.call_count == 2

    @pytest.mark.asyncio
    async def test_remediation_repo_called_for_each_finding(self):
        rules = [
            _rule_row("cov", "test_coverage", "unit_test_coverage"),
            _rule_row("sec", "security", "critical_cve_count"),
        ]
        eval_res = [_eval_result(r, passed=False) for r in rules]
        svc, mocks = _make_service(
            service_row=_service_row(),
            rule_rows=rules,
            eval_results=eval_res,
        )
        await svc.evaluate_payment_service(actor_role="developer")
        assert mocks["remediation_repo"].create.call_count == 2


# ---------------------------------------------------------------------------
# Health Score calculation tests
# ---------------------------------------------------------------------------

class TestHealthScoreCalculation:
    @pytest.mark.asyncio
    async def test_all_pass_produces_100(self):
        rules = [_rule_row("r1", "code_quality", "cq", weight=10)]
        eval_res = [_eval_result(rules[0], passed=True)]
        svc, _ = _make_service(
            service_row=_service_row(),
            rule_rows=rules,
            eval_results=eval_res,
        )
        result = await svc.evaluate_payment_service(actor_role="developer")
        assert result.health_score.overall == 100.0

    @pytest.mark.asyncio
    async def test_all_fail_produces_0(self):
        rules = [_rule_row("r1", "code_quality", "cq", weight=10)]
        eval_res = [_eval_result(rules[0], passed=False)]
        svc, _ = _make_service(
            service_row=_service_row(),
            rule_rows=rules,
            eval_results=eval_res,
        )
        result = await svc.evaluate_payment_service(actor_role="developer")
        assert result.health_score.overall == 0.0

    @pytest.mark.asyncio
    async def test_half_pass_half_fail_same_weight(self):
        rules = [
            _rule_row("pass_rule", "code_quality", "cq1", weight=10),
            _rule_row("fail_rule", "code_quality", "cq2", weight=10),
        ]
        eval_res = [
            _eval_result(rules[0], passed=True),
            _eval_result(rules[1], passed=False),
        ]
        svc, _ = _make_service(
            service_row=_service_row(),
            rule_rows=rules,
            eval_results=eval_res,
        )
        result = await svc.evaluate_payment_service(actor_role="developer")
        # code_quality = 10/20*100 = 50, only one dimension with data
        assert result.health_score.overall == pytest.approx(50.0, abs=0.5)

    @pytest.mark.asyncio
    async def test_multi_dimension_weighted_average(self):
        rules = [
            _rule_row("cq_pass", "code_quality", "cq", weight=20),
            _rule_row("sec_fail", "security", "sec", weight=20),
        ]
        eval_res = [
            _eval_result(rules[0], passed=True),
            _eval_result(rules[1], passed=False),
        ]
        svc, _ = _make_service(
            service_row=_service_row(),
            rule_rows=rules,
            eval_results=eval_res,
        )
        result = await svc.evaluate_payment_service(actor_role="developer")
        # code_quality=100, security=0, equal weights → 50
        assert result.health_score.overall == pytest.approx(50.0, abs=0.5)

    @pytest.mark.asyncio
    async def test_dimension_scores_present_in_response(self):
        rules = [_rule_row("cq", "code_quality", "cq", weight=10)]
        eval_res = [_eval_result(rules[0], passed=True)]
        svc, _ = _make_service(
            service_row=_service_row(),
            rule_rows=rules,
            eval_results=eval_res,
        )
        result = await svc.evaluate_payment_service(actor_role="developer")
        assert result.health_score.dimensions.code_quality == 100.0

    @pytest.mark.asyncio
    async def test_zero_weight_rule_does_not_affect_score(self):
        rules = [
            _rule_row("zero_weight_fail", "code_quality", "cq_zero", weight=0.0),
        ]
        eval_res = [_eval_result(rules[0], passed=False)]
        svc, _ = _make_service(
            service_row=_service_row(),
            rule_rows=rules,
            eval_results=eval_res,
        )
        result = await svc.evaluate_payment_service(actor_role="developer")
        # 0 weight → 0/0 → no dimension data → overall 0 (no active dimensions)
        assert result.health_score.overall == 0.0


# ---------------------------------------------------------------------------
# Template fallback tests
# ---------------------------------------------------------------------------

class TestTemplateFallback:
    @pytest.mark.asyncio
    async def test_circuit_open_uses_template_explanation(self):
        ai = MagicMock()
        ai.generate_completion = AsyncMock(
            side_effect=CircuitOpenError(state="open")
        )
        rule = _rule_row("unit_test_coverage", "test_coverage", "unit_test_coverage")
        eval_res = [_eval_result(rule, passed=False)]
        svc, _ = _make_service(
            service_row=_service_row(),
            rule_rows=[rule],
            eval_results=eval_res,
            ai_engine=ai,
        )
        result = await svc.evaluate_payment_service(actor_role="developer")
        assert len(result.findings) == 1
        # Should have template text, not an error
        assert result.findings[0].ai_explanation is not None
        assert len(result.findings[0].ai_explanation) > 10

    @pytest.mark.asyncio
    async def test_circuit_open_uses_template_remediation(self):
        ai = MagicMock()
        ai.generate_completion = AsyncMock(
            side_effect=CircuitOpenError(state="open")
        )
        rule = _rule_row("unit_test_coverage", "test_coverage", "unit_test_coverage")
        eval_res = [_eval_result(rule, passed=False)]
        svc, _ = _make_service(
            service_row=_service_row(),
            rule_rows=[rule],
            eval_results=eval_res,
            ai_engine=ai,
        )
        result = await svc.evaluate_payment_service(actor_role="developer")
        assert result.findings[0].remediation.source == "template"

    @pytest.mark.asyncio
    async def test_generic_exception_falls_back_to_template(self):
        ai = MagicMock()
        ai.generate_completion = AsyncMock(
            side_effect=ConnectionError("LLM unavailable")
        )
        rule = _rule_row("dep_vuln", "security", "dependency_vulnerabilities")
        eval_res = [_eval_result(rule, passed=False)]
        svc, _ = _make_service(
            service_row=_service_row(),
            rule_rows=[rule],
            eval_results=eval_res,
            ai_engine=ai,
        )
        result = await svc.evaluate_payment_service(actor_role="developer")
        assert result.findings[0].remediation.source == "template"
        assert result.findings[0].ai_explanation is not None

    @pytest.mark.asyncio
    async def test_ai_success_uses_ai_source(self):
        ai = _make_ai_engine("AI-generated explanation text", confidence=0.9)
        rule = _rule_row("cov", "test_coverage", "unit_test_coverage")
        eval_res = [_eval_result(rule, passed=False)]
        svc, _ = _make_service(
            service_row=_service_row(),
            rule_rows=[rule],
            eval_results=eval_res,
            ai_engine=ai,
        )
        result = await svc.evaluate_payment_service(actor_role="developer")
        assert result.findings[0].ai_explanation == "AI-generated explanation text"
        assert result.findings[0].remediation.source == "ai"


# ---------------------------------------------------------------------------
# Error handling tests
# ---------------------------------------------------------------------------

class TestErrorHandling:
    @pytest.mark.asyncio
    async def test_404_when_service_not_found(self):
        from fastapi import HTTPException
        svc, _ = _make_service(service_row=None, rule_rows=[])
        with pytest.raises(HTTPException) as exc_info:
            await svc.evaluate_payment_service(actor_role="developer")
        assert exc_info.value.status_code == 404
        assert exc_info.value.detail["error_code"] == "DEMO_SERVICE_NOT_FOUND"

    @pytest.mark.asyncio
    async def test_422_when_no_policy_rules(self):
        from fastapi import HTTPException
        svc, _ = _make_service(service_row=_service_row(), rule_rows=[])
        with pytest.raises(HTTPException) as exc_info:
            await svc.evaluate_payment_service(actor_role="developer")
        assert exc_info.value.status_code == 422
        assert exc_info.value.detail["error_code"] == "NO_POLICY_RULES"

    @pytest.mark.asyncio
    async def test_audit_log_called_even_if_persistence_fails(self):
        rule = _rule_row("cov", "test_coverage", "unit_test_coverage")
        eval_res = [_eval_result(rule, passed=True)]
        svc, mocks = _make_service(
            service_row=_service_row(),
            rule_rows=[rule],
            eval_results=eval_res,
        )
        mocks["assessment_repo"].create = AsyncMock(
            side_effect=Exception("DB connection lost")
        )
        result = await svc.evaluate_payment_service(actor_role="developer")
        # Audit log should still be called
        mocks["audit_repo"].insert.assert_called_once()
        # Response still returned
        assert result is not None


# ---------------------------------------------------------------------------
# Response structure tests
# ---------------------------------------------------------------------------

class TestResponseStructure:
    @pytest.mark.asyncio
    async def test_response_has_assessment_id(self):
        rule = _rule_row("cov", "test_coverage", "unit_test_coverage")
        svc, _ = _make_service(
            service_row=_service_row(),
            rule_rows=[rule],
            eval_results=[_eval_result(rule, passed=True)],
        )
        result = await svc.evaluate_payment_service(actor_role="developer")
        assert isinstance(result.assessment_id, uuid.UUID)

    @pytest.mark.asyncio
    async def test_response_is_simulated_true(self):
        rule = _rule_row("cov", "test_coverage", "unit_test_coverage")
        svc, _ = _make_service(
            service_row=_service_row(),
            rule_rows=[rule],
            eval_results=[_eval_result(rule, passed=True)],
        )
        result = await svc.evaluate_payment_service(actor_role="developer")
        assert result.is_simulated is True

    @pytest.mark.asyncio
    async def test_summary_finding_count_matches_findings(self):
        rules = [
            _rule_row("r1", "test_coverage", "unit_test_coverage"),
            _rule_row("r2", "security", "critical_cve_count"),
        ]
        eval_res = [_eval_result(r, passed=False) for r in rules]
        svc, _ = _make_service(
            service_row=_service_row(),
            rule_rows=rules,
            eval_results=eval_res,
        )
        result = await svc.evaluate_payment_service(actor_role="developer")
        assert result.summary.total_findings == len(result.findings)

    @pytest.mark.asyncio
    async def test_summary_by_severity_matches_findings(self):
        rules = [
            _rule_row("critical_rule", "security", "critical_cve", severity="critical", weight=10),
            _rule_row("high_rule", "test_coverage", "unit_cov", severity="high", weight=10),
        ]
        eval_res = [_eval_result(r, passed=False) for r in rules]
        svc, _ = _make_service(
            service_row=_service_row(),
            rule_rows=rules,
            eval_results=eval_res,
        )
        result = await svc.evaluate_payment_service(actor_role="developer")
        assert result.summary.by_severity.critical == 1
        assert result.summary.by_severity.high == 1

    @pytest.mark.asyncio
    async def test_evaluation_duration_ms_is_positive(self):
        rule = _rule_row("cov", "test_coverage", "unit_test_coverage")
        svc, _ = _make_service(
            service_row=_service_row(),
            rule_rows=[rule],
            eval_results=[_eval_result(rule, passed=True)],
        )
        result = await svc.evaluate_payment_service(actor_role="developer")
        assert result.summary.evaluation_duration_ms >= 0

    @pytest.mark.asyncio
    async def test_no_findings_when_all_pass(self):
        rules = [
            _rule_row("r1", "code_quality", "cq"),
            _rule_row("r2", "security", "sec"),
        ]
        eval_res = [_eval_result(r, passed=True) for r in rules]
        svc, _ = _make_service(
            service_row=_service_row(),
            rule_rows=rules,
            eval_results=eval_res,
        )
        result = await svc.evaluate_payment_service(actor_role="developer")
        assert len(result.findings) == 0
        assert result.summary.total_findings == 0

    @pytest.mark.asyncio
    async def test_finding_has_all_required_fields(self):
        rule = _rule_row("cov", "test_coverage", "unit_test_coverage", severity="high")
        svc, _ = _make_service(
            service_row=_service_row(),
            rule_rows=[rule],
            eval_results=[_eval_result(rule, passed=False)],
        )
        result = await svc.evaluate_payment_service(actor_role="developer")
        f = result.findings[0]
        assert f.id is not None
        assert f.severity == "high"
        assert f.dimension == "test_coverage"
        assert f.title is not None
        assert f.description is not None
        assert f.ai_explanation is not None
        assert f.remediation is not None
        assert 0.0 <= f.confidence_score <= 1.0

    @pytest.mark.asyncio
    async def test_remediation_has_confidence_score(self):
        rule = _rule_row("cov", "test_coverage", "unit_test_coverage")
        svc, _ = _make_service(
            service_row=_service_row(),
            rule_rows=[rule],
            eval_results=[_eval_result(rule, passed=False)],
        )
        result = await svc.evaluate_payment_service(actor_role="developer")
        rem = result.findings[0].remediation
        assert 0.0 <= rem.confidence_score <= 1.0
        assert rem.source in ("ai", "template")
