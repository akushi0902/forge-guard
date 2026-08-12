"""Integration tests for POST /api/v1/demo/evaluate endpoint (WO-056).

Tests mock all database and LLM dependencies — no running PostgreSQL or
LLM provider is required. These tests validate the full request/response
pipeline from the route handler through DemoEvaluationService to the
assembled response.

Run:
    pytest tests/integration/api/test_demo_evaluate.py -v
"""

from __future__ import annotations

import json
import time
import uuid
from decimal import Decimal
from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from forgeguard.services.ai_engine.errors import CircuitOpenError
from forgeguard.services.domain.evaluation import EvaluationStatus, RuleEvaluationResult
from forgeguard.services.domain.severity import SeverityLevel

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
    actual: float = 62.5,
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


def _make_ai_engine(content: str = "AI explanation.", confidence: float = 0.9):
    resp = MagicMock()
    resp.content = content
    resp.confidence_score = confidence
    ai = MagicMock()
    ai.generate_completion = AsyncMock(return_value=resp)
    return ai


def _pool_mock():
    return MagicMock()


async def _call_endpoint(
    *,
    service_row: dict | None,
    rule_rows: list[dict],
    eval_results: list[RuleEvaluationResult],
    ai_engine: Any = None,
    role: str = "developer",
) -> Any:
    from forgeguard.api.routes.demo import evaluate_demo_service

    pool = _pool_mock()
    request = MagicMock()
    request.headers = {"X-User-Role": role}

    ai = ai_engine or _make_ai_engine()

    with (
        patch("forgeguard.api.routes.demo.PolicyRepository") as mock_policy_repo,
        patch("forgeguard.api.routes.demo.ServiceRepository") as mock_service_repo,
        patch("forgeguard.api.routes.demo.AssessmentRepository") as mock_assessment_repo,
        patch("forgeguard.api.routes.demo.AssessmentScoreRepository") as mock_score_repo,
        patch("forgeguard.api.routes.demo.FindingRepository") as mock_finding_repo,
        patch("forgeguard.api.routes.demo.RemediationRecommendationRepository") as mock_rem_repo,
        patch("forgeguard.api.routes.demo.AuditLogRepository") as mock_audit_repo,
        patch("forgeguard.api.routes.demo.get_ai_engine") as mock_get_ai,
        patch("forgeguard.api.routes.demo.RuleEvaluationEngine") as mock_engine_cls,
        patch("forgeguard.api.routes.demo.MockDataCollector") as mock_collector_cls,
    ):
        mock_policy_repo.return_value.list_active_rules = AsyncMock(return_value=rule_rows)
        mock_service_repo.return_value.get_by_id = AsyncMock(return_value=service_row)
        mock_assessment_repo.return_value.create = AsyncMock(return_value={"id": uuid.uuid4()})
        mock_score_repo.return_value.create = AsyncMock(return_value={"id": uuid.uuid4()})
        mock_finding_repo.return_value.create = AsyncMock(return_value={"id": uuid.uuid4()})
        mock_rem_repo.return_value.create = AsyncMock(return_value={"id": uuid.uuid4()})
        mock_audit_repo.return_value.insert = AsyncMock(return_value={"id": uuid.uuid4()})
        mock_get_ai.return_value = ai
        mock_engine_cls.return_value.evaluate_rules = AsyncMock(return_value=eval_results)
        mock_collector_cls.return_value.collect = AsyncMock(
            return_value={"unit_test_coverage": 62.5}
        )

        return await evaluate_demo_service(request=request, role=role, pool=pool)


# ---------------------------------------------------------------------------
# Basic response structure
# ---------------------------------------------------------------------------

