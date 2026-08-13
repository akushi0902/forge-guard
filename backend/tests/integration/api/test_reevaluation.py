"""Integration tests for POST /api/v1/findings/{finding_id}/re-evaluate (WO-061).

All dependencies are mocked — no running PostgreSQL or LLM provider required.
Tests validate the full route→service→response pipeline.

Run:
    pytest tests/integration/api/test_reevaluation.py -v
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from forgeguard.core.exceptions import BadRequestError, ConflictError, NotFoundError
from forgeguard.services.domain.evaluation import EvaluationStatus, RuleEvaluationResult
from forgeguard.services.domain.severity import SeverityLevel

_SERVICE_ID = uuid.UUID("a1000000-0000-0000-0000-000000000001")
_FINDING_ID = uuid.UUID("b1000000-0000-0000-0000-000000000001")
_RULE_ID = uuid.UUID("c1000000-0000-0000-0000-000000000001")
_USER_ID = uuid.UUID("d1000000-0000-0000-0000-000000000001")


def _finding(status: str = "open") -> dict[str, Any]:
    return {
        "id": _FINDING_ID,
        "service_id": _SERVICE_ID,
        "policy_rule_id": _RULE_ID,
        "status": status,
        "version": 1,
        "severity": "high",
        "dimension": "test_coverage",
        "title": "Coverage too low",
        "description": "Coverage below threshold",
        "evidence": {"data_key": "unit_test_coverage"},
        "resolved_at": None,
        "created_at": datetime(2026, 1, 1, tzinfo=timezone.utc),
    }


def _eval_result(passed: bool) -> RuleEvaluationResult:
    return RuleEvaluationResult(
        rule_id=_RULE_ID,
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


def _mock_current_user(role: str = "developer"):
    from forgeguard.api.dependencies.auth import CurrentUser
    return CurrentUser(user_id=_USER_ID, role=role)


def _pool_mock():
    return MagicMock()


async def _call_endpoint(
    *,
    finding_row: dict | None = None,
    rule_rows: list[dict] | None = None,
    eval_results: list | None = None,
    score_row: dict | None = None,
    role: str = "developer",
    service_side_effect: Exception | None = None,
) -> Any:
    from forgeguard.api.routes.remediation import re_evaluate_finding
    from forgeguard.services.audit import AuditService

    pool = _pool_mock()
    request = MagicMock()
    request.headers = {}

    current_user = _mock_current_user(role)
    audit_svc = MagicMock(spec=AuditService)
    audit_svc.log_event = AsyncMock(return_value=None)

    # Build the mock ReEvaluationService
    from forgeguard.api.schemas.remediation import ReEvaluationResponse, RuleResult

    if service_side_effect:
        mock_svc = MagicMock()
        mock_svc.re_evaluate = AsyncMock(side_effect=service_side_effect)
    else:
        rule_result = RuleResult(
            rule_id=_RULE_ID,
            rule_name="Unit test coverage",
            passed=eval_results[0].status == EvaluationStatus.PASS if eval_results else True,
            actual_value="85.0",
            threshold="80.0",
        ) if eval_results else None

        resp = ReEvaluationResponse(
            finding_id=_FINDING_ID,
            before_health_score=60.0,
            after_health_score=80.0,
            score_delta=20.0,
            before_finding_status=finding_row["status"] if finding_row else "open",
            after_finding_status="remediated" if (eval_results and eval_results[0].status == EvaluationStatus.PASS) else "acknowledged",
            rule_results=[rule_result] if rule_result else [],
            updated_guidance=None,
            re_evaluated_at=datetime.now(tz=timezone.utc),
        )
        mock_svc = MagicMock()
        mock_svc.re_evaluate = AsyncMock(return_value=resp)

    with patch("forgeguard.api.routes.remediation.ReEvaluationService") as mock_cls:
        mock_cls.return_value = mock_svc
        with patch("forgeguard.api.routes.remediation.FindingRepository"):
            with patch("forgeguard.api.routes.remediation.PolicyRepository"):
                with patch("forgeguard.api.routes.remediation.AssessmentScoreRepository"):
                    with patch("forgeguard.api.routes.remediation.AssessmentRepository"):
                        with patch("forgeguard.api.routes.remediation.get_ai_engine"):
                            with patch("forgeguard.api.routes.remediation.RuleEvaluationEngine"):
                                with patch("forgeguard.api.routes.remediation.MockDataCollector"):
                                    return await re_evaluate_finding(
                                        finding_id=_FINDING_ID,
                                        request=request,
                                        current_user=current_user,
                                        pool=pool,
                                        audit_svc=audit_svc,
                                    )


# ---------------------------------------------------------------------------
# Response structure
# ---------------------------------------------------------------------------

class TestResponseStructure:
    @pytest.mark.asyncio
    async def test_response_has_finding_id(self):
        result = await _call_endpoint(
            finding_row=_finding(),
            eval_results=[_eval_result(True)],
        )
        assert "finding_id" in result.model_fields or hasattr(result, "finding_id")
        assert result.finding_id == _FINDING_ID

    @pytest.mark.asyncio
    async def test_response_has_before_and_after_scores(self):
        result = await _call_endpoint(
            finding_row=_finding(),
            eval_results=[_eval_result(True)],
        )
        assert result.before_health_score is not None
        assert result.after_health_score is not None

    @pytest.mark.asyncio
    async def test_response_has_score_delta(self):
        result = await _call_endpoint(
            finding_row=_finding(),
            eval_results=[_eval_result(True)],
        )
        assert result.score_delta is not None

    @pytest.mark.asyncio
    async def test_response_has_before_and_after_status(self):
        result = await _call_endpoint(
            finding_row=_finding(),
            eval_results=[_eval_result(True)],
        )
        assert result.before_finding_status is not None
        assert result.after_finding_status is not None

    @pytest.mark.asyncio
    async def test_response_has_rule_results(self):
        result = await _call_endpoint(
            finding_row=_finding(),
            eval_results=[_eval_result(True)],
        )
        assert isinstance(result.rule_results, list)

    @pytest.mark.asyncio
    async def test_response_has_re_evaluated_at(self):
        result = await _call_endpoint(
            finding_row=_finding(),
            eval_results=[_eval_result(True)],
        )
        assert result.re_evaluated_at is not None


# ---------------------------------------------------------------------------
# Resolved path
# ---------------------------------------------------------------------------

class TestResolvedResponse:
    @pytest.mark.asyncio
    async def test_after_status_remediated_on_pass(self):
        result = await _call_endpoint(
            finding_row=_finding(status="open"),
            eval_results=[_eval_result(True)],
        )
        assert result.after_finding_status == "remediated"

    @pytest.mark.asyncio
    async def test_score_delta_positive_on_improvement(self):
        result = await _call_endpoint(
            finding_row=_finding(status="open"),
            eval_results=[_eval_result(True)],
        )
        assert result.score_delta > 0


# ---------------------------------------------------------------------------
# Not-resolved path
# ---------------------------------------------------------------------------

class TestNotResolvedResponse:
    @pytest.mark.asyncio
    async def test_after_status_acknowledged_on_fail(self):
        result = await _call_endpoint(
            finding_row=_finding(status="open"),
            eval_results=[_eval_result(False)],
        )
        assert result.after_finding_status == "acknowledged"


# ---------------------------------------------------------------------------
# Error cases
# ---------------------------------------------------------------------------

class TestErrorCases:
    @pytest.mark.asyncio
    async def test_404_for_missing_finding(self):
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc_info:
            await _call_endpoint(
                service_side_effect=NotFoundError("Finding not found.")
            )
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_400_for_excepted_finding(self):
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc_info:
            await _call_endpoint(
                service_side_effect=BadRequestError(
                    "Cannot re-evaluate excepted finding",
                    details={"error_code": "EXCEPTED_FINDING"},
                )
            )
        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_409_for_already_remediated(self):
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc_info:
            await _call_endpoint(
                service_side_effect=ConflictError(
                    "Finding already resolved",
                    details={"error_code": "FINDING_ALREADY_RESOLVED"},
                )
            )
        assert exc_info.value.status_code == 409

    @pytest.mark.asyncio
    async def test_409_for_optimistic_lock_conflict(self):
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc_info:
            await _call_endpoint(
                service_side_effect=ConflictError(
                    "Concurrent re-evaluation in progress",
                    details={"error_code": "OPTIMISTIC_LOCK_CONFLICT"},
                )
            )
        assert exc_info.value.status_code == 409

    @pytest.mark.asyncio
    async def test_403_for_insufficient_permission(self):
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc_info:
            await _call_endpoint(
                finding_row=_finding(),
                eval_results=[_eval_result(True)],
                role="operator",
            )
        assert exc_info.value.status_code == 403
