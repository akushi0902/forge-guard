"""FindingsRetriever: findings + remediation context for the AI agent (WO-067).

Queries FINDINGS LEFT JOIN REMEDIATION_RECOMMENDATIONS filtered by service_id,
with optional severity/dimension filters, sorted by severity DESC (critical
first), limited to top 20. Also supports text-based title search for edge cases
where the user describes a finding by text.
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

# Severity ordering for DESC sort (critical=4, high=3, medium=2, low=1).
_SEVERITY_ORDER = """
CASE f.severity
    WHEN 'critical' THEN 4
    WHEN 'high'     THEN 3
    WHEN 'medium'   THEN 2
    WHEN 'low'      THEN 1
    ELSE 0
END
"""

# Base query: findings left-joined with their latest remediation recommendation.
# The sub-select on rr picks the most recently created recommendation to avoid
# row multiplication when multiple recommendations exist for a finding.
_FINDINGS_BASE = """
SELECT
    f.id               AS finding_id,
    f.assessment_id,
    f.service_id,
    f.policy_rule_id,
    f.severity,
    f.dimension,
    f.status,
    f.title,
    f.description,
    f.confidence_score AS finding_confidence,
    f.created_at       AS finding_created_at,
    f.resolved_at,
    rr.id              AS recommendation_id,
    rr.recommendation_text,
    rr.implementation_guide,
    rr.business_impact,
    rr.confidence_score AS recommendation_confidence,
    rr.source          AS recommendation_source
FROM findings f
LEFT JOIN LATERAL (
    SELECT *
    FROM remediation_recommendations
    WHERE finding_id = f.id
    ORDER BY created_at DESC
    LIMIT 1
) rr ON true
WHERE
    f.service_id = $1
    AND f.status NOT IN ('exception_granted')
"""


def _build_findings_query(
    severity: str | None,
    dimension: str | None,
    search_text: str | None,
) -> tuple[str, list[Any], int]:
    """Build a parameterised findings query with optional filters.

    Returns:
        (sql_string, params_list, next_param_index)
    """
    params: list[Any] = []
    idx = 2  # $1 is service_id (bound externally)
    extra_clauses: list[str] = []

    if severity:
        extra_clauses.append(f"AND f.severity = ${idx}")
        params.append(severity)
        idx += 1

    if dimension:
        extra_clauses.append(f"AND f.dimension = ${idx}")
        params.append(dimension)
        idx += 1

    if search_text:
        extra_clauses.append(f"AND f.title ILIKE ${idx}")
        params.append(f"%{search_text}%")
        idx += 1

    clauses = "\n    ".join(extra_clauses)
    sql = f"""
{_FINDINGS_BASE}
    {clauses}
ORDER BY {_SEVERITY_ORDER} DESC, f.created_at DESC
LIMIT 20
"""
    return sql, params, idx


class FindingsRetriever(BaseRetriever):
    """Retrieve findings and remediation recommendations for the AI agent."""

    async def retrieve(
        self,
        user_id: uuid.UUID,
        service_id: uuid.UUID,
        query_params: dict[str, Any] | None = None,
    ) -> RetrievalContext:
        """Return top-20 findings with remediation context for *service_id*.

        Args:
            user_id:      Authenticated user (ownership already verified).
            service_id:   Target service UUID.
            query_params: Optional filters:
                - ``severity`` (str): filter to a specific severity level.
                - ``dimension`` (str): filter to a specific engineering dimension.
                - ``search_text`` (str): free-text match against finding title.

        Returns:
            RetrievalContext with ``domain="findings"``.
        """
        t0 = time.monotonic()
        params = query_params or {}
        severity = params.get("severity")
        dimension = params.get("dimension")
        search_text = params.get("search_text")

        try:
            sql, extra_params, _ = _build_findings_query(severity, dimension, search_text)
            full_params = [service_id, *extra_params]

            async with self._pool.acquire() as conn:
                rows = await conn.fetch(sql, *full_params)

            if not rows:
                return RetrievalContext(
                    domain="findings",
                    is_empty=True,
                    empty_reason=(
                        "No open findings found for this service"
                        + (f" matching severity={severity}" if severity else "")
                        + (f" in dimension={dimension}" if dimension else "")
                        + ". The service may be fully compliant or have no "
                        "completed assessments yet."
                    ),
                    retrieval_time_ms=(time.monotonic() - t0) * 1000,
                )

            findings_list = []
            for row in rows:
                finding: dict[str, Any] = {
                    "finding_id": str(row["finding_id"]),
                    "severity": row["severity"],
                    "dimension": row["dimension"],
                    "status": row["status"],
                    "title": row["title"],
                    "description": row["description"],
                    "created_at": (
                        row["finding_created_at"].isoformat()
                        if row["finding_created_at"]
                        else None
                    ),
                    "resolved_at": (
                        row["resolved_at"].isoformat()
                        if row["resolved_at"]
                        else None
                    ),
                    "policy_rule_id": str(row["policy_rule_id"]) if row["policy_rule_id"] else None,
                    "remediation": None,
                }

                if row["recommendation_id"] is not None:
                    finding["remediation"] = {
                        "recommendation_id": str(row["recommendation_id"]),
                        "recommendation_text": row["recommendation_text"],
                        "implementation_guide": row["implementation_guide"],
                        "business_impact": row["business_impact"],
                        "confidence_score": (
                            float(row["recommendation_confidence"])
                            if row["recommendation_confidence"] is not None
                            else None
                        ),
                        "source": row["recommendation_source"],
                    }
                else:
                    finding["remediation"] = {
                        "recommendation_text": (
                            "Remediation guidance is pending for this finding. "
                            "Please check back shortly or consult the policy rule "
                            "documentation for manual remediation steps."
                        ),
                        "source": "pending",
                    }

                findings_list.append(finding)

            data: dict[str, Any] = {
                "service_id": str(service_id),
                "total_returned": len(findings_list),
                "filters_applied": {
                    "severity": severity,
                    "dimension": dimension,
                    "search_text": search_text,
                },
                "findings": findings_list,
            }

            return RetrievalContext(
                domain="findings",
                data=data,
                retrieval_time_ms=(time.monotonic() - t0) * 1000,
            )

        except Exception as exc:  # noqa: BLE001
            elapsed = (time.monotonic() - t0) * 1000
            logger.error(
                "findings_retriever.query_failed",
                service_id=str(service_id),
                error=str(exc),
            )
            return RetrievalContext(
                domain="findings",
                is_degraded=True,
                degraded_reason=f"Findings retrieval failed: {exc}",
                retrieval_time_ms=elapsed,
            )
