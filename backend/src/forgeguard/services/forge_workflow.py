"""Forge Workflow Engine adapter for release decision routing (WO-092).

Triggers Forge Workflow reviews for CONDITIONAL_APPROVE and BLOCK decisions,
tracks workflow lifecycle via polling, and falls back to dashboard notifications
when the Forge Workflow Engine is unavailable.

Security:
    FORGE_WORKFLOW_API_KEY is NEVER logged, included in error messages, or
    stored beyond this module.  Injected exclusively via X-Forge-Api-Key header.

Routing rules:
    CONDITIONAL_APPROVE           → Tech Lead  (reviewer participant)
    BLOCK                         → Tech Lead  (reviewer participant)
    BLOCK + CRITICAL+SECURITY     → Security Reviewer  (security_gate participant)
    Timeout escalation            → Platform Admin  (admin_reviewer participant)

Circuit breaker (mirrors AI engine config defaults):
    5 failures in 60 s → OPEN for 30 s → HALF_OPEN probe → CLOSED on success.
"""

from __future__ import annotations

import asyncio
import uuid
from abc import ABC, abstractmethod
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import httpx
import structlog

from forgeguard.services.ai_engine.circuit_breaker import CircuitBreaker
from forgeguard.services.ai_engine.errors import CircuitOpenError
from forgeguard.services.decision_engine.engine import DecisionOutcome

logger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

ROUTING_METHOD_FORGE = "forge_workflow"
ROUTING_METHOD_FALLBACK = "dashboard_fallback"

_WORKFLOW_TIMEOUT_HOURS = 24
_HTTP_TIMEOUT = 10.0
_TERMINAL_STATUSES = frozenset({"approved", "rejected", "timed_out"})

# Participant role mapping: ForgeGuard role → Forge Workflow participant type
_PARTICIPANT_MAP: dict[str, str] = {
    "tech_lead": "reviewer",
    "security_reviewer": "security_gate",
    "platform_admin": "admin_reviewer",
}


# ---------------------------------------------------------------------------
# Abstract interface (AC-6)
# ---------------------------------------------------------------------------


class ForgeWorkflowAdapter(ABC):
    """Abstract adapter for triggering and monitoring Forge Workflow reviews."""

    @abstractmethod
    async def trigger_workflow(
        self,
        *,
        decision_id: uuid.UUID,
        assessment_id: uuid.UUID,
        decision: str,
        reviewer_role: str,
        context: dict[str, Any],
        audit_svc: Any = None,
    ) -> dict[str, Any] | None:
        """Trigger a workflow and return the response, or None on failure."""

    @abstractmethod
    async def get_workflow_status(self, workflow_id: str) -> dict[str, Any] | None:
        """Poll workflow status.  Returns None on 404 or transient error."""

    @abstractmethod
    async def activate_fallback(
        self,
        *,
        decision_id: uuid.UUID,
        assessment_id: uuid.UUID,
        target_role: str,
        context: dict[str, Any],
        reason: str,
        audit_svc: Any = None,
    ) -> None:
        """Record a dashboard-fallback notification for manual review."""

    @staticmethod
    def determine_reviewer_role(
        decision: str | DecisionOutcome,
        *,
        findings: list[Any] | None = None,
    ) -> str:
        """Map a decision outcome to the appropriate ForgeGuard reviewer role.

        Rules (evaluated in priority order):
            1. Any finding with severity=CRITICAL and dimension=SECURITY → security_reviewer
            2. BLOCK → tech_lead
            3. CONDITIONAL_APPROVE → tech_lead
            4. APPROVE → None (no workflow needed; callers must check)

        Args:
            decision:  The decision outcome string or enum value.
            findings:  Optional list of finding dicts/objects.  May be empty.

        Returns:
            A ForgeGuard role string ('tech_lead', 'security_reviewer').
        """
        from forgeguard.services.domain.severity import SeverityClassifier  # noqa: PLC0415

        decision_val = decision.value if isinstance(decision, DecisionOutcome) else str(decision)

        # Critical security escalation takes highest priority.
        if findings:
            for f in findings:
                severity = f.get("severity") if isinstance(f, dict) else getattr(f, "severity", None)
                dimension = f.get("dimension") if isinstance(f, dict) else getattr(f, "dimension", None)
                if severity is None or dimension is None:
                    continue
                sev_str = severity.value if hasattr(severity, "value") else str(severity)
                dim_str = dimension.value if hasattr(dimension, "value") else str(dimension)
                try:
                    if SeverityClassifier.is_escalation_required(sev_str, dim_str):
                        return "security_reviewer"
                except ValueError:
                    pass

        if decision_val in (DecisionOutcome.BLOCK.value, DecisionOutcome.CONDITIONAL_APPROVE.value):
            return "tech_lead"

        return "tech_lead"  # safe default