class TestResponseStructure:
    @pytest.mark.asyncio
    async def test_response_has_assessment_id(self):
        rule = _rule_row("cov", "test_coverage", "unit_test_coverage")
        result = await _call_endpoint(
            service_row=_service_row(),
            rule_rows=[rule],
            eval_results=[_eval_result(rule, passed=True)],
        )
        assert "assessment_id" in result

    @pytest.mark.asyncio
    async def test_response_has_service_id(self):
        rule = _rule_row("cov", "test_coverage", "unit_test_coverage")
        result = await _call_endpoint(
            service_row=_service_row(),
            rule_rows=[rule],
            eval_results=[_eval_result(rule, passed=True)],
        )
        assert "service_id" in result

    @pytest.mark.asyncio
    async def test_response_is_simulated_true(self):
        rule = _rule_row("cov", "test_coverage", "unit_test_coverage")
        result = await _call_endpoint(
            service_row=_service_row(),
            rule_rows=[rule],
            eval_results=[_eval_result(rule, passed=True)],
        )
        assert result["is_simulated"] is True

    @pytest.mark.asyncio
    async def test_response_has_health_score(self):
        rule = _rule_row("cov", "test_coverage", "unit_test_coverage")
        result = await _call_endpoint(
            service_row=_service_row(),
            rule_rows=[rule],
            eval_results=[_eval_result(rule, passed=True)],
        )
        assert "health_score" in result
        assert 0.0 <= result["health_score"]["overall"] <= 100.0

    @pytest.mark.asyncio
    async def test_response_has_all_5_dimension_keys(self):
        rule = _rule_row("cov", "test_coverage", "unit_test_coverage")
        result = await _call_endpoint(
            service_row=_service_row(),
            rule_rows=[rule],
            eval_results=[_eval_result(rule, passed=True)],
        )
        dims = result["health_score"]["dimensions"]
        for dim in ("code_quality", "test_coverage", "security", "documentation", "operations_readiness"):
            assert dim in dims

    @pytest.mark.asyncio
    async def test_response_has_findings_list(self):
        rule = _rule_row("cov", "test_coverage", "unit_test_coverage")
        result = await _call_endpoint(
            service_row=_service_row(),
            rule_rows=[rule],
            eval_results=[_eval_result(rule, passed=True)],
        )
        assert "findings" in result
        assert isinstance(result["findings"], list)

    @pytest.mark.asyncio
    async def test_response_has_summary(self):
        rule = _rule_row("cov", "test_coverage", "unit_test_coverage")
        result = await _call_endpoint(
            service_row=_service_row(),
            rule_rows=[rule],
            eval_results=[_eval_result(rule, passed=True)],
        )
        assert "summary" in result
        assert "total_findings" in result["summary"]
        assert "by_severity" in result["summary"]
        assert "evaluated_at" in result["summary"]
        assert "evaluation_duration_ms" in result["summary"]

    @pytest.mark.asyncio
    async def test_summary_severity_breakdown_has_all_levels(self):
        rule = _rule_row("cov", "test_coverage", "unit_test_coverage")
        result = await _call_endpoint(
            service_row=_service_row(),
            rule_rows=[rule],
            eval_results=[_eval_result(rule, passed=True)],
        )
        sev = result["summary"]["by_severity"]
        for level in ("critical", "high", "medium", "low"):
            assert level in sev


# ---------------------------------------------------------------------------
# Multiple violations across dimensions
# ---------------------------------------------------------------------------

class TestMultipleViolations:
    _RULES = [
        _rule_row("unit_cov", "test_coverage", "unit_test_coverage", "high", 10),
        _rule_row("int_cov", "test_coverage", "integration_test_coverage", "medium", 10),
        _rule_row("critical_cve", "security", "critical_cve_count", "critical", 20),
        _rule_row("dep_vuln", "security", "dependency_vulnerabilities", "high", 10),
        _rule_row("readme", "documentation", "has_readme", "high", 10),
        _rule_row("slo", "operations_readiness", "slo_defined", "high", 10),
    ]

    @pytest.mark.asyncio
    async def test_at_least_5_findings_returned(self):
        eval_res = [_eval_result(r, passed=False) for r in self._RULES]
        result = await _call_endpoint(
            service_row=_service_row(),
            rule_rows=self._RULES,
            eval_results=eval_res,
        )
        assert result["summary"]["total_findings"] >= 5

    @pytest.mark.asyncio
    async def test_findings_span_multiple_dimensions(self):
        eval_res = [_eval_result(r, passed=False) for r in self._RULES]
        result = await _call_endpoint(
            service_row=_service_row(),
            rule_rows=self._RULES,
            eval_results=eval_res,
        )
        dims = {f["dimension"] for f in result["findings"]}
        assert len(dims) >= 3

    @pytest.mark.asyncio
    async def test_health_score_below_50_for_many_violations(self):
        eval_res = [_eval_result(r, passed=False) for r in self._RULES]
        result = await _call_endpoint(
            service_row=_service_row(),
            rule_rows=self._RULES,
            eval_results=eval_res,
        )
        assert result["health_score"]["overall"] < 50.0

    @pytest.mark.asyncio
    async def test_each_finding_has_remediation(self):
        eval_res = [_eval_result(r, passed=False) for r in self._RULES]
        result = await _call_endpoint(
            service_row=_service_row(),
            rule_rows=self._RULES,
            eval_results=eval_res,
        )
        for finding in result["findings"]:
            assert "remediation" in finding
            assert "recommendation_text" in finding["remediation"]
            assert "implementation_guide" in finding["remediation"]
            assert "confidence_score" in finding["remediation"]
            assert "source" in finding["remediation"]

    @pytest.mark.asyncio
    async def test_each_finding_has_ai_explanation(self):
        eval_res = [_eval_result(r, passed=False) for r in self._RULES]
        result = await _call_endpoint(
            service_row=_service_row(),
            rule_rows=self._RULES,
            eval_results=eval_res,
        )
        for finding in result["findings"]:
            assert finding["ai_explanation"] is not None
            assert len(finding["ai_explanation"]) > 0

    @pytest.mark.asyncio
    async def test_critical_finding_severity_in_breakdown(self):
        eval_res = [_eval_result(r, passed=False) for r in self._RULES]
        result = await _call_endpoint(
            service_row=_service_row(),
            rule_rows=self._RULES,
            eval_results=eval_res,
        )
        assert result["summary"]["by_severity"]["critical"] >= 1


