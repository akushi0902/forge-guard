"""ExceptionService: exception request submission, routing, and decision (WO-062, WO-064).

Routing rules (business-defined, tested independently):
  - finding.dimension == 'security'  →  approver_role = 'security_reviewer'
  - any other dimension              →  approver_role = 'platform_admin'

Security exceptions must always route to Security Reviewer; Platform Admin
cannot approve them (enforced at the approval layer, not here).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Optional

import structlog

from forgeguard.core.exceptions import BadRequestError, ConflictError, ForbiddenError, NotFoundError
from forgeguard.data.repositories.exception_repository import ExceptionRepository
from forgeguard.data.repositories.findings import FindingRepository
from forgeguard.services.audit import AuditService

logger = structlog.get_logger(__name__)

_SECURITY_DIMENSION = "security"
_APPROVER_SECURITY = "security_reviewer"
_APPROVER_DEFAULT = "platform_admin"

# Finding statuses that do not allow exception requests.
_TERMINAL_FINDING_STATUSES = {"remediated", "exception_granted"}


def _route_approver(dimension: str) -> str:
    """Return the approver role for a finding's dimension.

    Args:
        dimension: The finding's engineering dimension string.

    Returns:
        'security_reviewer' for security findings; 'platform_admin' otherwise.
    """
    return _APPROVER_SECURITY if dimension == _SECURITY_DIMENSION else _APPROVER_DEFAULT


class ExceptionService:
    """Orchestrates exception request submission, validation, and audit logging."""

    def __init__(
        self,
        exception_repo: ExceptionRepository,
        finding_repo: FindingRepository,
        audit_service: Optional[AuditService] = None,
    ) -> None:
        self._exception_repo = exception_repo
        self._finding_repo = finding_repo
        self._audit = audit_service

    async def _audit_log(self, **kwargs: Any) -> None:
        if self._audit is None:
            return
        try:
            await self._audit.log_event(**kwargs)
        except Exception:
            logger.warning("exception_service.audit_log_failed", kwargs=str(kwargs))

    @staticmethod
    def _row_to_serializable(row: dict[str, Any] | None) -> dict[str, Any] | None:
        if row is None:
            return None
        result = {}
        for k, v in row.items():
            if isinstance(v, uuid.UUID):
                result[k] = str(v)
            elif hasattr(v, "isoformat"):
                result[k] = v.isoformat()
            else:
                result[k] = v
        return result

    async def submit_request(
        self,
        *,
        finding_id: str | uuid.UUID,
        justification: str,
        expires_at: datetime,
        actor_id: str | None,
        actor_role: str,
    ) -> dict[str, Any]:
        """Validate, route, persist, and audit an exception request.

        Args:
            finding_id:    UUID of the finding being excepted.
            justification: Trimmed justification string (≥20 chars, already validated).
            expires_at:    Future datetime ≤90 days out (already validated).
            actor_id:      UUID string of the requesting user (or None if unknown).
            actor_role:    Role string of the requesting user.

        Returns:
            The persisted exception row as a dict.

        Raises:
            NotFoundError:  Finding does not exist.
            BadRequestError: Finding is in a terminal state (resolved/suppressed).
            ConflictError:   Pending or active exception already exists.
        """
        finding = await self._finding_repo.get_by_id(finding_id)
        if finding is None:
            raise NotFoundError(f"Finding {finding_id} not found.")

        finding_status = finding.get("status", "")
        if finding_status in _TERMINAL_FINDING_STATUSES:
            raise BadRequestError(
                f"Finding is in '{finding_status}' status and does not need an exception.",
                details={"error_code": "FINDING_ALREADY_RESOLVED"},
            )

        pending = await self._exception_repo.check_existing_pending(finding_id)
        if pending is not None:
            raise ConflictError("An exception request is already pending for this finding.")

        active = await self._exception_repo.check_existing_approved_active(finding_id)
        if active is not None:
            raise ConflictError("An active approved exception already exists for this finding.")

        approver_role = _route_approver(finding.get("dimension", ""))

        new_id = uuid.uuid4()
        payload: dict[str, Any] = {
            "id": new_id,
            "finding_id": uuid.UUID(str(finding_id)),
            "requested_by": uuid.UUID(str(actor_id)) if actor_id else None,
            "justification": justification,
            "status": "pending",
            "approver_role": approver_role,
            "expires_at": expires_at,
        }
        created = await self._exception_repo.create(payload)

        await self._audit_log(
            actor_id=actor_id,
            actor_role=actor_role,
            action="exception.requested",
            resource_type="exception",
            resource_id=new_id,
            before_state={"finding_status": finding_status},
            after_state=self._row_to_serializable(created),
        )

        logger.info(
            "exception_service.request_submitted",
            exception_id=str(new_id),
            finding_id=str(finding_id),
            approver_role=approver_role,
            actor_role=actor_role,
        )
        return created

    async def get_exception(
        self, exception_id: str | uuid.UUID
    ) -> dict[str, Any] | None:
        """Return a single exception record by ID, or None."""
        return await self._exception_repo.get_by_id(exception_id)

    async def decide_exception(
        self,
        *,
        exception_id: str | uuid.UUID,
        decision: str,
        decision_comment: str,
        actor_id: str | None,
        actor_role: str,
    ) -> dict[str, Any]:
        """Approve or deny a pending exception request.

        Args:
            exception_id:      UUID of the exception to decide.
            decision:          'approved' or 'denied'.
            decision_comment:  Mandatory comment (≥10 chars, already validated).
            actor_id:          UUID string of the deciding user.
            actor_role:        Role string of the deciding user.

        Returns:
            Decision result dict including finding_status and health_score_impact.

        Raises:
            NotFoundError:   Exception or finding not found.
            ConflictError:   Exception already decided (409) or expired (409).
            ForbiddenError:  Actor role does not match exception.approver_role (403).
            BadRequestError: Finding is already resolved — approval not needed (400).
        """
        exception = await self._exception_repo.get_by_id(exception_id)
        if exception is None:
            raise NotFoundError(f"Exception {exception_id} not found.")

        exc_status = exception.get("status", "")
        if exc_status == "expired":
            raise ConflictError("Exception has expired.")
        if exc_status != "pending":
            raise ConflictError("Exception already decided.")

        required_role = exception.get("approver_role", "")
        if actor_role != required_role:
            raise ForbiddenError(
                f"This exception requires approval from {required_role} role",
                details={"required_role": required_role},
            )

        finding_id = exception.get("finding_id")
        finding = await self._finding_repo.get_by_id(finding_id)
        if finding is None:
            raise NotFoundError(f"Finding {finding_id} not found.")

        finding_status_before = finding.get("status", "")

        if decision == "approved" and finding_status_before == "remediated":
            raise BadRequestError(
                "Finding already resolved, exception not needed",
                details={"error_code": "FINDING_ALREADY_RESOLVED"},
            )

        requested_by = exception.get("requested_by")
        if actor_id and requested_by and str(actor_id) == str(requested_by):
            logger.warning(
                "exception_service.self_approval_detected",
                exception_id=str(exception_id),
                actor_id=str(actor_id),
            )

        now = datetime.now(timezone.utc)
        decided_by = uuid.UUID(str(actor_id)) if actor_id else None

        updated_exception = await self._exception_repo.update_decision(
            exception_id,
            status=decision,
            decided_by=decided_by,
            decided_at=now,
            decision_comment=decision_comment,
        )
        if updated_exception is None:
            raise ConflictError("Exception already decided.")

        finding_status_after = finding_status_before
        if decision == "approved":
            try:
                updated_finding = await self._finding_repo.update_status(
                    finding_id, "exception_granted"
                )
                if updated_finding:
                    finding_status_after = updated_finding.get("status", "exception_granted")
            except Exception as exc:
                logger.error(
                    "exception_service.finding_status_update_failed",
                    exception_id=str(exception_id),
                    finding_id=str(finding_id),
                    error=str(exc),
                )

        health_score_impact = None
        if decision == "approved":
            service_id = str(finding.get("service_id", ""))
            health_score_impact = await self._trigger_health_score_recalculation(service_id)

        await self._audit_log(
            actor_id=actor_id,
            actor_role=actor_role,
            action=f"exception.{decision}",
            resource_type="exception",
            resource_id=exception_id,
            before_state={"status": exc_status},
            after_state=self._row_to_serializable(updated_exception),
        )
        if decision == "approved":
            await self._audit_log(
                actor_id=actor_id,
                actor_role=actor_role,
                action="finding.excepted",
                resource_type="finding",
                resource_id=finding_id,
                before_state={"status": finding_status_before},
                after_state={"status": finding_status_after},
            )

        exc_id = updated_exception.get("id") if updated_exception else exception.get("id")
        exc_finding_id = updated_exception.get("finding_id") if updated_exception else finding_id

        logger.info(
            "exception_service.decision_recorded",
            exception_id=str(exception_id),
            decision=decision,
            actor_role=actor_role,
        )
        return {
            "id": exc_id,
            "finding_id": exc_finding_id,
            "status": decision,
            "decided_by": decided_by,
            "decision_comment": decision_comment,
            "decided_at": now,
            "finding_status": finding_status_after,
            "health_score_impact": health_score_impact,
        }

    async def _trigger_health_score_recalculation(self, service_id: str) -> dict | None:
        """Emit a recalculation trigger for the health scoring pipeline (non-fatal)."""
        try:
            logger.info(
                "exception_service.trigger_health_score_recalculation",
                service_id=service_id,
                action="health_score.recalculation_requested",
            )
        except Exception as exc:
            logger.error(
                "exception_service.health_score_recalculation_failed",
                service_id=service_id,
                error=str(exc),
            )
        return None
