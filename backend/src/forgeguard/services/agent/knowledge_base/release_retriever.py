"""ReleaseRetriever: release assessment and decision context (WO-067).

Queries RELEASE_ASSESSMENTS JOIN RELEASE_DECISIONS for the most recent
assessment of a service. Returns:
    - risk score
    - decision (APPROVE / CONDITIONAL_APPROVE / BLOCK / pending)
    - escalation status
    - reviewer identity (role, not PII)
    - decision timestamp
"""

from __future__ import annotations

import time
import uuid
from typing import Any

import structlog

from forgeguard.services.agent.knowledge_base.base_retriever import (
    BaseRetriever,
    RetrievalContext,
)

logger = structlog.get_logger(__name__)

# Latest release assessment for a service with its decision (if any).
# We use a LEFT JOIN on release_decisions so pending assessments (no decision
# yet) are still returned — the caller surfaces a "pending review" message.
_RELEASE_QUERY = """
SELECT
    ra.id              AS release_assessment_id,
    ra.commit_sha,
    ra.pr_reference,
    ra.trigger_type,
    ra.status          AS assessment_status,
    ra.created_at      AS assessment_created_at,
    ra.completed_at    AS assessment_completed_at,
    rd.id              AS decision_id,
    rd.decision,
    rd.health_score_at_decision,
    rd.risk_score_at_decision,
    rd.decided_by_role,
    rd.was_escalated,
    rd.rationale,
    rd.comment,
    rd.created_at      AS decision_created_at
FROM release_assessments ra
LEFT JOIN release_decisions rd
    ON rd.release_assessment_id = ra.id
WHERE
    ra.service_id = $1
ORDER BY ra.created_at DESC
LIMIT 1
"""


class ReleaseRetriever(BaseRetriever):
    """Retrieve release assessment context for the AI agent."""

    async def retrieve(
        self,
        user_id: uuid.UUID,
        service_id: uuid.UUID,
        query_params: dict[str, Any] | None = None,
    ) -> RetrievalContext:
        """Return the most recent release assessment context for *service_id*.

        Args:
            user_id:      Authenticated user (ownership already verified).
            service_id:   Target service UUID.
            query_params: Unused — kept for interface consistency.

        Returns:
            RetrievalContext with ``domain="release"``.
        """
        t0 = time.monotonic()

        try:
            async with self._pool.acquire() as conn:
                row = await conn.fetchrow(_RELEASE_QUERY, service_id)

            if row is None:
                return RetrievalContext(
                    domain="release",
                    is_empty=True,
                    empty_reason=(
                        "No release assessment found for this service. "
                        "Submit a commit SHA or PR reference via the Release "
                        "Guardian to initiate a release readiness check."
                    ),
                    retrieval_time_ms=(time.monotonic() - t0) * 1000,
                )

            decision_data: dict[str, Any] | None = None
            if row["decision_id"] is not None:
                decision_data = {
                    "decision_id": str(row["decision_id"]),
                    "decision": row["decision"],
                    "health_score_at_decision": (
                        float(row["health_score_at_decision"])
                        if row["health_score_at_decision"] is not None
                        else None
                    ),
                    "risk_score_at_decision": (
                        float(row["risk_score_at_decision"])
                        if row["risk_score_at_decision"] is not None
                        else None
                    ),
                    "decided_by_role": row["decided_by_role"],
                    "was_escalated": row["was_escalated"],
                    "rationale": row["rationale"],
                    "comment": row["comment"],
                    "decision_created_at": (
                        row["decision_created_at"].isoformat()
                        if row["decision_created_at"]
                        else None
                    ),
                }
            else:
                # Assessment exists but no decision has been made yet.
                decision_data = {
                    "decision": "pending",
                    "message": (
                        "This release assessment has not received a decision yet. "
                        "The assessment is awaiting reviewer approval."
                    ),
                }

            data: dict[str, Any] = {
                "service_id": str(service_id),
                "release_assessment_id": str(row["release_assessment_id"]),
                "commit_sha": row["commit_sha"],
                "pr_reference": row["pr_reference"],
                "trigger_type": row["trigger_type"],
                "assessment_status": row["assessment_status"],
                "assessment_created_at": (
                    row["assessment_created_at"].isoformat()
                    if row["assessment_created_at"]
                    else None
                ),
                "assessment_completed_at": (
                    row["assessment_completed_at"].isoformat()
                    if row["assessment_completed_at"]
                    else None
                ),
                "decision": decision_data,
            }

            return RetrievalContext(
                domain="release",
                data=data,
                retrieval_time_ms=(time.monotonic() - t0) * 1000,
            )

        except Exception as exc:  # noqa: BLE001
            elapsed = (time.monotonic() - t0) * 1000
            logger.error(
                "release_retriever.query_failed",
                service_id=str(service_id),
                error=str(exc),
            )
            return RetrievalContext(
                domain="release",
                is_degraded=True,
                degraded_reason=f"Release retrieval failed: {exc}",
                retrieval_time_ms=elapsed,
            )
