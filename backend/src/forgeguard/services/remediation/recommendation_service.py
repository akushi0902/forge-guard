"""RecommendationService: orchestrates finding lookup, generation, persistence, and audit (WO-058, WO-060).

Idempotent by design: if a recommendation already exists for a finding and
force_refresh is False, the cached recommendation is returned immediately without
re-invoking the LLM.

WO-060 adds a DB-backed ResponseCache layer checked before the LLM provider.
Cache hits are keyed by (dimension, severity, policy_rule_id, template_version)
so identical findings across services share one cached result.

Raises:
    NotFoundError: Finding does not exist.
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import TYPE_CHECKING, Any

import structlog

from forgeguard.core.exceptions import NotFoundError
from forgeguard.data.repositories.findings import FindingRepository
from forgeguard.data.repositories.remediation_recommendation_repository import (
    RemediationRecommendationRepository,
)
from forgeguard.services.ai_engine.recommendation_generator import RecommendationGenerator
from forgeguard.services.audit import AuditService

if TYPE_CHECKING:
    from forgeguard.services.ai_engine.response_cache import DBResponseCache

logger = structlog.get_logger(__name__)

_RESOURCE_TYPE = "remediation_recommendation"
_ACTION = "recommendation.generated"


class RecommendationService:
    """Orchestrates the end-to-end remediation recommendation workflow.

    Args:
        finding_repo:   Repository for reading Finding records.
        rec_repo:       Repository for persisting RemediationRecommendation records.
        generator:      RecommendationGenerator that calls the LLM or falls back.
        audit_svc:      AuditService for immutable event logging.
        response_cache: Optional DB-backed ResponseCache (WO-060). When provided,
                        this is checked before the LLM and results are stored on
                        every generation so subsequent identical requests are served
                        from the cache without invoking the LLM provider.
    """

    def __init__(
        self,
        finding_repo: FindingRepository,
        rec_repo: RemediationRecommendationRepository,
        generator: RecommendationGenerator,
        audit_svc: AuditService,
        response_cache: DBResponseCache | None = None,
    ) -> None:
        self._findings = finding_repo
        self._recs = rec_repo
        self._generator = generator
        self._audit = audit_svc
        self._cache = response_cache

    async def get_or_generate(
        self,
        finding_id: uuid.UUID,
        actor_id: str | None = None,
        actor_role: str = "system",
        force_refresh: bool = False,
        correlation_id: str | None = None,
    ) -> dict[str, Any]:
        """Return an existing recommendation or generate a new one.

        With DB cache wired (WO-060):
            1. Check DB cache (keyed by content hash, TTL-aware) → return on hit.
            2. On miss or force_refresh: generate, persist to rec_repo, store in cache.

        Without DB cache (backward compat):
            1. Check rec_repo for latest recommendation → return if found.
            2. On miss or force_refresh: generate and persist.

        Args:
            finding_id:      UUID of the finding to generate guidance for.
            actor_id:        UUID of the requesting user (for audit log).
            actor_role:      Role of the requesting user (for audit log).
            force_refresh:   Bypass cache and regenerate even if one exists.
            correlation_id:  Request correlation ID for traceability.

        Returns:
            The recommendation dict (from the database RETURNING * row).

        Raises:
            NotFoundError: Finding with the given ID does not exist.
        """
        finding = await self._findings.get_by_id(finding_id)
        if finding is None:
            raise NotFoundError(f"Finding {finding_id} not found")

        if self._cache is not None:
            cache_key, cached_entry = await self._cache.get(finding)
            cache_hit = cached_entry is not None and not force_refresh
            logger.info(
                "recommendation_service.cache_lookup",
                event="cache_lookup",
                cache_hit=cache_hit,
                cache_key=cache_key,
                finding_id=str(finding_id),
            )
            if cache_hit:
                return {
                    "id": cached_entry["id"],
                    "finding_id": finding_id,
                    "recommendation_text": cached_entry["response_text"],
                    "implementation_guide": cached_entry["implementation_guide"],
                    "business_impact": None,
                    "confidence_score": cached_entry["confidence_score"],
                    "source": cached_entry["source"],
                    "created_at": cached_entry["created_at"],
                }
        else:
            # No DB cache — fall back to rec_repo (no TTL, original WO-058 behaviour).
            if not force_refresh:
                existing = await self._recs.get_latest_by_finding_id(finding_id)
                if existing is not None:
                    logger.info(
                        "recommendation_service.returning_cached",
                        finding_id=str(finding_id),
                        recommendation_id=str(existing["id"]),
                    )
                    return existing

        result = await self._generator.generate(finding)

        rec_data: dict[str, Any] = {
            "id": uuid.uuid4(),
            "finding_id": finding_id,
            "recommendation_text": result.recommendation_text,
            "implementation_guide": result.implementation_guide,
            "business_impact": result.business_impact,
            "confidence_score": Decimal(str(round(result.confidence_score, 2))),
            "source": result.source,
        }

        try:
            persisted = await self._recs.upsert(finding_id, rec_data)
        except Exception:
            # ON CONFLICT upsert requires a unique constraint on finding_id.
            # If the table doesn't have one yet, fall back to plain create.
            persisted = await self._recs.create(rec_data)

        if self._cache is not None:
            await self._cache.store(
                finding,
                response_text=result.recommendation_text,
                implementation_guide=result.implementation_guide,
                confidence_score=result.confidence_score,
                source=result.source,
            )

        await self._audit_recommendation(
            persisted=persisted,
            finding=finding,
            actor_id=actor_id,
            actor_role=actor_role,
            correlation_id=correlation_id,
        )

        logger.info(
            "recommendation_service.generated",
            finding_id=str(finding_id),
            recommendation_id=str(persisted["id"]),
            source=result.source,
            confidence=result.confidence_score,
        )
        return persisted

    async def _audit_recommendation(
        self,
        persisted: dict[str, Any],
        finding: dict[str, Any],
        actor_id: str | None,
        actor_role: str,
        correlation_id: str | None,
    ) -> None:
        """Emit an immutable audit record for the recommendation generation event."""
        try:
            await self._audit.log_event(
                actor_id=actor_id,
                actor_role=actor_role,
                action=_ACTION,
                resource_type=_RESOURCE_TYPE,
                resource_id=persisted["id"],
                after_state={
                    "finding_id": str(finding.get("id")),
                    "source": persisted.get("source"),
                    "confidence_score": str(persisted.get("confidence_score")),
                    "severity": finding.get("severity"),
                    "dimension": finding.get("dimension"),
                },
                correlation_id=correlation_id,
            )
        except Exception as exc:
            logger.error(
                "recommendation_service.audit_log_failed",
                finding_id=str(finding.get("id")),
                error=str(exc),
            )
