"""PolicyRetriever: policy rule context for the AI agent (WO-067).

Queries POLICIES JOIN POLICY_RULES for active rules, supporting:
    - filter by dimension (returns all rules in that dimension)
    - filter by specific rule_id (for explaining why a specific finding exists)
    - full active rule-set when no filter is provided (up to 50 rules)

Returns rule name, description, threshold_config, severity, weight, and
dimension — everything the agent needs to explain why a violation was flagged.
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

# Base query for policy rules joined with their parent policy.
_POLICY_RULES_BASE = """
SELECT
    pr.id            AS rule_id,
    pr.name          AS rule_name,
    pr.rule_type,
    pr.threshold_config,
    pr.severity,
    pr.weight,
    pr.is_active     AS rule_is_active,
    p.id             AS policy_id,
    p.name           AS policy_name,
    p.dimension,
    p.description    AS policy_description,
    p.version        AS policy_version,
    p.is_active      AS policy_is_active
FROM policy_rules pr
JOIN policies p ON p.id = pr.policy_id
WHERE
    pr.is_active = true
    AND pr.deleted_at IS NULL
    AND p.is_active = true
    AND p.deleted_at IS NULL
"""


class PolicyRetriever(BaseRetriever):
    """Retrieve policy rule definitions for the AI agent."""

    async def retrieve(
        self,
        user_id: uuid.UUID,
        service_id: uuid.UUID,
        query_params: dict[str, Any] | None = None,
    ) -> RetrievalContext:
        """Return active policy rules, optionally filtered.

        Args:
            user_id:      Authenticated user (ownership already verified).
            service_id:   Target service UUID. Policies may be service-scoped
                          (service_id = X) or global (service_id IS NULL);
                          both are returned.
            query_params: Optional filters:
                - ``dimension`` (str): return only rules for this dimension.
                - ``rule_id`` (str | UUID): return only the specific rule
                  (used when explaining a finding to the user).

        Returns:
            RetrievalContext with ``domain="policy"``.
        """
        t0 = time.monotonic()
        params = query_params or {}
        dimension = params.get("dimension")
        rule_id_raw = params.get("rule_id")

        try:
            rule_id: uuid.UUID | None = None
            if rule_id_raw:
                try:
                    rule_id = uuid.UUID(str(rule_id_raw))
                except (ValueError, AttributeError):
                    rule_id = None

            sql_parts = [_POLICY_RULES_BASE]
            sql_params: list[Any] = []
            idx = 1

            # Service scope: return rules that apply to this service OR global
            # rules (service_id IS NULL).
            sql_parts.append(f"AND (p.service_id = ${idx} OR p.service_id IS NULL)")
            sql_params.append(service_id)
            idx += 1

            if rule_id is not None:
                sql_parts.append(f"AND pr.id = ${idx}")
                sql_params.append(rule_id)
                idx += 1
            elif dimension:
                sql_parts.append(f"AND p.dimension = ${idx}")
                sql_params.append(dimension)
                idx += 1

            sql_parts.append("ORDER BY p.dimension, pr.severity, pr.name")
            sql_parts.append("LIMIT 50")

            sql = "\n".join(sql_parts)

            async with self._pool.acquire() as conn:
                rows = await conn.fetch(sql, *sql_params)

            if not rows:
                return RetrievalContext(
                    domain="policy",
                    is_empty=True,
                    empty_reason=(
                        "No active policy rules found"
                        + (f" for dimension={dimension}" if dimension else "")
                        + (f" with rule_id={rule_id}" if rule_id else "")
                        + ". Ensure at least one policy with active rules is "
                        "configured for this service."
                    ),
                    retrieval_time_ms=(time.monotonic() - t0) * 1000,
                )

            rules_list = []
            for row in rows:
                rules_list.append({
                    "rule_id": str(row["rule_id"]),
                    "rule_name": row["rule_name"],
                    "rule_type": row["rule_type"],
                    "threshold_config": dict(row["threshold_config"])
                    if row["threshold_config"]
                    else {},
                    "severity": row["severity"],
                    "weight": float(row["weight"]) if row["weight"] is not None else None,
                    "policy_id": str(row["policy_id"]),
                    "policy_name": row["policy_name"],
                    "dimension": row["dimension"],
                    "policy_description": row["policy_description"],
                    "policy_version": row["policy_version"],
                })

            # Group rules by dimension for easier LLM consumption.
            by_dimension: dict[str, list[dict[str, Any]]] = {}
            for rule in rules_list:
                dim = rule["dimension"]
                by_dimension.setdefault(dim, []).append(rule)

            data: dict[str, Any] = {
                "service_id": str(service_id),
                "total_rules": len(rules_list),
                "filters_applied": {
                    "dimension": dimension,
                    "rule_id": str(rule_id) if rule_id else None,
                },
                "rules_by_dimension": by_dimension,
                "rules": rules_list,
            }

            return RetrievalContext(
                domain="policy",
                data=data,
                retrieval_time_ms=(time.monotonic() - t0) * 1000,
            )

        except Exception as exc:  # noqa: BLE001
            elapsed = (time.monotonic() - t0) * 1000
            logger.error(
                "policy_retriever.query_failed",
                service_id=str(service_id),
                error=str(exc),
            )
            return RetrievalContext(
                domain="policy",
                is_degraded=True,
                degraded_reason=f"Policy retrieval failed: {exc}",
                retrieval_time_ms=elapsed,
            )
