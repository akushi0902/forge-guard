"""Unit tests for DBResponseCache (WO-060).

Coverage:
    - Cache key determinism: same inputs → same key, different inputs → different key
    - Cache key components: dimension, severity, policy_rule_id, template_version
    - TTL expiration: expired entries treated as cache miss (repository-level check)
    - force-refresh bypasses cache hit
    - store() calls repository upsert with correct fields
    - invalidate_by_policy_rule_id() delegates to repository
    - delete_expired() delegates to repository
    - Repository failure on get() degrades gracefully (returns miss, no exception)
    - Repository failure on store() logs error but does not raise
    - RecommendationService integrates cache correctly

Run:
    pytest tests/unit/services/ai_engine/test_response_cache.py -v
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from forgeguard.services.ai_engine.response_cache import DBResponseCache, _PROMPT_TEMPLATE_VERSION
from tests.fixtures.ai_response_cache import (
    CACHE_ENTRY_EXPIRED,
    CACHE_ENTRY_FRESH,
    CACHE_KEY_CRITICAL_SECURITY,
    CACHE_KEY_HIGH_QUALITY,
    CACHE_KEY_NO_RULE,
    FINDING_CRITICAL_SECURITY,
    FINDING_HIGH_QUALITY,
    FINDING_NO_RULE,
    POLICY_RULE_ID_A,
    make_cache_entry,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_cache(
    get_result: dict[str, Any] | None = None,
    upsert_result: dict[str, Any] | None = None,
    invalidate_count: int = 0,
    delete_count: int = 0,
    get_raises: Exception | None = None,
) -> tuple[DBResponseCache, MagicMock]:
    repo = MagicMock()
    if get_raises:
        repo.get_by_cache_key = AsyncMock(side_effect=get_raises)
    else:
        repo.get_by_cache_key = AsyncMock(return_value=get_result)
    repo.upsert = AsyncMock(
        return_value=upsert_result or make_cache_entry()
    )
    repo.invalidate_by_policy_rule_id = AsyncMock(return_value=invalidate_count)
    repo.delete_expired = AsyncMock(return_value=delete_count)
    return DBResponseCache(cache_repo=repo, ttl_seconds=3600), repo


# ===========================================================================
# Cache key determinism
# ===========================================================================

class TestCacheKeyDeterminism:
    def test_same_inputs_produce_same_key(self) -> None:
        k1 = DBResponseCache.compute_cache_key("security", "critical", "rule-1")
        k2 = DBResponseCache.compute_cache_key("security", "critical", "rule-1")
        assert k1 == k2

    def test_different_dimension_produces_different_key(self) -> None:
        k1 = DBResponseCache.compute_cache_key("security", "critical", "rule-1")
        k2 = DBResponseCache.compute_cache_key("code_quality", "critical", "rule-1")
        assert k1 != k2

    def test_different_severity_produces_different_key(self) -> None:
        k1 = DBResponseCache.compute_cache_key("security", "critical", "rule-1")
        k2 = DBResponseCache.compute_cache_key("security", "high", "rule-1")
        assert k1 != k2

    def test_different_policy_rule_id_produces_different_key(self) -> None:
        k1 = DBResponseCache.compute_cache_key("security", "critical", "rule-1")
        k2 = DBResponseCache.compute_cache_key("security", "critical", "rule-2")
        assert k1 != k2

    def test_none_policy_rule_id_produces_different_key(self) -> None:
        k1 = DBResponseCache.compute_cache_key("security", "critical", "rule-1")
        k2 = DBResponseCache.compute_cache_key("security", "critical", None)
        assert k1 != k2

    def test_different_template_version_produces_different_key(self) -> None:
        k1 = DBResponseCache.compute_cache_key("security", "critical", "rule-1", 1)
        k2 = DBResponseCache.compute_cache_key("security", "critical", "rule-1", 2)
        assert k1 != k2

    def test_key_is_sha256_hex_digest(self) -> None:
        raw = f"security:critical:rule-1:{_PROMPT_TEMPLATE_VERSION}"
        expected = hashlib.sha256(raw.encode()).hexdigest()
        assert DBResponseCache.compute_cache_key("security", "critical", "rule-1") == expected

    def test_key_length_is_64_chars(self) -> None:
        key = DBResponseCache.compute_cache_key("security", "critical", "rule-1")
        assert len(key) == 64

    def test_known_finding_keys_match_precomputed_fixtures(self) -> None:
        rule_id = str(POLICY_RULE_ID_A)
        computed = DBResponseCache.compute_cache_key("security", "critical", rule_id)
        assert computed == CACHE_KEY_CRITICAL_SECURITY

    def test_no_rule_finding_key_matches_fixture(self) -> None:
        computed = DBResponseCache.compute_cache_key("reliability", "medium", None)
        assert computed == CACHE_KEY_NO_RULE


# ===========================================================================
# Cache get() — hit and miss
# ===========================================================================

class TestCacheGet:
    @pytest.mark.asyncio
    async def test_cache_hit_returns_entry(self) -> None:
        cache, repo = _make_cache(get_result=CACHE_ENTRY_FRESH)
        key, entry = await cache.get(FINDING_CRITICAL_SECURITY)
        assert entry is not None
        assert entry["cache_key"] == CACHE_KEY_CRITICAL_SECURITY
        repo.get_by_cache_key.assert_awaited_once_with(CACHE_KEY_CRITICAL_SECURITY)

    @pytest.mark.asyncio
    async def test_cache_miss_returns_none(self) -> None:
        cache, repo = _make_cache(get_result=None)
        key, entry = await cache.get(FINDING_CRITICAL_SECURITY)
        assert entry is None

    @pytest.mark.asyncio
    async def test_returns_correct_cache_key(self) -> None:
        cache, _ = _make_cache(get_result=None)
        key, _ = await cache.get(FINDING_CRITICAL_SECURITY)
        assert key == CACHE_KEY_CRITICAL_SECURITY

    @pytest.mark.asyncio
    async def test_different_findings_produce_different_keys(self) -> None:
        cache, _ = _make_cache(get_result=None)
        key_a, _ = await cache.get(FINDING_CRITICAL_SECURITY)
        key_b, _ = await cache.get(FINDING_HIGH_QUALITY)
        assert key_a != key_b

    @pytest.mark.asyncio
    async def test_repo_failure_degrades_gracefully_to_miss(self) -> None:
        cache, _ = _make_cache(get_raises=RuntimeError("DB error"))
        key, entry = await cache.get(FINDING_CRITICAL_SECURITY)
        assert entry is None  # treated as cache miss, no exception propagated

    @pytest.mark.asyncio
    async def test_finding_with_no_rule_id_computes_correct_key(self) -> None:
        cache, repo = _make_cache(get_result=None)
        key, _ = await cache.get(FINDING_NO_RULE)
        assert key == CACHE_KEY_NO_RULE
        repo.get_by_cache_key.assert_awaited_once_with(CACHE_KEY_NO_RULE)


# ===========================================================================
# Cache store()
# ===========================================================================

class TestCacheStore:
    @pytest.mark.asyncio
    async def test_store_calls_upsert_with_correct_cache_key(self) -> None:
        cache, repo = _make_cache()
        await cache.store(
            FINDING_CRITICAL_SECURITY,
            response_text="Fix the SAST config.",
            implementation_guide="Step 1, Step 2.",
            confidence_score=0.85,
            source="ai_generated",
        )
        call_data = repo.upsert.call_args[0][0]
        assert call_data["cache_key"] == CACHE_KEY_CRITICAL_SECURITY

    @pytest.mark.asyncio
    async def test_store_sets_response_text(self) -> None:
        cache, repo = _make_cache()
        await cache.store(
            FINDING_CRITICAL_SECURITY,
            response_text="Detailed fix.",
            implementation_guide="Guide.",
            confidence_score=0.9,
            source="ai_generated",
        )
        call_data = repo.upsert.call_args[0][0]
        assert call_data["response_text"] == "Detailed fix."

    @pytest.mark.asyncio
    async def test_store_sets_expires_at_in_future(self) -> None:
        cache, repo = _make_cache()
        await cache.store(
            FINDING_CRITICAL_SECURITY,
            response_text="Fix.",
            implementation_guide="Guide.",
            confidence_score=0.8,
            source="ai_generated",
        )
        call_data = repo.upsert.call_args[0][0]
        now = datetime.now(tz=timezone.utc)
        assert call_data["expires_at"] > now

    @pytest.mark.asyncio
    async def test_store_expires_at_respects_ttl(self) -> None:
        cache, repo = _make_cache()
        cache._ttl_seconds = 7200
        await cache.store(
            FINDING_CRITICAL_SECURITY,
            response_text="Fix.",
            implementation_guide="Guide.",
            confidence_score=0.8,
            source="ai_generated",
        )
        call_data = repo.upsert.call_args[0][0]
        now = datetime.now(tz=timezone.utc)
        diff = (call_data["expires_at"] - now).total_seconds()
        assert 7100 < diff < 7300  # within 100s of 7200

    @pytest.mark.asyncio
    async def test_store_failure_does_not_raise(self) -> None:
        cache, repo = _make_cache()
        repo.upsert = AsyncMock(side_effect=RuntimeError("write failed"))
        # Must not propagate the exception
        await cache.store(
            FINDING_CRITICAL_SECURITY,
            response_text="Fix.",
            implementation_guide="Guide.",
            confidence_score=0.8,
            source="ai_generated",
        )

    @pytest.mark.asyncio
    async def test_store_sets_policy_rule_id_from_finding(self) -> None:
        cache, repo = _make_cache()
        await cache.store(
            FINDING_CRITICAL_SECURITY,
            response_text="Fix.",
            implementation_guide="Guide.",
            confidence_score=0.8,
            source="ai_generated",
        )
        call_data = repo.upsert.call_args[0][0]
        assert call_data["policy_rule_id"] == POLICY_RULE_ID_A

    @pytest.mark.asyncio
    async def test_store_null_policy_rule_id_when_absent(self) -> None:
        cache, repo = _make_cache()
        await cache.store(
            FINDING_NO_RULE,
            response_text="Fix.",
            implementation_guide="Guide.",
            confidence_score=0.5,
            source="template_fallback",
        )
        call_data = repo.upsert.call_args[0][0]
        assert call_data["policy_rule_id"] is None

    @pytest.mark.asyncio
    async def test_store_sets_prompt_template_version(self) -> None:
        cache, repo = _make_cache()
        await cache.store(
            FINDING_CRITICAL_SECURITY,
            response_text="Fix.",
            implementation_guide="Guide.",
            confidence_score=0.8,
            source="ai_generated",
        )
        call_data = repo.upsert.call_args[0][0]
        assert call_data["prompt_template_version"] == _PROMPT_TEMPLATE_VERSION


# ===========================================================================
# TTL expiration (repository-level check)
# ===========================================================================

class TestTTLExpiration:
    @pytest.mark.asyncio
    async def test_expired_entry_returns_none(self) -> None:
        # Repository returns None for expired entries (expires_at <= now())
        cache, repo = _make_cache(get_result=None)
        key, entry = await cache.get(FINDING_NO_RULE)
        assert entry is None

    @pytest.mark.asyncio
    async def test_fresh_entry_is_returned(self) -> None:
        cache, _ = _make_cache(get_result=CACHE_ENTRY_FRESH)
        _, entry = await cache.get(FINDING_CRITICAL_SECURITY)
        assert entry is not None

    @pytest.mark.asyncio
    async def test_repository_filters_by_expires_at(self) -> None:
        cache, repo = _make_cache(get_result=None)
        await cache.get(FINDING_CRITICAL_SECURITY)
        # get_by_cache_key is called — the repo itself is responsible for the
        # expires_at > now() filter; here we verify the call was made.
        repo.get_by_cache_key.assert_awaited_once()


# ===========================================================================
# Invalidation
# ===========================================================================

class TestInvalidation:
    @pytest.mark.asyncio
    async def test_invalidate_by_policy_rule_id_calls_repo(self) -> None:
        cache, repo = _make_cache(invalidate_count=3)
        count = await cache.invalidate_by_policy_rule_id(POLICY_RULE_ID_A)
        repo.invalidate_by_policy_rule_id.assert_awaited_once_with(POLICY_RULE_ID_A)
        assert count == 3

    @pytest.mark.asyncio
    async def test_invalidate_returns_count(self) -> None:
        cache, _ = _make_cache(invalidate_count=5)
        count = await cache.invalidate_by_policy_rule_id(POLICY_RULE_ID_A)
        assert count == 5

    @pytest.mark.asyncio
    async def test_invalidate_failure_returns_zero(self) -> None:
        cache, repo = _make_cache()
        repo.invalidate_by_policy_rule_id = AsyncMock(side_effect=RuntimeError("DB error"))
        count = await cache.invalidate_by_policy_rule_id(POLICY_RULE_ID_A)
        assert count == 0

    @pytest.mark.asyncio
    async def test_delete_expired_delegates_to_repo(self) -> None:
        cache, repo = _make_cache(delete_count=7)
        count = await cache.delete_expired()
        repo.delete_expired.assert_awaited_once()
        assert count == 7


# ===========================================================================
# RecommendationService integration with cache
# ===========================================================================

class TestRecommendationServiceIntegration:
    """Verify RecommendationService cache hit/miss/force-refresh behaviour."""

    def _make_service(
        self,
        finding: dict[str, Any] | None = None,
        cached_entry: dict[str, Any] | None = None,
        cache_raises: Exception | None = None,
        force_refresh: bool = False,
    ):
        from forgeguard.services.remediation.recommendation_service import RecommendationService
        from forgeguard.services.ai_engine.recommendation_generator import RecommendationResult

        finding_repo = MagicMock()
        finding_repo.get_by_id = AsyncMock(
            return_value=finding or FINDING_CRITICAL_SECURITY
        )

        rec_repo = MagicMock()
        persisted_rec = {
            "id": uuid.uuid4(),
            "finding_id": FINDING_CRITICAL_SECURITY["id"],
            "recommendation_text": "Generated recommendation.",
            "implementation_guide": "Generated guide.",
            "business_impact": "Impact.",
            "confidence_score": Decimal("0.85"),
            "source": "ai_generated",
            "created_at": datetime.now(tz=timezone.utc),
        }
        rec_repo.upsert = AsyncMock(return_value=persisted_rec)
        rec_repo.get_latest_by_finding_id = AsyncMock(return_value=None)

        generated = RecommendationResult(
            recommendation_text="Generated recommendation.",
            implementation_guide="Generated guide.",
            business_impact="Impact.",
            confidence_score=0.85,
            source="ai_generated",
        )
        generator = MagicMock()
        generator.generate = AsyncMock(return_value=generated)

        audit_svc = MagicMock()
        audit_svc.log_event = AsyncMock(return_value=None)

        cache_repo = MagicMock()
        if cache_raises:
            cache_repo.get_by_cache_key = AsyncMock(side_effect=cache_raises)
        else:
            cache_repo.get_by_cache_key = AsyncMock(return_value=cached_entry)
        cache_repo.upsert = AsyncMock(return_value=make_cache_entry())
        response_cache = DBResponseCache(cache_repo=cache_repo, ttl_seconds=3600)

        svc = RecommendationService(
            finding_repo=finding_repo,
            rec_repo=rec_repo,
            generator=generator,
            audit_svc=audit_svc,
            response_cache=response_cache,
        )
        return svc, generator, cache_repo

    @pytest.mark.asyncio
    async def test_cache_hit_returns_without_calling_generator(self) -> None:
        svc, generator, _ = self._make_service(cached_entry=CACHE_ENTRY_FRESH)
        result = await svc.get_or_generate(
            finding_id=FINDING_CRITICAL_SECURITY["id"],
        )
        generator.generate.assert_not_awaited()
        assert result["recommendation_text"] == CACHE_ENTRY_FRESH["response_text"]

    @pytest.mark.asyncio
    async def test_cache_miss_calls_generator(self) -> None:
        svc, generator, _ = self._make_service(cached_entry=None)
        await svc.get_or_generate(finding_id=FINDING_CRITICAL_SECURITY["id"])
        generator.generate.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_force_refresh_bypasses_cache_hit(self) -> None:
        svc, generator, _ = self._make_service(cached_entry=CACHE_ENTRY_FRESH)
        await svc.get_or_generate(
            finding_id=FINDING_CRITICAL_SECURITY["id"],
            force_refresh=True,
        )
        # Even though cache has a fresh entry, generator is called
        generator.generate.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_cache_miss_stores_after_generation(self) -> None:
        svc, generator, cache_repo = self._make_service(cached_entry=None)
        await svc.get_or_generate(finding_id=FINDING_CRITICAL_SECURITY["id"])
        cache_repo.upsert.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_force_refresh_stores_after_generation(self) -> None:
        svc, generator, cache_repo = self._make_service(cached_entry=CACHE_ENTRY_FRESH)
        await svc.get_or_generate(
            finding_id=FINDING_CRITICAL_SECURITY["id"],
            force_refresh=True,
        )
        cache_repo.upsert.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_cache_hit_returns_correct_fields(self) -> None:
        svc, _, _ = self._make_service(cached_entry=CACHE_ENTRY_FRESH)
        result = await svc.get_or_generate(finding_id=FINDING_CRITICAL_SECURITY["id"])
        assert result["recommendation_text"] == CACHE_ENTRY_FRESH["response_text"]
        assert result["implementation_guide"] == CACHE_ENTRY_FRESH["implementation_guide"]
        assert result["confidence_score"] == CACHE_ENTRY_FRESH["confidence_score"]
        assert result["source"] == CACHE_ENTRY_FRESH["source"]

    @pytest.mark.asyncio
    async def test_no_cache_falls_back_to_rec_repo(self) -> None:
        """Without response_cache, existing rec_repo recommendation is returned."""
        from forgeguard.services.remediation.recommendation_service import RecommendationService
        from forgeguard.services.ai_engine.recommendation_generator import RecommendationResult

        existing_rec = {
            "id": uuid.uuid4(),
            "finding_id": FINDING_CRITICAL_SECURITY["id"],
            "recommendation_text": "Existing recommendation.",
            "implementation_guide": "Existing guide.",
            "confidence_score": Decimal("0.70"),
            "source": "ai_generated",
            "created_at": datetime.now(tz=timezone.utc),
        }
        finding_repo = MagicMock()
        finding_repo.get_by_id = AsyncMock(return_value=FINDING_CRITICAL_SECURITY)
        rec_repo = MagicMock()
        rec_repo.get_latest_by_finding_id = AsyncMock(return_value=existing_rec)
        generator = MagicMock()
        generator.generate = AsyncMock()
        audit_svc = MagicMock()
        audit_svc.log_event = AsyncMock()

        svc = RecommendationService(
            finding_repo=finding_repo,
            rec_repo=rec_repo,
            generator=generator,
            audit_svc=audit_svc,
            response_cache=None,  # no DB cache
        )
        result = await svc.get_or_generate(finding_id=FINDING_CRITICAL_SECURITY["id"])
        generator.generate.assert_not_awaited()
        assert result["recommendation_text"] == "Existing recommendation."
