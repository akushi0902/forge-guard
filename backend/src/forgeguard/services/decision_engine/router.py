"""DecisionRouter: routes completed release assessments to the correct reviewer (WO-053).

Routing rules:
    - escalation_result.should_escalate=True  → assign to 'security_reviewer'
    - escalation_result.should_escalate=False → assign to 'tech_lead'

The router creates an immutable assignment record and an audit log entry for
each routing decision.  Routing failure is non-fatal: if the assignment write
fails, the error is logged at ERROR level but the assessment outcome is not
affected.  Reviewers can still discover the assessment manually.

Design:
    - DecisionRouter is a lightweight class; construct it with a repository and
      an optional audit service for dependency injection / testing.
    - route_decision() is async — it performs one INSERT into decision_assignments
      and one audit log write.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any, Optional

import structlog

from forgeguard.services.decision_engine.escalation_service import EscalationResult

if TYPE_CHECKING:
    from forgeguard.data.repositories.decision_assignment_repository import (
        DecisionAssignmentRepository,
    )
    from forgeguard.services.audit import AuditService

logger = structlog.get_logger(__name__)

#: Role assigned when a critical security escalation is required.
ESCALATED_ROLE = "security_reviewer"
#: Role assigned for all non-escalated assessments.
DEFAULT_ROLE = "tech_lead"


class DecisionRouter:
    """Routes completed release assessments to the appropriate reviewer role.

    Args:
        assignment_repo: Repository for creating and querying decision assignments.
        audit_svc:       Optional audit service; if provided, each assignment
                         creation is logged with action='decision_assignment'.
    """

    def __init__(
        self,
        assignment_repo: "DecisionAssignmentRepository",
        audit_svc: Optional["AuditService"] = None,
    ) -> None:
        self._repo = assignment_repo
        self._audit = audit_svc

    async def route_decision(
        self,
        assessment_id: uuid.UUID,
        escalation_result: EscalationResult,
        *,
        actor_id: Optional[str] = None,
        actor_role: str = "system",
    ) -> dict[str, Any] | None:
        """Create a decision assignment for the completed assessment.

        Args:
            assessment_id:     UUID of the completed release_assessment.
            escalation_result: Output from SecurityEscalationService.check_escalation().
            actor_id:          UUID string of the actor (user or system) triggering routing.
            actor_role:        Role of the actor triggering routing (for audit).

        Returns:
            The created assignment row dict, or None if the write failed.
        """
        assigned_role = ESCALATED_ROLE if escalation_result.should_escalate else DEFAULT_ROLE

        assignment_data: dict[str, Any] = {
            "id": uuid.uuid4(),
            "release_assessment_id": assessment_id,
            "assigned_role": assigned_role,
            "status": "pending",
        }

        try:
            assignment = await self._repo.create(assignment_data)
        except Exception as exc:
            logger.error(
                "decision_router.assignment_create_failed",
                assessment_id=str(assessment_id),
                assigned_role=assigned_role,
                error=str(exc),
                error_type=type(exc).__name__,
            )
            return None

        logger.info(
            "decision_router.assignment_created",
            assessment_id=str(assessment_id),
            assigned_role=assigned_role,
            assignment_id=str(assignment["id"]),
            should_escalate=escalation_result.should_escalate,
        )

        if self._audit is not None:
            try:
                await self._audit.log_event(
                    actor_id=actor_id,
                    actor_role=actor_role,
                    action="decision_assignment",
                    resource_type="decision_assignment",
                    resource_id=assignment["id"],
                    before_state=None,
                    after_state={
                        "assigned_role": assigned_role,
                        "assessment_id": str(assessment_id),
                        "should_escalate": escalation_result.should_escalate,
                        "status": "pending",
                    },
                )
            except Exception as exc:
                logger.warning(
                    "decision_router.audit_failed",
                    assignment_id=str(assignment["id"]),
                    error=str(exc),
                )

        return assignment
