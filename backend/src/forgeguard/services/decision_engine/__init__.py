"""Decision Engine package — score merging, threshold management, escalation, and routing."""

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
from forgeguard.services.decision_engine.router import DecisionRouter
from forgeguard.services.decision_engine.threshold_service import DecisionThresholdService

__all__ = [
    "DecisionEngine",
    "DecisionOutcome",
    "DecisionResult",
    "DEFAULT_THRESHOLDS",
    "DecisionRouter",
    "DecisionThresholdService",
    "EscalationResult",
    "SecurityEscalationService",
    "SYSTEM_ACTOR_UUID",
]
