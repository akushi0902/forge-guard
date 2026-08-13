"""ContextAssembler: orchestrates retrievers for the AI agent (WO-067).

Maps classified intent categories to retriever combinations, executes
retrievers concurrently via asyncio.gather with per-retriever timeout
handling, and assembles results into a structured ContextBundle.

Intent-to-retriever mapping:
    health_score  -> [health_retriever]
    findings      -> [findings_retriever, policy_retriever]
    remediation   -> [findings_retriever, policy_retriever]
    release_status -> [release_retriever, health_retriever]
    policy_rules  -> [policy_retriever]
    general_help  -> [] (template-only path)
"""

from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import structlog

from forgeguard.services.agent.knowledge_base.base_retriever import RetrievalContext
from forgeguard.services.agent.knowledge_base.findings_retriever import FindingsRetriever
from forgeguard.services.agent.knowledge_base.health_retriever import HealthRetriever
from forgeguard.services.agent.knowledge_base.policy_retriever import PolicyRetriever
from forgeguard.services.agent.knowledge_base.release_retriever import ReleaseRetriever
from forgeguard.services.agent.knowledge_base.service_access_resolver import (
    ServiceAccessResolver,
)
from forgeguard.services.agent.intent_classifier import IntentCategory

logger = structlog.get_logger(__name__)

# Per-retriever query timeout in seconds. A retriever that exceeds this limit
# is cancelled and contributes a degraded context to the bundle.
_RETRIEVER_TIMEOUT_SECONDS = 1.0

# Total assembly timeout budget (2 seconds per AC-8).
_ASSEMBLY_TIMEOUT_SECONDS = 2.0


@dataclass
class ContextBundle:
    """Assembled context for a single agent query.

    Attributes:
        service_id:       The queried service UUID (or None for general queries).
        intent:           Classified query intent.
        health:           Health retrieval result (may be empty or degraded).
        findings:         Findings retrieval result (may be empty or degraded).
        policy:           Policy retrieval result (may be empty or degraded).
        release:          Release retrieval result (may be empty or degraded).
        is_degraded:      True if at least one retriever failed or timed out.
        is_unauthorized:  True if the user lacks access to the requested service.
        unauthorized_message: Human-readable note when is_unauthorized is True.
        retrieval_time_ms: Total wall-clock time for context assembly in ms.
        assembled_at:     UTC timestamp of when the bundle was assembled.
        metadata:         Extra metadata for debugging (timeouts, partial data).
    """

    service_id: uuid.UUID | None = None
    intent: str = ""
    health: RetrievalContext | None = None
    findings: RetrievalContext | None = None
    policy: RetrievalContext | None = None
    release: RetrievalContext | None = None
    is_degraded: bool = False
    is_unauthorized: bool = False
    unauthorized_message: str = ""
    retrieval_time_ms: float = 0.0
    assembled_at: datetime = field(
        default_factory=lambda: datetime.now(tz=timezone.utc)
    )
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_prompt_dict(self) -> dict[str, Any]:
        """Convert the bundle to a flat dict suitable for prompt injection."""
        result: dict[str, Any] = {
            "intent": self.intent,
            "service_id": str(self.service_id) if self.service_id else None,
            "assembled_at": self.assembled_at.isoformat(),
            "retrieval_time_ms": round(self.retrieval_time_ms, 1),
            "is_degraded": self.is_degraded,
            "is_unauthorized": self.is_unauthorized,
        }

        if self.is_unauthorized:
            result["unauthorized_message"] = self.unauthorized_message
            return result

        if self.health:
            result["health_context"] = (
                self.health.data if not self.health.is_empty and not self.health.is_degraded
                else {"status": "unavailable", "reason": self.health.empty_reason or self.health.degraded_reason}
            )

        if self.findings:
            result["findings_context"] = (
                self.findings.data if not self.findings.is_empty and not self.findings.is_degraded
                else {"status": "unavailable", "reason": self.findings.empty_reason or self.findings.degraded_reason}
            )

        if self.policy:
            result["policy_context"] = (
                self.policy.data if not self.policy.is_empty and not self.policy.is_degraded
                else {"status": "unavailable", "reason": self.policy.empty_reason or self.policy.degraded_reason}
            )

        if self.release:
            result["release_context"] = (
                self.release.data if not self.release.is_empty and not self.release.is_degraded
                else {"status": "unavailable", "reason": self.release.empty_reason or self.release.degraded_reason}
            )

        return result


