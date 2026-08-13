"""Unit tests for ResponseCache.

Covers:
    1. Cache hit — returns cached response with AI_GENERATED_CACHED source.
    2. Cache miss — returns None.
    3. TTL expiry — expired entries not returned.
    4. Max size eviction — LRU entry evicted when full.
    5. Key generation determinism — same prompt+params → same key.
    6. Key differentiation — different prompts/params → different keys.
    7. hit_ratio computed correctly.
    8. clear() resets all state.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from forgeguard.services.ai_engine.cache import ResponseCache
from forgeguard.services.ai_engine.models import LLMResponse, ResponseSource


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_response(content: str = "test response") -> LLMResponse:
    return LLMResponse(
        content=content,
        confidence_score=0.9,
        source=ResponseSource.AI_GENERATED,
        latency_ms=100,
        model="gpt-4o-mini",
        token_usage={"total_tokens": 30},
    )


# ---------------------------------------------------------------------------
# Cache hit / miss
# ---------------------------------------------------------------------------

class TestCacheHitMiss:
    def test_miss_returns_none(self) -> None:
        cache = ResponseCache()
        assert cache.get("unknown prompt") is None

    def test_hit_returns_response(self) -> None:
        cache = ResponseCache()
        resp = _make_response("hello")
        cache.set("prompt", {}, resp)
        result = cache.get("prompt", {})
        assert result is not None
        assert result.content == "hello"

    def test_hit_source_is_cached(self) -> None:
        cache = ResponseCache()
        resp = _make_response()
        cache.set("prompt", None, resp)
        result = cache.get("prompt", None)
        assert result is not None
        assert result.source == ResponseSource.AI_GENERATED_CACHED

    def test_original_source_not_mutated(self) -> None:
        cache = ResponseCache()
        resp = _make_response()
        cache.set("prompt", None, resp)
        cache.get("prompt", None)
        # Original response is unchanged.
        assert resp.source == ResponseSource.AI_GENERATED

    def test_hit_increments_hit_count(self) -> None:
        cache = ResponseCache()
        cache.set("p", None, _make_response())
        cache.get("p", None)
        assert cache.hit_count == 1

    def test_miss_increments_miss_count(self) -> None:
        cache = ResponseCache()
        cache.get("missing")
        assert cache.miss_count == 1


# ---------------------------------------------------------------------------
# TTL expiry
# ---------------------------------------------------------------------------

class TestTTLExpiry:
    def test_entry_expired_after_ttl(self) -> None:
        cache = ResponseCache(ttl_seconds=60)
        cache.set("prompt", None, _make_response())

        with patch("forgeguard.services.ai_engine.cache.time.monotonic") as m:
            m.return_value = 1_000_000.0 + 61  # well past TTL
            cache._cache["_dummy"] if False else None  # ensure patch active
            # The entry's inserted_at was ~0; now monotonic() returns 61s later.
            # Patch only affects the get() path; inserted_at was real.

        # Re-insert with patched time so we control both sides.
        cache2 = ResponseCache(ttl_seconds=60)
        with patch("forgeguard.services.ai_engine.cache.time.monotonic") as m:
            m.return_value = 1000.0
            cache2.set("prompt", None, _make_response())

        with patch("forgeguard.services.ai_engine.cache.time.monotonic") as m:
            m.return_value = 1000.0 + 61  # 61s later
            result = cache2.get("prompt", None)

        assert result is None  # expired

    def test_entry_valid_within_ttl(self) -> None:
        cache = ResponseCache(ttl_seconds=60)
        with patch("forgeguard.services.ai_engine.cache.time.monotonic") as m:
            m.return_value = 1000.0
            cache.set("prompt", None, _make_response())

        with patch("forgeguard.services.ai_engine.cache.time.monotonic") as m:
            m.return_value = 1000.0 + 59  # within TTL
            result = cache.get("prompt", None)

        assert result is not None

    def test_expired_entry_evicted_on_read(self) -> None:
        cache = ResponseCache(ttl_seconds=60)
        with patch("forgeguard.services.ai_engine.cache.time.monotonic") as m:
            m.return_value = 0.0
            cache.set("prompt", None, _make_response())
        assert cache.size == 1

        with patch("forgeguard.services.ai_engine.cache.time.monotonic") as m:
            m.return_value = 61.0
            cache.get("prompt", None)

        assert cache.size == 0  # evicted on read


# ---------------------------------------------------------------------------
# Max size eviction (LRU)
# ---------------------------------------------------------------------------

class TestMaxSizeEviction:
    def test_lru_evicted_when_full(self) -> None:
        cache = ResponseCache(max_size=3)
        cache.set("a", None, _make_response("a"))
        cache.set("b", None, _make_response("b"))
        cache.set("c", None, _make_response("c"))
        assert cache.size == 3

        # Access "a" to promote it (LRU order: b < c < a).
        cache.get("a", None)

        # Adding "d" should evict the LRU entry, which is "b".
        cache.set("d", None, _make_response("d"))
        assert cache.size == 3
        assert cache.get("b", None) is None   # "b" was evicted
        assert cache.get("a", None) is not None
        assert cache.get("c", None) is not None
        assert cache.get("d", None) is not None

    def test_size_never_exceeds_max(self) -> None:
        cache = ResponseCache(max_size=5)
        for i in range(20):
            cache.set(f"prompt_{i}", None, _make_response(f"resp_{i}"))
        assert cache.size <= 5


# ---------------------------------------------------------------------------
# Key generation
# ---------------------------------------------------------------------------

class TestKeyGeneration:
    def test_same_inputs_produce_same_key(self) -> None:
        k1 = ResponseCache._make_key("hello", {"a": 1})
        k2 = ResponseCache._make_key("hello", {"a": 1})
        assert k1 == k2

    def test_different_prompt_different_key(self) -> None:
        k1 = ResponseCache._make_key("prompt A", None)
        k2 = ResponseCache._make_key("prompt B", None)
        assert k1 != k2

    def test_different_params_different_key(self) -> None:
        k1 = ResponseCache._make_key("prompt", {"temperature": 0.7})
        k2 = ResponseCache._make_key("prompt", {"temperature": 0.9})
        assert k1 != k2

    def test_param_order_irrelevant(self) -> None:
        k1 = ResponseCache._make_key("p", {"a": 1, "b": 2})
        k2 = ResponseCache._make_key("p", {"b": 2, "a": 1})
        assert k1 == k2

    def test_none_params_same_as_empty_dict(self) -> None:
        k1 = ResponseCache._make_key("p", None)
        k2 = ResponseCache._make_key("p", {})
        assert k1 == k2

    def test_key_is_64_char_hex(self) -> None:
        k = ResponseCache._make_key("test", None)
        assert len(k) == 64
        assert all(c in "0123456789abcdef" for c in k)


# ---------------------------------------------------------------------------
# hit_ratio
# ---------------------------------------------------------------------------

class TestHitRatio:
    def test_initial_ratio_is_zero(self) -> None:
        cache = ResponseCache()
        assert cache.hit_ratio == 0.0

    def test_ratio_after_only_hits(self) -> None:
        cache = ResponseCache()
        cache.set("p", None, _make_response())
        cache.get("p", None)
        cache.get("p", None)
        assert cache.hit_ratio == 1.0

    def test_ratio_after_only_misses(self) -> None:
        cache = ResponseCache()
        cache.get("missing1")
        cache.get("missing2")
        assert cache.hit_ratio == 0.0

    def test_ratio_mixed(self) -> None:
        cache = ResponseCache()
        cache.set("p", None, _make_response())
        cache.get("p", None)   # hit
        cache.get("q", None)   # miss
        assert cache.hit_ratio == 0.5


# ---------------------------------------------------------------------------
# invalidate and clear
# ---------------------------------------------------------------------------

class TestInvalidateAndClear:
    def test_invalidate_removes_entry(self) -> None:
        cache = ResponseCache()
        cache.set("p", None, _make_response())
        assert cache.invalidate("p", None) is True
        assert cache.get("p", None) is None

    def test_invalidate_returns_false_for_missing(self) -> None:
        cache = ResponseCache()
        assert cache.invalidate("nope") is False

    def test_clear_resets_everything(self) -> None:
        cache = ResponseCache()
        cache.set("p", None, _make_response())
        cache.get("p", None)   # hit
        cache.get("q", None)   # miss
        cache.clear()
        assert cache.size == 0
        assert cache.hit_count == 0
        assert cache.miss_count == 0
        assert cache.hit_ratio == 0.0
