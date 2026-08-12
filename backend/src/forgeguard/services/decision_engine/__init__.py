"""Decision Engine package — score merging, threshold management, and escalation (WO-049, WO-050)."""

from forgeguard.services.decision_engine.engine import (
    DecisionEngine,
    DecisionOutcome,
    DecisionResult,
    DEFAULT_THRESHOLDS,
)
from forgeguard.services.decision_engine.escalation_service import (
    EscalationResult,
    SecurityEscalationService,
    SYSTEM_ACTOR_UUID,
)
from forgeguard.services.decision_engine.threshold_service import DecisionThresholdService

__all__ = [
    "DecisionEngine",
    "DecisionOutcome",
    "DecisionResult",
    "DEFAULT_THRESHOLDS",
    "DecisionThresholdService",
    "EscalationResult",
    "SecurityEscalationService",
    "SYSTEM_ACTOR_UUID",
]
