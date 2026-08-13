"""HealthRetriever: optimised single-query health context assembly (WO-067).

Queries SERVICES ⟶ ASSESSMENTS ⟶ ASSESSMENT_SCORES with a single JOIN to
return:
    - overall health score
    - dimension scores (JSONB)
    - finding counts by severity
    - evaluation timestamp

Uses only the latest completed health_check assessment for the service.
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

# Single optimised query: latest completed health assessment + its score.
# Sub-select ranks assessments by created_at DESC to guarantee "latest".
_HEALTH_QUERY = """
SELECT
    s.id        AS service_id,
    s.name      AS service_name,
    a.id        AS assessment_id,
    a.created_at AS evaluated_at,
    a.status    AS assessment_status,
    sc.overall_score,
    sc.dimension_scores,
    sc.weights_used
FROM services s
JOIN assessments a
    ON a.service_id = s.id
    AND a.assessment_type = 'health_check'
    AND a.status = 'completed'
JOIN assessment_scores sc
    ON sc.assessment_id = a.id
    AND sc.score_type = 'health'
WHERE
    s.id = $1
    AND s.deleted_at IS NULL
ORDER BY a.created_at DESC
LIMIT 1
"""

# Count open findings by severity for the latest assessment (same assessment_id
# constraint applied after fetching the latest row above).
_FINDING_COUNTS_QUERY = """
SELECT
    severity,
    COUNT(*) AS cnt
FROM findings
WHERE
    assessment_id = $1
    AND status NOT IN ('exception_granted')
GROUP BY severity
"""


class HealthRetriever(BaseRetriever):
    """Retrieve health score context for the AI agent."""

    async def retrieve(
        self,
        user_id: uuid.UUID,
        service_id: uuid.UUID,
        query_params: dict[str, Any] | None = None,
    ) -> RetrievalContext:
        """Return the latest health assessment context for *service_id*.

        Args:
            user_id:      Authenticated user (not used for filtering here;
                          caller already verified ownership via
                          ServiceAccessResolver).
            service_id:   Target service UUID.
            query_params: Unused — kept for interface consistency.

        Returns:
            RetrievalContext with ``domain="health"``.
        """
        t0 = time.monotonic()
        try:
            async with self._pool.acquire() as conn:
                row = await conn.fetchrow(_HEALTH_QUERY, service_id)

                if row is None:
                    return RetrievalContext(
                        domain="health",
                        is_empty=True,
                        empty_reason=(
                            "No completed health assessment found for this service. "
                            "The service may be newly registered or the latest "
                            "assessment may still be in progress."
                        ),
                        retrieval_time_ms=(time.monotonic() - t0) * 1000,
                    )

                assessment_id = row["assessment_id"]
                severity_rows = await conn.fetch(
                    _FINDING_COUNTS_QUERY, assessment_id
                )

            finding_counts = {r["severity"]: r["cnt"] for r in severity_rows}

            dimension_scores: dict[str, Any] = row["dimension_scores"] or {}

            data: dict[str, Any] = {
                "service_id": str(service_id),
                "service_name": row["service_name"],
                "assessment_id": str(assessment_id),
                "overall_score": (
                    float(row["overall_score"])
                    if row["overall_score"] is not None
                    else None
                ),
                "dimension_scores": dimension_scores,
                "finding_counts_by_severity": {
                    "critical": finding_counts.get("critical", 0),
                    "high": finding_counts.get("high", 0),
                    "medium": finding_counts.get("medium", 0),
                    "low": finding_counts.get("low", 0),
                },
                "evaluated_at": (
                    row["evaluated_at"].isoformat()
                    if row["evaluated_at"] is not None
                    else None
                ),
                "assessment_status": row["assessment_status"],
            }

            return RetrievalContext(
                domain="health",
                data=data,
                retrieval_time_ms=(time.monotonic() - t0) * 1000,
            )

        except Exception as exc:  # noqa: BLE001
            elapsed = (time.monotonic() - t0) * 1000
            logger.error(
                "health_retriever.query_failed",
                service_id=str(service_id),
                error=str(exc),
            )
            return RetrievalContext(
                domain="health",
                is_degraded=True,
                degraded_reason=f"Health retrieval failed: {exc}",
                retrieval_time_ms=elapsed,
            )