class ContextAssembler:
    """Orchestrates retriever execution for a classified agent query.

    Instantiate once; reuse across requests.
    """

    def __init__(self, pool: Any) -> None:
        self._pool = pool
        self._health = HealthRetriever(pool)
        self._findings = FindingsRetriever(pool)
        self._policy = PolicyRetriever(pool)
        self._release = ReleaseRetriever(pool)
        self._access = ServiceAccessResolver(pool)

    async def assemble(
        self,
        *,
        user_id: uuid.UUID,
        actor_role: str,
        intent: IntentCategory,
        service_id: uuid.UUID | None = None,
        query_params: dict[str, Any] | None = None,
    ) -> ContextBundle:
        """Assemble a ContextBundle for the given query.

        Args:
            user_id:      Authenticated user UUID.
            actor_role:   User's current role.
            intent:       Classified query intent.
            service_id:   Optional target service UUID. Required for all
                          intents except GENERAL_HELP.
            query_params: Optional retriever-specific filters forwarded to
                          the appropriate retrievers.

        Returns:
            ContextBundle with data from all relevant retrievers.
        """
        t0 = time.monotonic()

        # ── General help: no DB retrieval needed ──────────────────────────
        if intent == IntentCategory.GENERAL_HELP or service_id is None:
            return ContextBundle(
                service_id=service_id,
                intent=intent.value,
                retrieval_time_ms=(time.monotonic() - t0) * 1000,
                metadata={"retriever_set": []},
            )

        # ── Service ownership check ───────────────────────────────────────
        authorized = await self._access.is_authorized(
            user_id, actor_role, service_id
        )
        if not authorized:
            logger.info(
                "context_assembler.access_denied",
                user_id=str(user_id),
                service_id=str(service_id),
                intent=intent.value,
            )
            return ContextBundle(
                service_id=service_id,
                intent=intent.value,
                is_unauthorized=True,
                unauthorized_message=(
                    f"Service {service_id} is not accessible to your account. "
                    "Contact your Platform Admin for service access."
                ),
                retrieval_time_ms=(time.monotonic() - t0) * 1000,
            )

        # ── Select retrievers based on intent ─────────────────────────────
        retriever_plan = _INTENT_RETRIEVER_MAP.get(intent, [])

        if not retriever_plan:
            return ContextBundle(
                service_id=service_id,
                intent=intent.value,
                retrieval_time_ms=(time.monotonic() - t0) * 1000,
                metadata={"retriever_set": []},
            )

        # ── Execute retrievers concurrently ───────────────────────────────
        tasks = [
            _timed_retrieve(
                retriever_name,
                retriever_fn,
                user_id,
                service_id,
                query_params,
            )
            for retriever_name, retriever_fn in (
                (name, self._get_retriever(name))
                for name in retriever_plan
            )
        ]

        results: list[tuple[str, RetrievalContext]] = await asyncio.gather(*tasks)

        # ── Assemble bundle ───────────────────────────────────────────────
        bundle = ContextBundle(
            service_id=service_id,
            intent=intent.value,
            retrieval_time_ms=(time.monotonic() - t0) * 1000,
            metadata={"retriever_set": retriever_plan},
        )

        for domain_name, ctx in results:
            if ctx.is_degraded:
                bundle.is_degraded = True
            if domain_name == "health":
                bundle.health = ctx
            elif domain_name == "findings":
                bundle.findings = ctx
            elif domain_name == "policy":
                bundle.policy = ctx
            elif domain_name == "release":
                bundle.release = ctx

        return bundle

    def _get_retriever(self, name: str) -> Any:
        return {
            "health": self._health,
            "findings": self._findings,
            "policy": self._policy,
            "release": self._release,
        }[name]


# ---------------------------------------------------------------------------
# Intent → retriever mapping
# ---------------------------------------------------------------------------

# Keys are IntentCategory enum values; values are lists of retriever domain
# names in the order they will be requested (execution is concurrent).
_INTENT_RETRIEVER_MAP: dict[IntentCategory, list[str]] = {
    IntentCategory.HEALTH_SCORE: ["health"],
    IntentCategory.FINDINGS: ["findings", "policy"],
    IntentCategory.REMEDIATION: ["findings", "policy"],
    IntentCategory.RELEASE_STATUS: ["release", "health"],
    IntentCategory.POLICY_RULES: ["policy"],
    IntentCategory.GENERAL_HELP: [],
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _timed_retrieve(
    domain_name: str,
    retriever: Any,
    user_id: uuid.UUID,
    service_id: uuid.UUID,
    query_params: dict[str, Any] | None,
) -> tuple[str, RetrievalContext]:
    """Run a retriever with a per-query timeout.

    Returns a (domain_name, RetrievalContext) tuple.  On timeout or any
    exception the returned context is marked as degraded so the assembler
    can still build a partial bundle.
    """
    try:
        ctx = await asyncio.wait_for(
            retriever.retrieve(user_id, service_id, query_params),
            timeout=_RETRIEVER_TIMEOUT_SECONDS,
        )
        return domain_name, ctx
    except asyncio.TimeoutError:
        logger.warning(
            "context_assembler.retriever_timeout",
            domain=domain_name,
            service_id=str(service_id),
            timeout=_RETRIEVER_TIMEOUT_SECONDS,
        )
        return domain_name, RetrievalContext(
            domain=domain_name,
            is_degraded=True,
            degraded_reason=(
                f"{domain_name} retriever timed out after "
                f"{_RETRIEVER_TIMEOUT_SECONDS}s — partial context returned."
            ),
        )
    except Exception as exc:  # noqa: BLE001
        logger.error(
            "context_assembler.retriever_error",
            domain=domain_name,
            service_id=str(service_id),
            error=str(exc),
        )
        return domain_name, RetrievalContext(
            domain=domain_name,
            is_degraded=True,
            degraded_reason=f"{domain_name} retriever raised an error: {exc}",
        )
