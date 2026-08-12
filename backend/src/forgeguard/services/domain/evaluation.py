"""Evaluation domain types for the rule evaluation engine (WO-038)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any

from forgeguard.services.domain.severity import SeverityLevel


class EvaluationStatus(str, Enum):
    """Possible outcomes of evaluating a single policy rule."""

    PASS = "pass"
    FAIL = "fail"
    INCONCLUSIVE = "inconclusive"
    ERROR = "error"


@dataclass(frozen=True)
class RuleEvaluationResult:
    """Immutable result of evaluating one policy rule against input data."""

    rule_id: uuid.UUID
    rule_name: str
    dimension: str
    severity: SeverityLevel
    status: EvaluationStatus
    actual_value: Any
    expected_value: Any
    evidence: dict
    evaluated_at: datetime
