"""CacheRepository: async CRUD for the ai_response_cache table (WO-060).

Methods:
    get_by_cache_key        — fetch non-expired entry by SHA-256 key
    upsert                  — insert or update on conflict (cache_key)
    invalidate_by_policy_rule_id — delete all entries for a rule
    delete_expired          — purge entries where expires_at < now()
"""

from __future__ import annotations

import uuid
from typing import Any

import structlog

from forgeguard.data.repositories.base import BaseRepository

logger = structlog.get_logger(__name__)


class CacheRepository(BaseRepository):
    _table = "ai_response_cache"

    async def get_by_cache_key(self, cache_key: str) -> dict[str, Any] | None:
        """Return a non-expired cache entry by its SHA-256 key, or None."""
        q = (
            "SELECT * FROM ai_response_cache "
            "WHERE cache_key = $1 AND expires_at > now()"
        )
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(q, cache_key)
        return self._row(row)

    async def upsert(self, data: dict[str, Any]) -> dict[str, Any]:
        """Insert or update a cache entry; resolves conflicts on cache_key."""
        q = """
            INSERT INTO ai_response_cache (
                id, cache_key, response_text, implementation_guide,
                confidence_score, source, policy_rule_id,
                prompt_template_version, created_at, expires_at
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, now(), $9)
            ON CONFLICT (cache_key) DO UPDATE SET
                response_text        = EXCLUDED.response_text,
                implementation_guide = EXCLUDED.implementation_guide,
                confidence_score     = EXCLUDED.confidence_score,
                source               = EXCLUDED.source,
                policy_rule_id       = EXCLUDED.policy_rule_id,
                prompt_template_version = EXCLUDED.prompt_template_version,
                expires_at           = EXCLUDED.expires_at
            RETURNING *
        """
        row_id = data.get("id") or uuid.uuid4()
        if not isinstance(row_id, uuid.UUID):
            row_id = uuid.UUID(str(row_id))
        policy_rule_id = data.get("policy_rule_id")
        if policy_rule_id is not None and not isinstance(policy_rule_id, uuid.UUID):
            policy_rule_id = uuid.UUID(str(policy_rule_id))
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                q,
                row_id,
                data["cache_key"],
                data["response_text"],
                data["implementation_guide"],
                data["confidence_score"],
                data["source"],
                policy_rule_id,
                data.get("prompt_template_version"),
                data["expires_at"],
            )
        return dict(row)  # type: ignore[arg-type]

    async def invalidate_by_policy_rule_id(self, policy_rule_id: uuid.UUID) -> int:
        """Delete all cache entries referencing the given policy rule."""
        q = "DELETE FROM ai_response_cache WHERE policy_rule_id = $1"
        async with self._pool.acquire() as conn:
            result = await conn.execute(q, policy_rule_id)
        # asyncpg returns a tag string like "DELETE N"
        try:
            return int(result.split()[-1])
        except (AttributeError, IndexError, ValueError):
            return 0

    async def delete_expired(self) -> int:
        """Purge entries where expires_at < now(). Call from maintenance jobs."""
        q = "DELETE FROM ai_response_cache WHERE expires_at < now()"
        async with self._pool.acquire() as conn:
            result = await conn.execute(q)
        try:
            return int(result.split()[-1])
        except (AttributeError, IndexError, ValueError):
            return 0

    async def soft_delete(self, id: str | uuid.UUID) -> bool:
        raise NotImplementedError(
            "ai_response_cache does not support soft delete — "
            "use delete_expired() or invalidate_by_policy_rule_id()"
        )