# ---------------------------------------------------------------------------
# HTTP implementation
# ---------------------------------------------------------------------------


class ForgeWorkflowHttpAdapter(ForgeWorkflowAdapter):
    """Forge Workflow HTTP adapter with circuit breaker and dashboard fallback.

    Args:
        base_url:            Base URL of the Forge Workflow Engine API.
        api_key:             API key (X-Forge-Api-Key). Never logged.
        circuit_breaker:     Pre-configured CircuitBreaker instance.
        timeout:             HTTP request timeout in seconds.
    """

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        circuit_breaker: CircuitBreaker,
        timeout: float = _HTTP_TIMEOUT,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._cb = circuit_breaker
        self._timeout = timeout

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=self._base_url,
            headers={
                "X-Forge-Api-Key": self._api_key,
                "Content-Type": "application/json",
            },
            timeout=self._timeout,
        )

    async def trigger_workflow(
        self,
        *,
        decision_id: uuid.UUID,
        assessment_id: uuid.UUID,
        decision: str,
        reviewer_role: str,
        context: dict[str, Any],
        audit_svc: Any = None,
    ) -> dict[str, Any] | None:
        """POST /workflows/trigger.  Returns trigger response or None on failure.

        On failure, activates dashboard fallback automatically.
        """
        participant_type = _PARTICIPANT_MAP.get(reviewer_role, "reviewer")
        payload: dict[str, Any] = {
            "workflow_type": "release_review",
            "context": {
                "assessment_id": str(assessment_id),
                **context,
            },
            "participants": [
                {"role": participant_type, "required": True},
            ],
            "priority": "critical" if reviewer_role == "security_reviewer" else "normal",
            "callback_url": None,
        }

        log = logger.bind(
            assessment_id=str(assessment_id),
            decision_id=str(decision_id),
            decision=decision,
            reviewer_role=reviewer_role,
        )

        try:
            async with self._client() as client:
                response = await self._cb.call(
                    client.post("/workflows/trigger", json=payload)
                )
        except CircuitOpenError:
            log.info(
                "forge_workflow.circuit_open",
                routing_method=ROUTING_METHOD_FALLBACK,
                message="Circuit open — routing to dashboard fallback",
            )
            await self.activate_fallback(
                decision_id=decision_id,
                assessment_id=assessment_id,
                target_role=reviewer_role,
                context=context,
                reason="circuit_open",
                audit_svc=audit_svc,
            )
            return None
        except httpx.TimeoutException as exc:
            log.warning(
                "forge_workflow.trigger_timeout",
                error=str(exc),
                routing_method=ROUTING_METHOD_FALLBACK,
            )
            await self.activate_fallback(
                decision_id=decision_id,
                assessment_id=assessment_id,
                target_role=reviewer_role,
                context=context,
                reason="timeout",
                audit_svc=audit_svc,
            )
            return None
        except Exception as exc:
            log.error(
                "forge_workflow.trigger_failed",
                error=str(exc),
                error_type=type(exc).__name__,
                routing_method=ROUTING_METHOD_FALLBACK,
            )
            await self.activate_fallback(
                decision_id=decision_id,
                assessment_id=assessment_id,
                target_role=reviewer_role,
                context=context,
                reason="connection_error",
                audit_svc=audit_svc,
            )
            return None

        # HTTP 4xx — do not retry, go to fallback.
        if 400 <= response.status_code < 500:
            log.error(
                "forge_workflow.trigger_4xx",
                status_code=response.status_code,
                routing_method=ROUTING_METHOD_FALLBACK,
            )
            await self.activate_fallback(
                decision_id=decision_id,
                assessment_id=assessment_id,
                target_role=reviewer_role,
                context=context,
                reason=f"http_{response.status_code}",
                audit_svc=audit_svc,
            )
            return None

        # HTTP 5xx — retry once, then fallback.
        if response.status_code >= 500:
            log.warning(
                "forge_workflow.trigger_5xx_retrying",
                status_code=response.status_code,
            )
            try:
                async with self._client() as client:
                    response = await self._cb.call(
                        client.post("/workflows/trigger", json=payload)
                    )
            except Exception as retry_exc:
                log.error(
                    "forge_workflow.trigger_retry_failed",
                    error=str(retry_exc),
                    routing_method=ROUTING_METHOD_FALLBACK,
                )
                await self.activate_fallback(
                    decision_id=decision_id,
                    assessment_id=assessment_id,
                    target_role=reviewer_role,
                    context=context,
                    reason="5xx_retry_failed",
                    audit_svc=audit_svc,
                )
                return None

            if not response.is_success:
                await self.activate_fallback(
                    decision_id=decision_id,
                    assessment_id=assessment_id,
                    target_role=reviewer_role,
                    context=context,
                    reason=f"http_{response.status_code}_after_retry",
                    audit_svc=audit_svc,
                )
                return None

        try:
            result: dict[str, Any] = response.json()
        except Exception:
            log.error("forge_workflow.trigger_invalid_json")
            await self.activate_fallback(
                decision_id=decision_id,
                assessment_id=assessment_id,
                target_role=reviewer_role,
                context=context,
                reason="invalid_response_json",
                audit_svc=audit_svc,
            )
            return None

        workflow_id = result.get("workflow_id") or result.get("id")
        log.info(
            "forge_workflow.triggered",
            workflow_id=str(workflow_id),
            routing_method=ROUTING_METHOD_FORGE,
        )

        if audit_svc is not None:
            try:
                await audit_svc.log_event(
                    actor_id=None,
                    actor_role="system",
                    action="workflow_triggered",
                    resource_type="release_decision",
                    resource_id=decision_id,
                    after_state={
                        "workflow_id": str(workflow_id) if workflow_id else None,
                        "assessment_id": str(assessment_id),
                        "decision": decision,
                        "reviewer_role": reviewer_role,
                        "routing_method": ROUTING_METHOD_FORGE,
                    },
                )
            except Exception as audit_exc:
                log.warning("forge_workflow.audit_failed", error=str(audit_exc))

        return result

    async def get_workflow_status(self, workflow_id: str) -> dict[str, Any] | None:
        """GET /workflows/{workflow_id}/status.

        Returns the status dict, or None on 404 (treat as timed_out) or error.
        """
        try:
            async with self._client() as client:
                response = await self._cb.call(
                    client.get(f"/workflows/{workflow_id}/status")
                )
        except (CircuitOpenError, Exception) as exc:
            logger.warning(
                "forge_workflow.status_poll_failed",
                workflow_id=workflow_id,
                error=str(exc),
                error_type=type(exc).__name__,
            )
            return None

        if response.status_code == 404:
            logger.warning(
                "forge_workflow.status_404",
                workflow_id=workflow_id,
                message="Workflow not found — treating as timed_out",
            )
            return {"id": workflow_id, "status": "timed_out"}

        if not response.is_success:
            logger.warning(
                "forge_workflow.status_error",
                workflow_id=workflow_id,
                status_code=response.status_code,
            )
            return None

        try:
            return response.json()
        except Exception:
            logger.error("forge_workflow.status_invalid_json", workflow_id=workflow_id)
            return None

    async def activate_fallback(
        self,
        *,
        decision_id: uuid.UUID,
        assessment_id: uuid.UUID,
        target_role: str,
        context: dict[str, Any],
        reason: str,
        audit_svc: Any = None,
    ) -> None:
        """Record a dashboard-fallback notification.

        Emits a CRITICAL-level log and an audit record so the review requirement
        is never silently lost.  The fallback ensures reviewers can still discover
        the pending decision via the ForgeGuard dashboard.
        """
        logger.critical(
            "forge_workflow.fallback_activated",
            decision_id=str(decision_id),
            assessment_id=str(assessment_id),
            target_role=target_role,
            reason=reason,
            routing_method=ROUTING_METHOD_FALLBACK,
            message=(
                f"Forge Workflow unavailable ({reason}). "
                f"Decision {decision_id} requires manual review by {target_role} "
                "via ForgeGuard dashboard."
            ),
        )

        if audit_svc is not None:
            try:
                await audit_svc.log_event(
                    actor_id=None,
                    actor_role="system",
                    action="workflow_fallback_activated",
                    resource_type="release_decision",
                    resource_id=decision_id,
                    after_state={
                        "assessment_id": str(assessment_id),
                        "target_role": target_role,
                        "reason": reason,
                        "routing_method": ROUTING_METHOD_FALLBACK,
                        "context": context,
                    },
                )
            except Exception as audit_exc:
                logger.warning(
                    "forge_workflow.fallback_audit_failed",
                    decision_id=str(decision_id),
                    error=str(audit_exc),
                )


