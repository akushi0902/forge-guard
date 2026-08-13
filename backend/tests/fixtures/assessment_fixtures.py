"""Assessment pipeline test fixtures for WO-042.

Provides:
    - Stable UUIDs for services, assessments, and policy rules
    - Mock rule dicts covering all 5 dimensions with mix of pass/fail
    - Mock input data matching the Payment Service demo data
    - Pre-built DimensionScore and HealthScoreResult objects for expected outputs
    - AssessmentResult factory for orchestrator tests
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from forgeguard.services.assessment_orchestrator import AssessmentResult
from forgeguard.services.domain.evaluation import EvaluationStatus, RuleEvaluationResult
from forgeguard.services.domain.scoring import DimensionScore, HealthScoreResult
from forgeguard.services.domain.severity import SeverityLevel

# ---------------------------------------------------------------------------
# Stable IDs
# ---------------------------------------------------------------------------

SERVICE_ID = uuid.UUID("10000000-0000-0000-0000-000000000001")
ASSESSMENT_ID = uuid.UUID("20000000-0000-0000-0000-000000000001")
ASSESSMENT_ID_2 = uuid.UUID("20000000-0000-0000-0000-000000000002")

RULE_CQ_1 = uuid.UUID("30000000-0000-0000-0000-000000000001")  # code_quality
RULE_TC_1 = uuid.UUID("30000000-0000-0000-0000-000000000002")  # test_coverage
RULE_SEC_1 = uuid.UUID("30000000-0000-0000-0000-000000000003")  # security
RULE_DOC_1 = uuid.UUID("30000000-0000-0000-0000-000000000004")  # documentation
RULE_OPS_1 = uuid.UUID("30000000-0000-0000-0000-000000000005")  # operations_readiness

POLICY_ID = uuid.UUID("40000000-0000-0000-0000-000000000001")
SCORE_ID = uuid.UUID("50000000-0000-0000-0000-000000000001")

# ---------------------------------------------------------------------------
# Rule dicts (from DB, with dimension projected via JOIN)
# ---------------------------------------------------------------------------

def _rule_dict(
    id: uuid.UUID,
    name: str,
    dimension: str,
    rule_type: str,
    threshold_config: dict[str, Any],
    severity: str = "medium",
    weight: float = 1.0,
    is_active: bool = True,
) -> dict[str, Any]:
    return {
        "id": id,
        "policy_id": POLICY_ID,
        "name": name,
        "rule_type": rule_type,
        "threshold_config": threshold_config,
        "severity": severity,
        "weight": Decimal(str(weight)),
        "is_active": is_active,
        "dimension": dimension,
    }


# Rules that will PASS against the mock input data
RULE_CQ_COMPLEXITY = _rule_dict(
    id=RULE_CQ_1,
    name="Cyclomatic Complexity Check",
    dimension="code_quality",
    rule_type="threshold_lte",
    threshold_config={"data_key": "cyclomatic_complexity_avg", "threshold": 10},
    severity="medium",
)

RULE_OPS_RUNBOOK = _rule_dict(
    id=RULE_OPS_1,
    name="Runbook Check",
    dimension="operations_readiness",
    rule_type="threshold_eq",
    threshold_config={"data_key": "has_runbook", "threshold": True},
    severity="high",
)

# Rules that will FAIL against the mock input data
RULE_TC_COVERAGE = _rule_dict(
    id=RULE_TC_1,
    name="Unit Test Coverage",
    dimension="test_coverage",
    rule_type="threshold_gte",
    threshold_config={"data_key": "unit_test_coverage", "threshold": 80},
    severity="high",
)

RULE_SEC_CVE = _rule_dict(
    id=RULE_SEC_1,
    name="Critical CVE Check",
    dimension="security",
    rule_type="threshold_eq",
    threshold_config={"data_key": "critical_cve_count", "threshold": 0},
    severity="critical",
)

RULE_DOC_README = _rule_dict(
    id=RULE_DOC_1,
    name="README Exists Check",
    dimension="documentation",
    rule_type="threshold_eq",
    threshold_config={"data_key": "has_readme", "threshold": True},
    severity="medium",
)

ALL_RULES: list[dict[str, Any]] = [
    RULE_CQ_COMPLEXITY,
    RULE_TC_COVERAGE,
    RULE_SEC_CVE,
    RULE_DOC_README,
    RULE_OPS_RUNBOOK,
]

# ---------------------------------------------------------------------------
# Mock input data
# ---------------------------------------------------------------------------

MOCK_INPUT_DATA: dict[str, Any] = {
    "cyclomatic_complexity_avg": 8.2,    # PASS for ≤10
    "unit_test_coverage": 62.5,          # FAIL for ≥80
    "critical_cve_count": 2,             # FAIL for ==0
    "has_readme": False,                 # FAIL for ==True
    "has_runbook": True,                 # PASS for ==True
}

# ---------------------------------------------------------------------------
# Pre-built evaluation results
# ---------------------------------------------------------------------------

_NOW = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)

EVAL_RESULTS: list[RuleEvaluationResult] = [
    RuleEvaluationResult(
        rule_id=RULE_CQ_1,
        rule_name="Cyclomatic Complexity Check",
        dimension="code_quality",
        severity=SeverityLevel.MEDIUM,
        status=EvaluationStatus.PASS,
        actual_value=Decimal("8.2"),
        expected_value=Decimal("10"),
        evidence={"actual_value": "8.2", "expected_value": "10"},
        evaluated_at=_NOW,
    ),
    RuleEvaluationResult(
        rule_id=RULE_TC_1,
        rule_name="Unit Test Coverage",
        dimension="test_coverage",
        severity=SeverityLevel.HIGH,
        status=EvaluationStatus.FAIL,
        actual_value=Decimal("62.5"),
        expected_value=Decimal("80"),
        evidence={"actual_value": "62.5", "expected_value": "80"},
        evaluated_at=_NOW,
    ),
    RuleEvaluationResult(
        rule_id=RULE_SEC_1,
        rule_name="Critical CVE Check",
        dimension="security",
        severity=SeverityLevel.CRITICAL,
        status=EvaluationStatus.FAIL,
        actual_value=Decimal("2"),
        expected_value=Decimal("0"),
        evidence={"actual_value": "2", "expected_value": "0"},
        evaluated_at=_NOW,
    ),
    RuleEvaluationResult(
        rule_id=RULE_DOC_1,
        rule_name="README Exists Check",
        dimension="documentation",
        severity=SeverityLevel.MEDIUM,
        status=EvaluationStatus.FAIL,
        actual_value=False,
        expected_value=True,
        evidence={"actual_value": "False", "expected_value": "True"},
        evaluated_at=_NOW,
    ),
    RuleEvaluationResult(
        rule_id=RULE_OPS_1,
        rule_name="Runbook Check",
        dimension="operations_readiness",
        severity=SeverityLevel.HIGH,
        status=EvaluationStatus.PASS,
        actual_value=True,
        expected_value=True,
        evidence={"actual_value": "True", "expected_value": "True"},
        evaluated_at=_NOW,
    ),
]

# ---------------------------------------------------------------------------
# Pre-built dimension scores (for test assertions)
# ---------------------------------------------------------------------------

DIM_SCORES: dict[str, DimensionScore] = {
    "code_quality": DimensionScore(
        dimension="code_quality",
        score=Decimal("100"),
        total_rules=1,
        passed_rules=1,
        failed_rules=0,
        inconclusive_rules=0,
        error_rules=0,
        has_data=True,
    ),
    "test_coverage": DimensionScore(
        dimension="test_coverage",
        score=Decimal("0"),
        total_rules=1,
        passed_rules=0,
        failed_rules=1,
        inconclusive_rules=0,
        error_rules=0,
        has_data=True,
    ),
    "security": DimensionScore(
        dimension="security",
        score=Decimal("0"),
        total_rules=1,
        passed_rules=0,
        failed_rules=1,
        inconclusive_rules=0,
        error_rules=0,
        has_data=True,
    ),
    "documentation": DimensionScore(
        dimension="documentation",
        score=Decimal("0"),
        total_rules=1,
        passed_rules=0,
        failed_rules=1,
        inconclusive_rules=0,
        error_rules=0,
        has_data=True,
    ),
    "operations_readiness": DimensionScore(
        dimension="operations_readiness",
        score=Decimal("100"),
        total_rules=1,
        passed_rules=1,
        failed_rules=0,
        inconclusive_rules=0,
        error_rules=0,
        has_data=True,
    ),
}

# Expected overall_score: (100 + 0 + 0 + 0 + 100) / 5 = 40.00
EXPECTED_OVERALL_SCORE = Decimal("40.00")


def make_assessment_result(
    *,
    assessment_id: uuid.UUID = ASSESSMENT_ID,
    service_id: uuid.UUID = SERVICE_ID,
    overall_score: Decimal | None = EXPECTED_OVERALL_SCORE,
    status: str = "completed",
    message: str | None = None,
    finding_counts: dict[str, int] | None = None,
) -> AssessmentResult:
    return AssessmentResult(
        assessment_id=assessment_id,
        status=status,
        overall_score=overall_score,
        dimension_scores=DIM_SCORES,
        finding_counts=finding_counts or {"critical": 1, "high": 1, "medium": 1, "low": 0},
        evaluated_at=_NOW,
        message=message,
        findings=[],
    )


# ---------------------------------------------------------------------------
# Assessment DB row fixture
# ---------------------------------------------------------------------------

def make_assessment_row(
    *,
    id: uuid.UUID = ASSESSMENT_ID,
    service_id: uuid.UUID = SERVICE_ID,
    status: str = "completed",
) -> dict[str, Any]:
    return {
        "id": id,
        "service_id": service_id,
        "assessment_type": "health_check",
        "trigger_type": "manual",
        "triggered_by": None,
        "status": status,
        "collected_data": None,
        "started_at": _NOW,
        "completed_at": _NOW,
        "created_at": _NOW,
        "updated_at": _NOW,
    }
