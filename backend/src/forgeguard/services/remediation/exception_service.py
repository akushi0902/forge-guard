"""ExceptionService: exception request submission and approver routing (WO-062).

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

from forgeguard.core.exceptions import BadRequestError, ConflictError, NotFoundError
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
