"""Scoring test fixtures: pre-built RuleEvaluationResult lists (WO-039).

Provides deterministic result lists for testing DimensionScoreCalculator
across all scenarios: all-pass, all-fail, mixed, inconclusive, error, etc.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal

from forgeguard.services.domain.evaluation import EvaluationStatus, RuleEvaluationResult
from forgeguard.services.domain.severity import SeverityLevel

_TS = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)


def _r(
    *,
    name: str,
    dimension: str,
    status: EvaluationStatus,
    weight: str = "1.0",
    severity: SeverityLevel = SeverityLevel.HIGH,
    rule_id: uuid.UUID | None = None,
) -> RuleEvaluationResult:
    return RuleEvaluationResult(
        rule_id=rule_id or uuid.uuid4(),
        rule_name=name,
        dimension=dimension,
        severity=severity,
        status=status,
        actual_value=None,
        expected_value=None,
        evidence={},
        evaluated_at=_TS,
        weight=Decimal(weight),
    )


# ---------------------------------------------------------------------------
# All-pass: one dimension, three equal-weight passing rules → score 100.00
# ---------------------------------------------------------------------------

ALL_PASS_RESULTS: list[RuleEvaluationResult] = [
    _r(name="Coverage Check", dimension="test_coverage", status=EvaluationStatus.PASS),
    _r(name="Branch Check", dimension="test_coverage", status=EvaluationStatus.PASS),
    _r(name="Mutation Check", dimension="test_coverage", status=EvaluationStatus.PASS),
]

# ---------------------------------------------------------------------------
# All-fail: three equal-weight failing rules → score 0.00
# ---------------------------------------------------------------------------

ALL_FAIL_RESULTS: list[RuleEvaluationResult] = [
    _r(name="CVE Check", dimension="security", status=EvaluationStatus.FAIL),
    _r(name="Secrets Check", dimension="security", status=EvaluationStatus.FAIL),
    _r(name="SAST Check", dimension="security", status=EvaluationStatus.FAIL),
]

# ---------------------------------------------------------------------------
# Mixed: 2 pass (weight 2.0 each) + 1 fail (weight 1.0)
# weighted_pass=4.0, weighted_total=5.0 → score=80.00
# ---------------------------------------------------------------------------

MIXED_RESULTS: list[RuleEvaluationResult] = [
    _r(name="API Docs", dimension="documentation", status=EvaluationStatus.PASS, weight="2.0"),
    _r(name="README", dimension="documentation", status=EvaluationStatus.PASS, weight="2.0"),
    _r(name="Runbook", dimension="documentation", status=EvaluationStatus.FAIL, weight="1.0"),
]

# ---------------------------------------------------------------------------
# All inconclusive → score None, has_data False
# ---------------------------------------------------------------------------

ALL_INCONCLUSIVE_RESULTS: list[RuleEvaluationResult] = [
    _r(name="Complexity", dimension="code_quality", status=EvaluationStatus.INCONCLUSIVE),
    _r(name="Duplication", dimension="code_quality", status=EvaluationStatus.INCONCLUSIVE),
]

# ---------------------------------------------------------------------------
# Error rules treated as failures
# 1 pass (w=1.0) + 1 error (w=1.0) → weighted_pass=1, weighted_total=2, score=50.00
# ---------------------------------------------------------------------------

ERROR_RESULTS: list[RuleEvaluationResult] = [
    _r(name="Health Check", dimension="operations_readiness", status=EvaluationStatus.PASS, weight="1.0"),
    _r(name="Log Format", dimension="operations_readiness", status=EvaluationStatus.ERROR, weight="1.0"),
]

# ---------------------------------------------------------------------------
# Single rule pass → score 100.00
# ---------------------------------------------------------------------------

SINGLE_PASS_RESULTS: list[RuleEvaluationResult] = [
    _r(name="Only Rule", dimension="security", status=EvaluationStatus.PASS, weight="3.0"),
]

# ---------------------------------------------------------------------------
# Single rule fail → score 0.00
# ---------------------------------------------------------------------------

SINGLE_FAIL_RESULTS: list[RuleEvaluationResult] = [
    _r(name="Only Rule", dimension="security", status=EvaluationStatus.FAIL, weight="3.0"),
]

# ---------------------------------------------------------------------------
# Zero-weight rules: all pass but weight=0 → score None (weighted_total=0)
# ---------------------------------------------------------------------------

ZERO_WEIGHT_RESULTS: list[RuleEvaluationResult] = [
    _r(name="Informational Rule A", dimension="documentation", status=EvaluationStatus.PASS, weight="0.0"),
    _r(name="Informational Rule B", dimension="documentation", status=EvaluationStatus.PASS, weight="0.0"),
]

# ---------------------------------------------------------------------------
# Mixed statuses in one dimension: PASS + FAIL + INCONCLUSIVE + ERROR
# PASS w=2, FAIL w=1, ERROR w=1, INCONCLUSIVE excluded
# weighted_pass=2, weighted_total=4 → score=50.00
# ---------------------------------------------------------------------------

ALL_STATUS_RESULTS: list[RuleEvaluationResult] = [
    _r(name="Pass Rule", dimension="code_quality", status=EvaluationStatus.PASS, weight="2.0"),
    _r(name="Fail Rule", dimension="code_quality", status=EvaluationStatus.FAIL, weight="1.0"),
    _r(name="Inconclusive Rule", dimension="code_quality", status=EvaluationStatus.INCONCLUSIVE, weight="1.0"),
    _r(name="Error Rule", dimension="code_quality", status=EvaluationStatus.ERROR, weight="1.0"),
]

# ---------------------------------------------------------------------------
# Multi-dimension batch: results spanning all 5 dimensions
# ---------------------------------------------------------------------------

MULTI_DIMENSION_RESULTS: list[RuleEvaluationResult] = [
    _r(name="CQ Rule 1", dimension="code_quality", status=EvaluationStatus.PASS, weight="1.0"),
    _r(name="CQ Rule 2", dimension="code_quality", status=EvaluationStatus.FAIL, weight="1.0"),
    _r(name="TC Rule 1", dimension="test_coverage", status=EvaluationStatus.PASS, weight="2.0"),
    _r(name="SEC Rule 1", dimension="security", status=EvaluationStatus.FAIL, weight="3.0"),
    _r(name="DOC Rule 1", dimension="documentation", status=EvaluationStatus.PASS, weight="1.0"),
    _r(name="OPS Rule 1", dimension="operations_readiness", status=EvaluationStatus.PASS, weight="1.0"),
]

# ---------------------------------------------------------------------------
# 50-rule dimension for benchmark testing
# ---------------------------------------------------------------------------

FIFTY_RULE_RESULTS: list[RuleEvaluationResult] = [
    _r(
        name=f"Rule {i:02d}",
        dimension="test_coverage",
        status=EvaluationStatus.PASS if i % 3 != 0 else EvaluationStatus.FAIL,
        weight="1.0",
    )
    for i in range(50)
]