# ---------------------------------------------------------------------------
# Background task: trigger workflow after decision (AC-1, AC-5)
# ---------------------------------------------------------------------------


async def trigger_workflow_for_decision(
    *,
    adapter: ForgeWorkflowAdapter,
    decision_repo: Any,
    decision_id: uuid.UUID,
    assessment_id: uuid.UUID,
    decision: str,
    findings: list[Any],
    context: dict[str, Any],
    audit_svc: Any = None,
) -> None:
    """Background task: trigger Forge Workflow for a CONDITIONAL_APPROVE or BLOCK decision.

    Only runs for CONDITIONAL_APPROVE and BLOCK.  APPROVE decisions are audited
    but do not require a workflow.  Updates release_decisions with workflow_id,
    routing_method, and workflow_timeout_at.
    """
    if decision not in (DecisionOutcome.CONDITIONAL_APPROVE.value, DecisionOutcome.BLOCK.value):
        logger.debug(
            "forge_workflow.skipped_approve",
            decision_id=str(decision_id),
            decision=decision,
        )
        if audit_svc is not None:
            try:
                await audit_svc.log_event(
                    actor_id=None,
                    actor_role="system",
                    action="workflow_auto_approved",
                    resource_type="release_decision",
                    resource_id=decision_id,
                    after_state={"decision": decision, "routing_method": "none"},
                )
            except Exception:
                pass
        return

    reviewer_role = ForgeWorkflowAdapter.determine_reviewer_role(decision, findings=findings)

    result = await adapter.trigger_workflow(
        decision_id=decision_id,
        assessment_id=assessment_id,
        decision=decision,
        reviewer_role=reviewer_role,
        context=context,
        audit_svc=audit_svc,
    )

    routing_method = ROUTING_METHOD_FORGE if result else ROUTING_METHOD_FALLBACK
    workflow_id: str | None = None
    if result:
        workflow_id = str(result.get("workflow_id") or result.get("id") or "")

    timeout_at = datetime.now(timezone.utc) + timedelta(hours=_WORKFLOW_TIMEOUT_HOURS)

    try:
        await decision_repo.update_workflow_status(
            decision_id,
            workflow_id=workflow_id,
            routing_method=routing_method,
            workflow_status="pending" if result else "fallback",
            workflow_timeout_at=timeout_at,
        )
    except Exception as exc:
        logger.error(
            "forge_workflow.update_workflow_status_failed",
            decision_id=str(decision_id),
            error=str(exc),
        )


