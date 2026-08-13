"""SecurityEscalationService: auto-BLOCK override for critical security findings (WO-050).

After the threshold engine computes its initial recommendation, this service scans
the assessment's findings for any with severity=CRITICAL AND dimension=SECURITY.
If found, the recommendation is overridden to BLOCK and the escalation reasons are
recorded for audit and rationale purposes.

Design guarantees:
    - Fail-closed: any unexpected exception during the finding scan results in a
      BLOCK recommendation and logs an ERROR.  Availability is never prioritised
      over security when the escalation state is unknown.
    - Pure function: no I/O, no database calls, no side effects.  Completes
      in < 1ms regardless of finding count (simple linear scan over in-memory data).
    - The auto-BLOCK is absolute: no score combination can override a critical
      security escalation without an explicit Security Reviewer approval.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import structlog

from forgeguard.services.decision_engine.engine import DecisionOutcome, DecisionResult
from forgeguard.services.domain.severity import SeverityClassifier

logger = structlog.get_logger(__name__)

#: UUID used as actor_id in audit records created by the escalation system.
SYSTEM_ACTOR_UUID: str = "00000000-0000-0000-0000-000000000001"


@dataclass(frozen=True)
class EscalationResult:
    """Immutable output of :meth:`SecurityEscalationService.check_escalation`.

    Attributes:
        should_escalate:          True if at least one critical security finding was found.
        escalation_reasons:       List of dicts with ``finding_id`` and ``title`` for each
                                  critical security finding that triggered escalation.
        original_recommendation:  The threshold-based decision (before any override).
        final_recommendation:     BLOCK if escalated, else the original recommendation.
    """

    should_escalate: bool
    escalation_reasons: list[dict[str, str]] = field(default_factory=list)
    original_recommendation: DecisionOutcome = DecisionOutcome.BLOCK
    final_recommendation: DecisionOutcome = DecisionOutcome.BLOCK


def _get_field(obj: Any, attr: str) -> Any:
    """Extract a field from either a dict or an object attribute."""
    if isinstance(obj, dict):
        return obj.get(attr)
    return getattr(obj, attr, None)


class SecurityEscalationService:
    """Stateless post-threshold escalation check.

    Scans a list of findings for any with ``severity=CRITICAL`` AND
    ``dimension=security``.  If any are found, the recommendation is overridden
    to :attr:`~DecisionOutcome.BLOCK` and all triggering finding IDs and titles
    are captured in the escalation reasons.

    Fail-closed policy: any exception during scanning defaults to BLOCK to
    prevent critical security violations from slipping through on errors.
    """

    @staticmethod
    def check_escalation(
        findings: list[Any],
        threshold_decision: DecisionResult,
    ) -> EscalationResult:
        """Determine whether critical security findings require an escalation override.

        Args:
            findings:             List of finding dicts (from DB query or JSONB) or
                                  finding objects.  Each entry must have ``severity``
                                  and ``dimension`` fields (string values).  ``id`` and
                                  ``title`` are used for escalation_reasons if present.
            threshold_decision:   The :class:`DecisionResult` from
                                  :meth:`DecisionEngine.merge_scores`.

        Returns:
            :class:`EscalationResult` with ``should_escalate``, ``escalation_reasons``,
            and the ``final_recommendation`` (overridden to BLOCK if escalated).
        """
        original = threshold_decision.decision

        try:
            escalating: list[dict[str, str]] = []

            for f in findings:
                severity = _get_field(f, "severity")
                dimension = _get_field(f, "dimension")
                if severity is None or dimension is None:
                    continue

                try:
                    if SeverityClassifier.is_escalation_required(severity, str(dimension)):
                        finding_id = str(_get_field(f, "id") or "")
                        title = str(_get_field(f, "title") or "Critical security finding")
                        escalating.append({"finding_id": finding_id, "title": title})
                except ValueError:
                    # Unknown severity value — log and skip, do not hard-fail.
                    logger.warning(
                        "security_escalation.unknown_severity",
                        severity=severity,
                        dimension=dimension,
                    )

            if escalating:
                logger.info(
                    "security_escalation.triggered",
                    original_recommendation=original.value,
                    final_recommendation=DecisionOutcome.BLOCK.value,
                    escalating_finding_count=len(escalating),
                    finding_ids=[r["finding_id"] for r in escalating],
                )
                return EscalationResult(
                    should_escalate=True,
                    escalation_reasons=escalating,
                    original_recommendation=original,
                    final_recommendation=DecisionOutcome.BLOCK,
                )

            return EscalationResult(
                should_escalate=False,
                escalation_reasons=[],
                original_recommendation=original,
                final_recommendation=original,
            )

        except Exception as exc:
            # Fail-closed: any unexpected error defaults to BLOCK.
            logger.error(
                "security_escalation.check_failed",
                error=str(exc),
                error_type=type(exc).__name__,
                message="Failing closed to BLOCK — escalation check raised an exception",
            )
            return EscalationResult(
                should_escalate=True,
                escalation_reasons=[],
                original_recommendation=original,
                final_recommendation=DecisionOutcome.BLOCK,
            )
