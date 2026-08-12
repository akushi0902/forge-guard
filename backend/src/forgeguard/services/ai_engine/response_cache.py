"""DB-backed response cache for AI remediation recommendations (WO-060).

Distinct from the in-memory LRU cache in services/ai_engine/cache.py, which
caches raw LLM completions. This cache stores structured recommendation data
keyed by content attributes so identical findings across services share one
cached result rather than triggering redundant LLM calls.

Cache key: SHA-256 hex digest of
    "{dimension}:{severity}:{policy_rule_id}:{prompt_template_version}"

Entries expire after ttl_seconds. Policy rule changes trigger synchronous
invalidation via invalidate_by_policy_rule_id().
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

import structlog

from forgeguard.data.repositories.cache_repository import CacheRepository

logger = structlog.get_logger(__name__)

# Increment this constant when the prompt template structure changes to ensure
# previously-cached responses are not returned with the new template.
_PROMPT_TEMPLATE_VERSION = 1


class DBResponseCache:
    """Content-addressable DB cache for AI-generated remediation responses."""

    def __init__(self, cache_repo: CacheRepository, ttl_seconds: int = 3600) -> None:
        self._repo = cache_repo
        self._ttl_seconds = ttl_seconds

    @staticmethod
    def compute_cache_key(
        dimension: str,
        severity: str,
        policy_rule_id: str | None,
        prompt_template_version: int = _PROMPT_TEMPLATE_VERSION,
    ) -> str:
        """Return a deterministic SHA-256 hex key for the given content attributes."""
        raw = f"{dimension}:{severity}:{policy_rule_id}:{prompt_template_version}"
        return hashlib.sha256(raw.encode()).hexdigest()

    def _key_for_finding(self, finding: dict[str, Any]) -> str:
        rule_id = finding.get("policy_rule_id")
        rule_id_str = str(rule_id) if rule_id is not None else None
        return self.compute_cache_key(
            dimension=finding.get("dimension", ""),
            severity=str(finding.get("severity", "")),
            policy_rule_id=rule_id_str,
            prompt_template_version=_PROMPT_TEMPLATE_VERSION,
        )

    async def get(
        self, finding: dict[str, Any]
    ) -> tuple[str, dict[str, Any] | None]:
        """Look up a non-expired cache entry for the given finding.

        Returns:
            (cache_key, entry_dict) on hit; (cache_key, None) on miss.
        """
        cache_key = self._key_for_finding(finding)
        try:
            row = await self._repo.get_by_cache_key(cache_key)
        except Exception as exc:
            logger.warning(
                "response_cache.lookup_failed",
                cache_key=cache_key,
                error=str(exc),
            )
            row = None
        return cache_key, row

    async def store(
        self,
        finding: dict[str, Any],
        response_text: str,
        implementation_guide: str,
        confidence_score: float,
        source: str,
    ) -> None:
        """Upsert a cache entry for the given finding response."""
        cache_key = self._key_for_finding(finding)
        policy_rule_id = finding.get("policy_rule_id")
        if policy_rule_id is not None:
            policy_rule_id = uuid.UUID(str(policy_rule_id))
        expires_at = datetime.now(tz=timezone.utc) + timedelta(seconds=self._ttl_seconds)
        data: dict[str, Any] = {
            "id": uuid.uuid4(),
            "cache_key": cache_key,
            "response_text": response_text,
            "implementation_guide": implementation_guide,
            "confidence_score": Decimal(str(round(confidence_score, 2))),
            "source": source,
            "policy_rule_id": policy_rule_id,
            "prompt_template_version": _PROMPT_TEMPLATE_VERSION,
            "expires_at": expires_at,
        }
        try:
            await self._repo.upsert(data)
        except Exception as exc:
            logger.error(
                "response_cache.store_failed",
                cache_key=cache_key,
                error=str(exc),
            )

    async def invalidate_by_policy_rule_id(self, policy_rule_id: uuid.UUID) -> int:
        """Synchronously invalidate all cache entries for a policy rule.

        Called when a policy rule is modified or deleted so stale recommendations
        are not served after the rule change.
        """
        try:
            count = await self._repo.invalidate_by_policy_rule_id(policy_rule_id)
            logger.info(
                "response_cache.invalidated_by_rule",
                policy_rule_id=str(policy_rule_id),
                count=count,
            )
            return count
        except Exception as exc:
            logger.error(
                "response_cache.invalidation_failed",
                policy_rule_id=str(policy_rule_id),
                error=str(exc),
            )
            return 0

    async def delete_expired(self) -> int:
        """Purge expired cache entries. Suitable for periodic maintenance."""
        return await self._repo.delete_expired()