# ---------------------------------------------------------------------------
# Background task: poll active workflows (AC-4)
# ---------------------------------------------------------------------------


async def poll_active_workflows(
    *,
    adapter: ForgeWorkflowAdapter,
    decision_repo: Any,
    audit_svc: Any = None,
) -> None:
    """Poll Forge Workflow status for all non-terminal release decisions.

    Called every 60 seconds by the scheduler.  For each active workflow:
      - Fetches current status from GET /workflows/{id}/status
      - On terminal state (approved, rejected, timed_out): updates release_decisions
      - On 404: marks as timed_out and activates dashboard fallback
      - On timeout_at exceeded: marks as timed_out and activates dashboard fallback
    """
    try:
        active = await decision_repo.list_active_workflows()
    except Exception as exc:
        logger.error("forge_workflow.poll_list_failed", error=str(exc))
        return

    if not active:
        return

    logger.debug("forge_workflow.polling", count=len(active))

    now = datetime.now(timezone.utc)

    for row in active:
        decision_id = row.get("id")
        workflow_id = row.get("workflow_id")
        timeout_at = row.get("workflow_timeout_at")

        if not workflow_id:
            continue

        # Check 24-hour timeout.
        if timeout_at is not None:
            if hasattr(timeout_at, "tzinfo") and timeout_at.tzinfo is None:
                timeout_at = timeout_at.replace(tzinfo=timezone.utc)
            if now > timeout_at:
                logger.warning(
                    "forge_workflow.timed_out",
                    decision_id=str(decision_id),
                    workflow_id=str(workflow_id),
                )
                try:
                    await decision_repo.update_workflow_status(
                        decision_id,
                        workflow_status="timed_out",
                    )
                except Exception:
                    pass
                if audit_svc is not None:
                    try:
                        await audit_svc.log_event(
                            actor_id=None,
                            actor_role="system",
                            action="workflow_timed_out",
                            resource_type="release_decision",
                            resource_id=decision_id,
                            after_state={
                                "workflow_id": str(workflow_id),
                                "routing_method": ROUTING_METHOD_FALLBACK,
                            },
                        )
                    except Exception:
                        pass
                await adapter.activate_fallback(
                    decision_id=decision_id,
                    assessment_id=row.get("release_assessment_id", decision_id),
                    target_role="platform_admin",
                    context={"workflow_id": str(workflow_id)},
                    reason="timeout_24h",
                    audit_svc=audit_svc,
                )
                continue

        status_resp = await adapter.get_workflow_status(str(workflow_id))
        if status_resp is None:
            continue

        new_status = status_resp.get("status")
        if new_status not in _TERMINAL_STATUSES and new_status not in ("pending", "in_review"):
            continue

        if new_status in _TERMINAL_STATUSES:
            decided_by = status_resp.get("decided_by")
            decided_at_raw = status_resp.get("decided_at")

            # Validate approver role if provided (edge case: wrong role approved).
            required_role = row.get("routing_method")  # stored for reference
            if decided_by and isinstance(decided_by, dict):
                approver_role = decided_by.get("role", "")
                if (
                    approver_role
                    and required_role
                    and approver_role not in ("reviewer", "security_gate", "admin_reviewer", required_role)
                ):
                    logger.warning(
                        "forge_workflow.approver_role_mismatch",
                        decision_id=str(decision_id),
                        approver_role=approver_role,
                        required_role=required_role,
                    )

            try:
                await decision_repo.update_workflow_status(
                    decision_id,
                    workflow_status=new_status,
                )
            except Exception as exc:
                logger.error(
                    "forge_workflow.update_terminal_status_failed",
                    decision_id=str(decision_id),
                    error=str(exc),
                )
                continue

            action = (
                "workflow_approved" if new_status == "approved"
                else "workflow_rejected" if new_status == "rejected"
                else "workflow_timed_out"
            )
            if audit_svc is not None:
                try:
                    await audit_svc.log_event(
                        actor_id=None,
                        actor_role="system",
                        action=action,
                        resource_type="release_decision",
                        resource_id=decision_id,
                        after_state={
                            "workflow_id": str(workflow_id),
                            "status": new_status,
                            "decided_by": decided_by,
                            "decided_at": decided_at_raw,
                        },
                    )
                except Exception:
                    pass

            logger.info(
                "forge_workflow.status_updated",
                decision_id=str(decision_id),
                workflow_id=str(workflow_id),
                status=new_status,
            )

            if new_status == "timed_out":
                await adapter.activate_fallback(
                    decision_id=decision_id,
                    assessment_id=row.get("release_assessment_id", decision_id),
                    target_role="platform_admin",
                    context={"workflow_id": str(workflow_id)},
                    reason="workflow_engine_timed_out",
                    audit_svc=audit_svc,
                )
