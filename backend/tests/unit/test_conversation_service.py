"""Unit tests for ConversationService (WO-065).

Tests cover the full orchestration flow, circuit breaker fallback,
error handling paths, feedback, and conversation list logic.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from forgeguard.api.schemas.agent import AgentQueryResponse, ConversationListResponse
from forgeguard.core.exceptions import ForbiddenError, NotFoundError
from forgeguard.services.agent.conversation_service import ConversationService
from forgeguard.services.ai_engine.errors import CircuitOpenError
from forgeguard.services.ai_engine.models import LLMResponse, ResponseSource

_USER_ID = uuid.UUID("a1000000-0000-0000-0000-000000000001")
_CONV_ID = uuid.UUID("b1000000-0000-0000-0000-000000000001")

_NOW = datetime(2026, 8, 12, tzinfo=timezone.utc)


def _mock_conversation(user_id=_USER_ID, messages=None):
    return {
        "id": _CONV_ID,
        "user_id": user_id,
        "messages": messages or [],
        "context_refs": [],
        "created_at": _NOW,
        "updated_at": _NOW,
    }


def _mock_llm_response(content="Test answer", confidence=0.85):
    return LLMResponse(
        content=content,
        confidence_score=confidence,
        source=ResponseSource.AI_GENERATED,
        model="test",
        tokens_used=100,
        latency_ms=200,
        cached=False,
    )


def _make_svc(*, repo=None, ai=None, audit=None):
    repo = repo or MagicMock()
    ai = ai or MagicMock()
    audit = audit or MagicMock()
    audit.log_event = AsyncMock(return_value=None)
    return ConversationService(agent_repo=repo, ai_engine=ai, audit_svc=audit)


# ---------------------------------------------------------------------------
# New conversation creation
# ---------------------------------------------------------------------------

class TestNewConversation:
    @pytest.mark.asyncio
    async def test_creates_conversation_when_no_id(self):
        repo = MagicMock()
        repo.create_conversation = AsyncMock(return_value=_mock_conversation())
        repo.append_message = AsyncMock(return_value=_mock_conversation())
        ai = MagicMock()
        ai.generate_completion = AsyncMock(return_value=_mock_llm_response())
        svc = _make_svc(repo=repo, ai=ai)

        result = await svc.handle_query("What is my health score?", user_id=_USER_ID, actor_role="developer")

        repo.create_conversation.assert_awaited_once_with(_USER_ID)
        assert isinstance(result, AgentQueryResponse)

    @pytest.mark.asyncio
    async def test_response_has_conversation_id(self):
        repo = MagicMock()
        repo.create_conversation = AsyncMock(return_value=_mock_conversation())
        repo.append_message = AsyncMock(return_value=_mock_conversation())
        ai = MagicMock()
        ai.generate_completion = AsyncMock(return_value=_mock_llm_response())
        svc = _make_svc(repo=repo, ai=ai)

        result = await svc.handle_query("Show findings", user_id=_USER_ID, actor_role="developer")
        assert result.conversation_id == _CONV_ID


# ---------------------------------------------------------------------------
# Existing conversation continuation
# ---------------------------------------------------------------------------

class TestExistingConversation:
    @pytest.mark.asyncio
    async def test_loads_existing_conversation(self):
        repo = MagicMock()
        repo.get_conversation_by_id = AsyncMock(return_value=_mock_conversation())
        repo.append_message = AsyncMock(return_value=_mock_conversation())
        ai = MagicMock()
        ai.generate_completion = AsyncMock(return_value=_mock_llm_response())
        svc = _make_svc(repo=repo, ai=ai)

        result = await svc.handle_query(
            "Tell me more",
            user_id=_USER_ID,
            actor_role="developer",
            conversation_id=_CONV_ID,
        )
        repo.get_conversation_by_id.assert_awaited_once_with(_CONV_ID)
        assert isinstance(result, AgentQueryResponse)

    @pytest.mark.asyncio
    async def test_not_found_raises_404(self):
        repo = MagicMock()
        repo.get_conversation_by_id = AsyncMock(return_value=None)
        svc = _make_svc(repo=repo)

        with pytest.raises(NotFoundError):
            await svc.handle_query(
                "Hello",
                user_id=_USER_ID,
                actor_role="developer",
                conversation_id=_CONV_ID,
            )

    @pytest.mark.asyncio
    async def test_other_user_conversation_raises_403(self):
        other_user = uuid.UUID("c1000000-0000-0000-0000-000000000001")
        repo = MagicMock()
        repo.get_conversation_by_id = AsyncMock(
            return_value=_mock_conversation(user_id=other_user)
        )
        svc = _make_svc(repo=repo)

        with pytest.raises(ForbiddenError):
            await svc.handle_query(
                "Hello",
                user_id=_USER_ID,
                actor_role="developer",
                conversation_id=_CONV_ID,
            )


# ---------------------------------------------------------------------------
# Circuit breaker fallback
# ---------------------------------------------------------------------------

class TestCircuitBreakerFallback:
    @pytest.mark.asyncio
    async def test_circuit_open_returns_template_response(self):
        repo = MagicMock()
        repo.create_conversation = AsyncMock(return_value=_mock_conversation())
        repo.append_message = AsyncMock(return_value=_mock_conversation())
        ai = MagicMock()
        ai.generate_completion = AsyncMock(side_effect=CircuitOpenError("Circuit open"))
        svc = _make_svc(repo=repo, ai=ai)

        result = await svc.handle_query("Health score?", user_id=_USER_ID, actor_role="developer")

        assert result.is_template_fallback is True
        assert result.answer is not None
        assert result.confidence < 0.5

    @pytest.mark.asyncio
    async def test_llm_error_returns_fallback(self):
        repo = MagicMock()
        repo.create_conversation = AsyncMock(return_value=_mock_conversation())
        repo.append_message = AsyncMock(return_value=_mock_conversation())
        ai = MagicMock()
        ai.generate_completion = AsyncMock(side_effect=RuntimeError("LLM unavailable"))
        svc = _make_svc(repo=repo, ai=ai)

        result = await svc.handle_query("Health score?", user_id=_USER_ID, actor_role="developer")

        assert result.is_template_fallback is True

    @pytest.mark.asyncio
    async def test_successful_call_not_fallback(self):
        repo = MagicMock()
        repo.create_conversation = AsyncMock(return_value=_mock_conversation())
        repo.append_message = AsyncMock(return_value=_mock_conversation())
        ai = MagicMock()
        ai.generate_completion = AsyncMock(return_value=_mock_llm_response(content="Real answer"))
        svc = _make_svc(repo=repo, ai=ai)

        result = await svc.handle_query("Health score?", user_id=_USER_ID, actor_role="developer")

        assert result.is_template_fallback is False
        assert result.answer == "Real answer"


# ---------------------------------------------------------------------------
# Message persistence
# ---------------------------------------------------------------------------

class TestMessagePersistence:
    @pytest.mark.asyncio
    async def test_persists_two_messages(self):
        repo = MagicMock()
        repo.create_conversation = AsyncMock(return_value=_mock_conversation())
        repo.append_message = AsyncMock(return_value=_mock_conversation())
        ai = MagicMock()
        ai.generate_completion = AsyncMock(return_value=_mock_llm_response())
        svc = _make_svc(repo=repo, ai=ai)

        await svc.handle_query("Test", user_id=_USER_ID, actor_role="developer")

        # User message + assistant message = 2 appends
        assert repo.append_message.await_count == 2

    @pytest.mark.asyncio
    async def test_persist_failure_does_not_raise(self):
        repo = MagicMock()
        repo.create_conversation = AsyncMock(return_value=_mock_conversation())
        repo.append_message = AsyncMock(side_effect=Exception("DB error"))
        ai = MagicMock()
        ai.generate_completion = AsyncMock(return_value=_mock_llm_response())
        svc = _make_svc(repo=repo, ai=ai)

        # Should not raise despite DB failure
        result = await svc.handle_query("Test", user_id=_USER_ID, actor_role="developer")
        assert isinstance(result, AgentQueryResponse)


# ---------------------------------------------------------------------------
# Audit logging
# ---------------------------------------------------------------------------

class TestAuditLogging:
    @pytest.mark.asyncio
    async def test_audit_event_written(self):
        repo = MagicMock()
        repo.create_conversation = AsyncMock(return_value=_mock_conversation())
        repo.append_message = AsyncMock(return_value=_mock_conversation())
        ai = MagicMock()
        ai.generate_completion = AsyncMock(return_value=_mock_llm_response())
        audit = MagicMock()
        audit.log_event = AsyncMock(return_value=None)
        svc = _make_svc(repo=repo, ai=ai, audit=audit)

        await svc.handle_query("Test", user_id=_USER_ID, actor_role="developer")

        audit.log_event.assert_awaited_once()
        call_kwargs = audit.log_event.call_args.kwargs
        assert call_kwargs["action"] == "agent.query"
        assert call_kwargs["actor_id"] == _USER_ID

    @pytest.mark.asyncio
    async def test_audit_failure_does_not_raise(self):
        repo = MagicMock()
        repo.create_conversation = AsyncMock(return_value=_mock_conversation())
        repo.append_message = AsyncMock(return_value=_mock_conversation())
        ai = MagicMock()
        ai.generate_completion = AsyncMock(return_value=_mock_llm_response())
        audit = MagicMock()
        audit.log_event = AsyncMock(side_effect=Exception("Audit DB down"))
        svc = _make_svc(repo=repo, ai=ai, audit=audit)

        result = await svc.handle_query("Test", user_id=_USER_ID, actor_role="developer")
        assert isinstance(result, AgentQueryResponse)


# ---------------------------------------------------------------------------
# Conversation list
# ---------------------------------------------------------------------------

class TestConversationList:
    @pytest.mark.asyncio
    async def test_list_returns_summary(self):
        repo = MagicMock()
        repo.list_conversations_by_user = AsyncMock(
            return_value=(
                [_mock_conversation(messages=[{"role": "user", "content": "Hello there"}])],
                None,
            )
        )
        svc = _make_svc(repo=repo)

        result = await svc.list_conversations(_USER_ID)

        assert isinstance(result, ConversationListResponse)
        assert len(result.items) == 1
        assert "Hello there" in result.items[0].preview

    @pytest.mark.asyncio
    async def test_list_empty_returns_no_cursor(self):
        repo = MagicMock()
        repo.list_conversations_by_user = AsyncMock(return_value=([], None))
        svc = _make_svc(repo=repo)

        result = await svc.list_conversations(_USER_ID)

        assert result.items == []
        assert result.next_cursor is None


# ---------------------------------------------------------------------------
# Feedback
# ---------------------------------------------------------------------------

class TestFeedback:
    @pytest.mark.asyncio
    async def test_feedback_recorded(self):
        repo = MagicMock()
        repo.get_conversation_by_id = AsyncMock(return_value=_mock_conversation())
        repo.save_feedback = AsyncMock(return_value={"id": uuid.uuid4(), "rating": "thumbs_up"})
        svc = _make_svc(repo=repo)

        result = await svc.save_feedback(_CONV_ID, 1, _USER_ID, "thumbs_up")

        assert result.status == "recorded"
        repo.save_feedback.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_feedback_on_missing_conversation_raises(self):
        repo = MagicMock()
        repo.get_conversation_by_id = AsyncMock(return_value=None)
        svc = _make_svc(repo=repo)

        with pytest.raises(NotFoundError):
            await svc.save_feedback(_CONV_ID, 0, _USER_ID, "thumbs_down")

    @pytest.mark.asyncio
    async def test_feedback_on_other_user_conversation_raises(self):
        other = uuid.UUID("c2000000-0000-0000-0000-000000000001")
        repo = MagicMock()
        repo.get_conversation_by_id = AsyncMock(
            return_value=_mock_conversation(user_id=other)
        )
        svc = _make_svc(repo=repo)

        with pytest.raises(ForbiddenError):
            await svc.save_feedback(_CONV_ID, 0, _USER_ID, "thumbs_up")
