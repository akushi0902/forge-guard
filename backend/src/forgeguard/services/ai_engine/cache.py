"""In-memory LRU response cache with TTL eviction.

Cache keys are SHA-256 hashes of the (prompt, sorted params) tuple so the
same logical request always maps to the same bucket regardless of dict ordering.

Design notes:
    - ``OrderedDict`` provides O(1) LRU semantics via ``move_to_end`` /
      ``popitem(last=False)``.
    - TTL eviction is lazy (checked on read, not on a background timer) to
      avoid asyncio task overhead.
    - This cache is NOT thread-safe at the Python level; it must be used from
      a single asyncio event loop, which is the standard FastAPI runtime model.
    - PII must never be cached — callers are responsible for redacting prompt
      content before passing it to ``set()``.
"""

from __future__ import annotations

import hashlib
import json
import time
from collections import OrderedDict
from typing import Any

from .models import LLMResponse, ResponseSource


class ResponseCache:
    """LRU in-memory cache for LLM responses.

    Args:
        max_size:    Maximum number of entries.  Oldest entries are evicted
                     when this limit is reached.
        ttl_seconds: Time-to-live for each entry in seconds.
    """

    def __init__(self, max_size: int = 1000, ttl_seconds: int = 3600) -> None:
        self._max_size = max_size
        self._ttl = ttl_seconds
        # Mapping of cache_key → (LLMResponse, insert_timestamp_monotonic)
        self._cache: OrderedDict[str, tuple[LLMResponse, float]] = OrderedDict()
        self._hits: int = 0
        self._misses: int = 0

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def get(self, prompt: str, params: dict[str, Any] | None = None) -> LLMResponse | None:
        """Return a cached response or ``None`` on miss / TTL expiry.

        On a hit the entry is promoted to MRU position (LRU semantics).
        Expired entries are evicted eagerly on read.
        """
        key = self._make_key(prompt, params)
        entry = self._cache.get(key)
        if entry is None:
            self._misses += 1
            return None

        response, inserted_at = entry
        if (time.monotonic() - inserted_at) > self._ttl:
            del self._cache[key]
            self._misses += 1
            return None

        # Promote to MRU.
        self._cache.move_to_end(key)
        self._hits += 1

        # Return a copy with the cached source tag applied.
        import dataclasses
        return dataclasses.replace(response, source=ResponseSource.AI_GENERATED_CACHED)

    def set(
        self,
        prompt: str,
        params: dict[str, Any] | None,
        response: LLMResponse,
    ) -> None:
        """Store a response in the cache.

        If the cache is at capacity the LRU entry is evicted first.
        """
        key = self._make_key(prompt, params)
        self._cache[key] = (response, time.monotonic())
        self._cache.move_to_end(key)

        while len(self._cache) > self._max_size:
            self._cache.popitem(last=False)  # evict LRU

    def invalidate(self, prompt: str, params: dict[str, Any] | None = None) -> bool:
        """Remove a specific entry.  Returns True if it existed."""
        key = self._make_key(prompt, params)
        if key in self._cache:
            del self._cache[key]
            return True
        return False

    def clear(self) -> None:
        """Remove all entries and reset counters."""
        self._cache.clear()
        self._hits = 0
        self._misses = 0

    # ------------------------------------------------------------------
    # Metrics
    # ------------------------------------------------------------------

    @property
    def hit_ratio(self) -> float:
        """Fraction of lookups that returned a cached result (0.0–1.0)."""
        total = self._hits + self._misses
        return self._hits / total if total > 0 else 0.0

    @property
    def hit_count(self) -> int:
        return self._hits

    @property
    def miss_count(self) -> int:
        return self._misses

    @property
    def size(self) -> int:
        return len(self._cache)

    # ------------------------------------------------------------------
    # Key generation
    # ------------------------------------------------------------------

    @staticmethod
    def _make_key(prompt: str, params: dict[str, Any] | None) -> str:
        """Deterministic SHA-256 key from prompt + canonicalized params."""
        params_str = json.dumps(params or {}, sort_keys=True, ensure_ascii=False)
        raw = f"{prompt}\x00{params_str}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()