# ---------------------------------------------------------------------------
# Error cases
# ---------------------------------------------------------------------------

class TestErrorCases:
    @pytest.mark.asyncio
    async def test_404_when_service_not_found(self):
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc_info:
            await _call_endpoint(
                service_row=None,
                rule_rows=[],
                eval_results=[],
            )
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_404_detail_has_error_code(self):
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc_info:
            await _call_endpoint(
                service_row=None,
                rule_rows=[],
                eval_results=[],
            )
        assert exc_info.value.detail["error_code"] == "DEMO_SERVICE_NOT_FOUND"

    @pytest.mark.asyncio
    async def test_422_when_no_rules_configured(self):
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc_info:
            await _call_endpoint(
                service_row=_service_row(),
                rule_rows=[],
                eval_results=[],
            )
        assert exc_info.value.status_code == 422

    @pytest.mark.asyncio
    async def test_422_detail_has_error_code(self):
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc_info:
            await _call_endpoint(
                service_row=_service_row(),
                rule_rows=[],
                eval_results=[],
            )
        assert exc_info.value.detail["error_code"] == "NO_POLICY_RULES"


# ---------------------------------------------------------------------------
# LLM unavailable — template fallback
# ---------------------------------------------------------------------------

class TestLLMFallback:
    @pytest.mark.asyncio
    async def test_circuit_open_does_not_cause_500(self):
        ai = MagicMock()
        ai.generate_completion = AsyncMock(
            side_effect=CircuitOpenError(state="open")
        )
        rule = _rule_row("cov", "test_coverage", "unit_test_coverage")
        result = await _call_endpoint(
            service_row=_service_row(),
            rule_rows=[rule],
            eval_results=[_eval_result(rule, passed=False)],
            ai_engine=ai,
        )
        assert result is not None
        assert len(result["findings"]) == 1

    @pytest.mark.asyncio
    async def test_circuit_open_produces_template_source(self):
        ai = MagicMock()
        ai.generate_completion = AsyncMock(
            side_effect=CircuitOpenError(state="open")
        )
        rule = _rule_row("cov", "test_coverage", "unit_test_coverage")
        result = await _call_endpoint(
            service_row=_service_row(),
            rule_rows=[rule],
            eval_results=[_eval_result(rule, passed=False)],
            ai_engine=ai,
        )
        assert result["findings"][0]["remediation"]["source"] == "template"

    @pytest.mark.asyncio
    async def test_connection_error_falls_back_to_template(self):
        ai = MagicMock()
        ai.generate_completion = AsyncMock(
            side_effect=ConnectionError("refused")
        )
        rule = _rule_row("dep_vuln", "security", "dependency_vulnerabilities")
        result = await _call_endpoint(
            service_row=_service_row(),
            rule_rows=[rule],
            eval_results=[_eval_result(rule, passed=False)],
            ai_engine=ai,
        )
        assert result["findings"][0]["ai_explanation"] is not None
        assert len(result["findings"][0]["ai_explanation"]) > 0


# ---------------------------------------------------------------------------
# Performance
# ---------------------------------------------------------------------------

class TestPerformance:
    @pytest.mark.asyncio
    async def test_endpoint_completes_within_60s_for_20_rules(self):
        rules = [
            _rule_row(f"rule_{i}", "code_quality", f"metric_{i}", "medium", 10)
            for i in range(20)
        ]
        eval_res = [_eval_result(r, passed=(i % 3 != 0)) for i, r in enumerate(rules)]

        start = time.perf_counter()
        result = await _call_endpoint(
            service_row=_service_row(),
            rule_rows=rules,
            eval_results=eval_res,
        )
        elapsed = time.perf_counter() - start

        assert elapsed < 60.0, f"Endpoint took {elapsed:.1f}s — must be under 60s"
        assert result is not None
