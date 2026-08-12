"""Core Decision Engine: merge_scores() and DecisionOutcome (WO-049).

The merge operation is a pure function with no I/O.  It completes in < 1ms
regardless of input values — well within the 10ms latency budget.

Decision logic (evaluated strictly in order to prevent ambiguity):
    1. APPROVE        — health_score >= approve_health_min AND
                        risk_score  <= approve_risk_max
    2. CONDITIONAL    — health_score >= conditional_health_min AND
                        risk_score  <= conditional_risk_max
    3. BLOCK          — all other cases (default)

The ordering ensures that a score combination meeting both APPROVE and
CONDITIONAL thresholds is always classified as APPROVE.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


class DecisionOutcome(str, Enum):
    """Three possible combined release decisions."""

    APPROVE = "APPROVE"
    CONDITIONAL_APPROVE = "CONDITIONAL_APPROVE"
    BLOCK = "BLOCK"


# ---------------------------------------------------------------------------
# Default threshold constants
# ---------------------------------------------------------------------------

DEFAULT_THRESHOLDS: dict[str, Decimal] = {
    "approve_health_min": Decimal("70.00"),
    "approve_risk_max": Decimal("30.00"),
    "conditional_health_min": Decimal("50.00"),
    "conditional_risk_max": Decimal("60.00"),
}


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class DecisionResult:
    """Immutable result of a merge_scores() call.

    Attributes:
        decision:              APPROVE / CONDITIONAL_APPROVE / BLOCK.
        health_score:          Input health score used for the comparison.
        risk_score:            Input risk score used for the comparison.
        threshold_config_id:   UUID of the threshold config used (None if defaults).
        contributing_factors:  Dict of threshold values and pass/fail flags for each
                               condition, providing a full audit trail.
    """

    decision: DecisionOutcome
    health_score: Decimal
    risk_score: Decimal
    threshold_config_id: uuid.UUID | None
    contributing_factors: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------

class DecisionEngine:
    """Deterministic release decision engine.

    All decision logic lives in the stateless :meth:`merge_scores` class method
    so it can be called directly in unit tests without instantiation overhead.
    The instance methods are thin wrappers that resolve the active threshold
    from a pre-loaded config dict.
    """

    def __init__(self, threshold_config: dict[str, Any] | None = None) -> None:
        self._config = threshold_config

    @classmethod
    def merge_scores(
        cls,
        health_score: Decimal,
        risk_score: Decimal,
        *,
        threshold_config: dict[str, Any] | None = None,
    ) -> DecisionResult:
        """Merge health and risk scores into a deterministic release decision.

        This is a **pure function**: no I/O, no side effects, no randomness.
        The result for a given (health_score, risk_score, threshold_config)
        triple is always identical.

        Args:
            health_score:      Engineering Health Score (0–100 Decimal).
            risk_score:        Release Risk Score (0–100 Decimal, lower = safer).
            threshold_config:  Optional threshold overrides loaded from DB.
                               Falls back to :data:`DEFAULT_THRESHOLDS` if None
                               or missing keys.

        Returns:
            :class:`DecisionResult` with decision, contributing_factors, and the
            threshold_config_id that was used.

        Raises:
            ValueError: If health_score or risk_score is outside the [0, 100] range.
        """
        health_score = Decimal(str(health_score))
        risk_score = Decimal(str(risk_score))

        # Input validation
        if not (Decimal("0") <= health_score <= Decimal("100")):
            raise ValueError(
                f"health_score must be in [0, 100], got {health_score}"
            )
        if not (Decimal("0") <= risk_score <= Decimal("100")):
            raise ValueError(
                f"risk_score must be in [0, 100], got {risk_score}"
            )

        # Resolve thresholds — fall back to hardcoded defaults for any missing key.
        cfg = threshold_config or {}
        approve_health_min = Decimal(str(cfg.get("approve_health_min", DEFAULT_THRESHOLDS["approve_health_min"])))
        approve_risk_max = Decimal(str(cfg.get("approve_risk_max", DEFAULT_THRESHOLDS["approve_risk_max"])))
        conditional_health_min = Decimal(str(cfg.get("conditional_health_min", DEFAULT_THRESHOLDS["conditional_health_min"])))
        conditional_risk_max = Decimal(str(cfg.get("conditional_risk_max", DEFAULT_THRESHOLDS["conditional_risk_max"])))

        config_id: uuid.UUID | None = None
        if cfg.get("id"):
            try:
                config_id = uuid.UUID(str(cfg["id"]))
            except (ValueError, AttributeError):
                config_id = None

        # Evaluate conditions.
        approve_health_ok = health_score >= approve_health_min
        approve_risk_ok = risk_score <= approve_risk_max
        conditional_health_ok = health_score >= conditional_health_min
        conditional_risk_ok = risk_score <= conditional_risk_max

        contributing_factors = {
            "approve_health_min": str(approve_health_min),
            "approve_risk_max": str(approve_risk_max),
            "conditional_health_min": str(conditional_health_min),
            "conditional_risk_max": str(conditional_risk_max),
            "approve_health_ok": approve_health_ok,
            "approve_risk_ok": approve_risk_ok,
            "conditional_health_ok": conditional_health_ok,
            "conditional_risk_ok": conditional_risk_ok,
        }

        # Strict evaluation order: APPROVE → CONDITIONAL_APPROVE → BLOCK.
        if approve_health_ok and approve_risk_ok:
            decision = DecisionOutcome.APPROVE
        elif conditional_health_ok and conditional_risk_ok:
            decision = DecisionOutcome.CONDITIONAL_APPROVE
        else:
            decision = DecisionOutcome.BLOCK

        logger.debug(
            "decision_engine.merge_scores",
            health_score=str(health_score),
            risk_score=str(risk_score),
            decision=decision.value,
            threshold_config_id=str(config_id) if config_id else None,
        )

        return DecisionResult(
            decision=decision,
            health_score=health_score,
            risk_score=risk_score,
            threshold_config_id=config_id,
            contributing_factors=contributing_factors,
        )

    def decide(
        self,
        health_score: Decimal,
        risk_score: Decimal,
    ) -> DecisionResult:
        """Convenience instance method using the config passed at construction."""
        return self.merge_scores(
            health_score,
            risk_score,
            threshold_config=self._config,
        )
