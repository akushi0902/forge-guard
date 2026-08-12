"""AgentRepository: async CRUD for ai_conversations and agent_feedback (WO-065)."""

from __future__ import annotations

import base64
import json
import uuid
from datetime import datetime, timezone
from typing import Any

import asyncpg
import structlog

from forgeguard.data.repositories.base import BaseRepository

logger = structlog.get_logger(__name__)

_CONV_ALLOWED_INSERT: frozenset[str] = frozenset({
    "id", "user_id", "messages", "context_refs",
})

_FEEDBACK_ALLOWED_INSERT: frozenset[str] = frozenset({
    "id", "conversation_id", "message_index", "user_id", "rating",
})


def _encode_cursor(created_at: datetime, row_id: uuid.UUID) -> str:
    payload = f"{created_at.isoformat()}|{row_id}"
    return base64.urlsafe_b64encode(payload.encode()).decode()


def _decode_cursor(cursor: str) -> tuple[datetime, uuid.UUID] | None:
    try:
        payload = base64.urlsafe_b64decode(cursor.encode()).decode()
        iso, id_str = payload.split("|", 1)
        return datetime.fromisoformat(iso), uuid.UUID(id_str)
    except Exception:  # noqa: BLE001
        return None


class AgentRepository(BaseRepository):
    """Async repository for AI agent conversations and feedback.

    Provides cursor-based pagination, atomic JSONB message append, and
    feedback persistence for the agent query lifecycle.
    """

    _table = "ai_conversations"

    # ------------------------------------------------------------------
    # BaseRepository abstract interface
    # ------------------------------------------------------------------

    async def get_by_id(
        self,
        id: str | uuid.UUID,
        *,
        include_deleted: bool = False,
    ) -> dict[str, Any] | None:
        row = await self._pool.fetchrow(
            "SELECT * FROM ai_conversations WHERE id = $1",
            uuid.UUID(str(id)),
        )
        return self._row(row)

    async def list(
        self,
        *,
        filters: dict[str, Any] | None = None,
        cursor: str | None = None,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        rows = await self._pool.fetch(
            "SELECT * FROM ai_conversations ORDER BY created_at DESC LIMIT $1",
            limit,
        )
        return self._rows(rows)

    async def create(self, data: dict[str, Any]) -> dict[str, Any]:
        query, values = self._safe_insert("ai_conversations", _CONV_ALLOWED_INSERT, data)
        row = await self._pool.fetchrow(query, *values)
        return dict(row)

    async def update(
        self, id: str | uuid.UUID, data: dict[str, Any]
    ) -> dict[str, Any] | None:
        raise NotImplementedError("Use append_message for conversation updates.")

    async def soft_delete(self, id: str | uuid.UUID) -> bool:
        raise NotImplementedError("ai_conversations are not soft-deleted.")

    # ------------------------------------------------------------------
    # Domain-specific methods
    # ------------------------------------------------------------------

    async def create_conversation(
        self,
        user_id: uuid.UUID,
        messages: list[Any] | None = None,
        context_refs: list[Any] | None = None,
    ) -> dict[str, Any]:
        """Create a new AI conversation for *user_id*."""
        data: dict[str, Any] = {
            "id": uuid.uuid4(),
            "user_id": user_id,
            "messages": json.dumps(messages or []),
            "context_refs": json.dumps(context_refs or []),
        }
        query, values = self._safe_insert("ai_conversations", _CONV_ALLOWED_INSERT, data)
        row = await self._pool.fetchrow(query, *values)
        return dict(row)

    async def get_conversation_by_id(
        self, conversation_id: uuid.UUID
    ) -> dict[str, Any] | None:
        return await self.get_by_id(conversation_id)

    async def append_message(
        self,
        conversation_id: uuid.UUID,
        user_id: uuid.UUID,
        message: dict[str, Any],
    ) -> dict[str, Any] | None:
        """Atomically append *message* to the messages JSONB array.

        The WHERE clause on user_id ensures a user can only append to their
        own conversations.  Returns None if the conversation is not found or
        does not belong to user_id.
        """
        row = await self._pool.fetchrow(
            """
            UPDATE ai_conversations
               SET messages = messages || $1::jsonb,
                   updated_at = NOW()
             WHERE id = $2
               AND user_id = $3
            RETURNING *
            """,
            json.dumps([message]),
            conversation_id,
            user_id,
        )
        return self._row(row)

    async def list_conversations_by_user(
        self,
        user_id: uuid.UUID,
        cursor: str | None = None,
        limit: int = 50,
    ) -> tuple[list[dict[str, Any]], str | None]:
        """Cursor-based conversation list scoped to *user_id*.

        Returns ``(items, next_cursor)``.  *next_cursor* is None when there
        are no more pages.
        """
        limit = max(1, min(limit, 100))
        fetch_n = limit + 1  # over-fetch by one to detect next page

        if cursor:
            decoded = _decode_cursor(cursor)
            if decoded is None:
                decoded = None
            if decoded:
                cursor_ts, cursor_id = decoded
                rows = await self._pool.fetch(
                    """
                    SELECT * FROM ai_conversations
                     WHERE user_id = $1
                       AND (created_at < $2 OR (created_at = $2 AND id < $3))
                     ORDER BY created_at DESC, id DESC
                     LIMIT $4
                    """,
                    user_id,
                    cursor_ts,
                    cursor_id,
                    fetch_n,
                )
            else:
                rows = await self._pool.fetch(
                    """
                    SELECT * FROM ai_conversations
                     WHERE user_id = $1
                     ORDER BY created_at DESC, id DESC
                     LIMIT $2
                    """,
                    user_id,
                    fetch_n,
                )
        else:
            rows = await self._pool.fetch(
                """
                SELECT * FROM ai_conversations
                 WHERE user_id = $1
                 ORDER BY created_at DESC, id DESC
                 LIMIT $2
                """,
                user_id,
                fetch_n,
            )

        items = self._rows(rows)
        next_cursor: str | None = None
        if len(items) > limit:
            items = items[:limit]
            last = items[-1]
            next_cursor = _encode_cursor(last["created_at"], last["id"])

        return items, next_cursor

    async def save_feedback(
        self,
        conversation_id: uuid.UUID,
        message_index: int,
        user_id: uuid.UUID,
        rating: str,
    ) -> dict[str, Any]:
        """Persist a thumbs-up/down rating for a conversation message.

        Uses ON CONFLICT DO UPDATE to allow users to change their rating.
        """
        data: dict[str, Any] = {
            "id": uuid.uuid4(),
            "conversation_id": conversation_id,
            "message_index": message_index,
            "user_id": user_id,
            "rating": rating,
        }
        query, values = self._safe_insert("agent_feedback", _FEEDBACK_ALLOWED_INSERT, data)
        # Replace ON CONFLICT to allow rating updates
        upsert_query = query.replace(
            "RETURNING *",
            "ON CONFLICT (conversation_id, message_index, user_id) "
            "DO UPDATE SET rating = EXCLUDED.rating RETURNING *",
        )
        row = await self._pool.fetchrow(upsert_query, *values)
        return dict(row)

    async def check_ownership(
        self, conversation_id: uuid.UUID, user_id: uuid.UUID
    ) -> bool:
        """Return True if *conversation_id* belongs to *user_id*."""
        row = await self._pool.fetchrow(
            "SELECT id FROM ai_conversations WHERE id = $1 AND user_id = $2",
            conversation_id,
            user_id,
        )
        return row is not None
