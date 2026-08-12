"""Health score test fixtures (WO-040).

Pre-built DimensionScore inputs and expected HealthScoreResult outputs for
testing HealthScoreAggregator across all scenarios.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal

from forgeguard.services.domain.scoring import DimensionScore

_ASSESSMENT_ID = uuid.UUID("d0000000-0000-0000-0000-000000000001")
_SERVICE_ID = uuid.UUID("d0000000-0000-0000-0000-000000000002")


def _ds(
    *,
    dimension: str,
    score: Decimal | None,
    has_data: bool = True,
    passed: int = 1,
    failed: int = 0,
) -> DimensionScore:
    return DimensionScore(
        dimension=dimension,
        score=score,
        total_rules=passed + failed,
        passed_rules=passed,
        failed_rules=failed,
        inconclusive_rules=0,
        error_rules=0,
        has_data=has_data,
        contributing_factors=[],
    )


# ---------------------------------------------------------------------------
# All five dimensions with data, equal scores → overall = each score
# ---------------------------------------------------------------------------

ALL_EQUAL_80: dict[str, DimensionScore] = {
    "code_quality": _ds(dimension="code_quality", score=Decimal("80.00")),
    "test_coverage": _ds(dimension="test_coverage", score=Decimal("80.00")),
    "security": _ds(dimension="security", score=Decimal("80.00")),
    "documentation": _ds(dimension="documentation", score=Decimal("80.00")),
    "operations_readiness": _ds(dimension="operations_readiness", score=Decimal("80.00")),
}
# Expected: overall = 80.00 (all equal, any weights)

# ---------------------------------------------------------------------------
# All five dimensions, varied scores, equal weights
# (50 + 60 + 70 + 80 + 90) / 5 = 70.00
# ---------------------------------------------------------------------------

VARIED_EQUAL_WEIGHTS: dict[str, DimensionScore] = {
    "code_quality": _ds(dimension="code_quality", score=Decimal("50.00")),
    "test_coverage": _ds(dimension="test_coverage", score=Decimal("60.00")),
    "security": _ds(dimension="security", score=Decimal("70.00")),
    "documentation": _ds(dimension="documentation", score=Decimal("80.00")),
    "operations_readiness": _ds(dimension="operations_readiness", score=Decimal("90.00")),
}
# Expected with equal weights (20 each): (50*20+60*20+70*20+80*20+90*20)/100 = 70.00

# ---------------------------------------------------------------------------
# Custom weights — security gets double weight
# weights: code_quality=10, test_coverage=20, security=40, documentation=20, ops=10
# scores: 100, 100, 50, 100, 100
# weighted sum = 10*100 + 20*100 + 40*50 + 20*100 + 10*100 = 1000+2000+2000+2000+1000 = 8000
# / 100 = 80.00
# ---------------------------------------------------------------------------

SECURITY_WEIGHTED: dict[str, DimensionScore] = {
    "code_quality": _ds(dimension="code_quality", score=Decimal("100.00")),
    "test_coverage": _ds(dimension="test_coverage", score=Decimal("100.00")),
    "security": _ds(dimension="security", score=Decimal("50.00")),
    "documentation": _ds(dimension="documentation", score=Decimal("100.00")),
    "operations_readiness": _ds(dimension="operations_readiness", score=Decimal("100.00")),
}
SECURITY_WEIGHTS: dict[str, Decimal] = {
    "code_quality": Decimal("10"),
    "test_coverage": Decimal("20"),
    "security": Decimal("40"),
    "documentation": Decimal("20"),
    "operations_readiness": Decimal("10"),
}
# Expected: 80.00

# ---------------------------------------------------------------------------
# One dimension missing — weight redistributed proportionally
# docs has no data; remaining 4 each get +5 (20% each → 25% effective)
# scores: 80, 80, 80, 80 with effective weight 25 each
# overall = 80.00
# ---------------------------------------------------------------------------

DOCS_NO_DATA: dict[str, DimensionScore] = {
    "code_quality": _ds(dimension="code_quality", score=Decimal("80.00")),
    "test_coverage": _ds(dimension="test_coverage", score=Decimal("80.00")),
    "security": _ds(dimension="security", score=Decimal("80.00")),
    "documentation": _ds(dimension="documentation", score=None, has_data=False),
    "operations_readiness": _ds(dimension="operations_readiness", score=Decimal("80.00")),
}
# Expected: overall = 80.00, dimensions_with_data=4, dimensions_without_data=1

# ---------------------------------------------------------------------------
# Two dimensions missing — code_quality and test_coverage no data
# Remaining: security=60, docs=90, ops=75 with weights 20,20,20 → effective 33.33 each
# weighted sum = (60+90+75)/3 = 225/3 = 75.00
# ---------------------------------------------------------------------------

TWO_MISSING: dict[str, DimensionScore] = {
    "code_quality": _ds(dimension="code_quality", score=None, has_data=False),
    "test_coverage": _ds(dimension="test_coverage", score=None, has_data=False),
    "security": _ds(dimension="security", score=Decimal("60.00")),
    "documentation": _ds(dimension="documentation", score=Decimal("90.00")),
    "operations_readiness": _ds(dimension="operations_readiness", score=Decimal("75.00")),
}
# Expected: overall = 75.00, dimensions_with_data=3, dimensions_without_data=2

# ---------------------------------------------------------------------------
# All dimensions missing → overall = None
# ---------------------------------------------------------------------------

ALL_NO_DATA: dict[str, DimensionScore] = {
    "code_quality": _ds(dimension="code_quality", score=None, has_data=False),
    "test_coverage": _ds(dimension="test_coverage", score=None, has_data=False),
    "security": _ds(dimension="security", score=None, has_data=False),
    "documentation": _ds(dimension="documentation", score=None, has_data=False),
    "operations_readiness": _ds(dimension="operations_readiness", score=None, has_data=False),
}
# Expected: overall = None, dimensions_with_data=0, dimensions_without_data=5

# ---------------------------------------------------------------------------
# Single dimension with data → gets 100% effective weight
# security=72.50 only; expected overall = 72.50
# ---------------------------------------------------------------------------

SINGLE_DIMENSION: dict[str, DimensionScore] = {
    "code_quality": _ds(dimension="code_quality", score=None, has_data=False),
    "test_coverage": _ds(dimension="test_coverage", score=None, has_data=False),
    "security": _ds(dimension="security", score=Decimal("72.50")),
    "documentation": _ds(dimension="documentation", score=None, has_data=False),
    "operations_readiness": _ds(dimension="operations_readiness", score=None, has_data=False),
}
# Expected: overall = 72.50, dimensions_with_data=1

# ---------------------------------------------------------------------------
# Boundary: all 0.00
# ---------------------------------------------------------------------------

ALL_ZERO: dict[str, DimensionScore] = {
    "code_quality": _ds(dimension="code_quality", score=Decimal("0.00"), failed=1, passed=0),
    "test_coverage": _ds(dimension="test_coverage", score=Decimal("0.00"), failed=1, passed=0),
    "security": _ds(dimension="security", score=Decimal("0.00"), failed=1, passed=0),
    "documentation": _ds(dimension="documentation", score=Decimal("0.00"), failed=1, passed=0),
    "operations_readiness": _ds(dimension="operations_readiness", score=Decimal("0.00"), failed=1, passed=0),
}
# Expected: overall = 0.00

# ---------------------------------------------------------------------------
# Boundary: all 100.00
# ---------------------------------------------------------------------------

ALL_HUNDRED: dict[str, DimensionScore] = {
    "code_quality": _ds(dimension="code_quality", score=Decimal("100.00")),
    "test_coverage": _ds(dimension="test_coverage", score=Decimal("100.00")),
    "security": _ds(dimension="security", score=Decimal("100.00")),
    "documentation": _ds(dimension="documentation", score=Decimal("100.00")),
    "operations_readiness": _ds(dimension="operations_readiness", score=Decimal("100.00")),
}
# Expected: overall = 100.00
