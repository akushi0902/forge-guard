"""Dimension scoring domain types for the health score calculator (WO-039)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum
from typing import Optional

from forgeguard.services.domain.evaluation import EvaluationStatus


class PolicyDimension(str, Enum):
    """The five governance dimensions evaluated by the Policy Guardian."""

    CODE_QUALITY = "code_quality"
    TEST_COVERAGE = "test_coverage"
    SECURITY = "security"
    DOCUMENTATION = "documentation"
    OPERATIONS_READINESS = "operations_readiness"

    @classmethod
    def values(cls) -> frozenset[str]:
        return frozenset(m.value for m in cls)


VALID_DIMENSIONS: frozenset[str] = PolicyDimension.values()


@dataclass(frozen=True)
class ContributingFactor:
    """The contribution of a single rule to its dimension score."""

    rule_id: uuid.UUID
    rule_name: str
    status: EvaluationStatus
    weight: Decimal
    score_impact: Decimal


@dataclass
class DimensionScore:
    """Aggregated score for one governance dimension.

    score is None when has_data is False (no evaluated rules).
    """

    dimension: str
    score: Optional[Decimal]
    total_rules: int
    passed_rules: int
    failed_rules: int
    inconclusive_rules: int
    error_rules: int
    has_data: bool
    contributing_factors: list[ContributingFactor] = field(default_factory=list)
