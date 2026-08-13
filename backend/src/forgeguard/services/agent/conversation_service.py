"""ConversationService: AI agent conversation orchestration (WO-065, WO-067).

Pipeline for POST /api/v1/agent/query:
    1. Classify query intent
    2. Load or create conversation
    3. Retrieve context via ContextAssembler (WO-067)
    4. Build LLM prompt with history + context
    5. Call AI engine (with circuit-breaker fallback to template)
    6. Persist new messages atomically
    7. Write audit record
    8. Return AgentQueryResponse
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

import structlog

from forgeguard.api.schemas.agent import (
    AgentFeedbackResponse,
    AgentQueryResponse,
    ContextReference,
    ConversationListResponse,
    ConversationSummary,
)
from forgeguard.core.exceptions import ForbiddenError, NotFoundError
from forgeguard.services.agent.intent_classifier import IntentCategory, IntentClassifier
from forgeguard.services.agent.knowledge_base.context_assembler import ContextAssembler
from forgeguard.services.agent.prompt_builder import PromptBuilder
from forgeguard.services.ai_engine.errors import CircuitOpenError

logger = structlog.get_logger(__name__)

_FALLBACK_ANSWER = (
    "I'm temporarily unable to generate a detailed response — the AI service is "
    "unavailable. Please try again shortly, or consult the ForgeGuard dashboard "
    "for direct data access."
)
_FALLBACK_CONFIDENCE: float = 0.1


def _make_preview(messages: list[Any]) -> str:
    """Extract a short preview from the first user message."""
    for msg in messages:
        if isinstance(msg, dict) and msg.get("role") == "user":
            content = str(msg.get("content", ""))
            return content[:120] + ("…" if len(content) > 120 else "")
    return "(empty conversation)"


class ConversationService:
    """Orchestrates the full AI agent conversation lifecycle."""

    def __init__(
        self,
        *,
        agent_repo: Any,
        ai_engine: Any,
        audit_svc: Any,
        context_assembler: ContextAssembler | None = None,
    ) -> None:
        self._repo = agent_repo
        self._ai = ai_engine
        self._audit = audit_svc
        self._classifier = IntentClassifier()
        self._prompt_builder = PromptBuilder()
        self._context_assembler: ContextAssembler | None = context_assembler

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------

    async def handle_query(
        self,
        query: str,
        *,
        user_id: uuid.UUID,
        actor_role: str,
        conversation_id: uuid.UUID | None = None,
        service_id: uuid.UUID | None = None,
        query_params: dict[str, Any] | None = None,
    ) -> AgentQueryResponse:
        """Process a user query and return a structured response."""
        now = datetime.now(tz=timezone.utc)

        # ── 1. Classify intent ──────────────────────────────────────────
        intent: IntentCategory = self._classifier.classify(query)

        # ── 2. Load or create conversation ─────────────────────────────
        history: list[Any] = []
        if conversation_id is not None:
            conv = await self._repo.get_conversation_by_id(conversation_id)
            if conv is None:
                raise NotFoundError(f"Conversation {conversation_id} not found.")
            # Ownership check
            if conv.get("user_id") != user_id:
                raise ForbiddenError(
                    "You do not have access to this conversation.",
                    required_permission="agent.conversations.view",
                )
            messages = conv.get("messages") or []
            if isinstance(messages, str):
                import json  # noqa: PLC0415
                messages = json.loads(messages)
            history = messages
        else:
            conv = await self._repo.create_conversation(user_id)
            conversation_id = conv["id"]

        # ── 3. Context retrieval via ContextAssembler (WO-067) ────────────
        context_refs: list[ContextReference] = []
        context_bundle_dict: dict[str, Any] = {}

        if self._context_assembler is not None:
            try:
                bundle = await self._context_assembler.assemble(
                    user_id=user_id,
                    actor_role=actor_role,
                    intent=intent,
                    service_id=service_id,
                    query_params=query_params,
                )
                context_bundle_dict = bundle.to_prompt_dict()
                # Build ContextReference entries from domains that returned data.
                for domain in ("health", "findings", "policy", "release"):
                    ctx = getattr(bundle, domain, None)
                    if ctx is not None and not ctx.is_empty and not ctx.is_degraded:
                        context_refs.append(
                            ContextReference(
                                type=f"{domain}_retriever",
                                id=str(service_id) if service_id else "global",
                                title=f"{domain.capitalize()} data for service",
                            )
                        )
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "agent.query.context_assembly_failed",
                    conversation_id=str(conversation_id),
                    error=str(exc),
                )

        # ── 4. Build prompt ────────────────────────────────────────────
        prompt = self._prompt_builder.build(
            query=query,
            intent=intent,
            history=history,
            context=[c.model_dump() for c in context_refs],
            knowledge_base=context_bundle_dict,
        )

        # ── 5. Call AI engine with circuit-breaker fallback ───────────
        is_template_fallback = False
        answer = _FALLBACK_ANSWER
        confidence = _FALLBACK_CONFIDENCE

        try:
            llm_resp = await self._ai.generate_completion(
                prompt,
                params={
                    "intent": intent.value,
                    "conversation_id": str(conversation_id),
                    "service_id": str(service_id) if service_id else None,
                },
            )
            answer = llm_resp.content
            confidence = float(llm_resp.confidence_score or 0.8)
            is_template_fallback = llm_resp.source.name == "TEMPLATE_GENERATED"
        except CircuitOpenError:
            is_template_fallback = True
            logger.warning(
                "agent.query.circuit_open",
                conversation_id=str(conversation_id),
                intent=intent.value,
            )
        except Exception as exc:  # noqa: BLE001
            is_template_fallback = True
            logger.warning(
                "agent.query.llm_error",
                conversation_id=str(conversation_id),
                error=str(exc),
            )

        # ── 6. Persist messages ────────────────────────────────────────
        user_message = {"role": "user", "content": query, "intent": intent.value, "ts": now.isoformat()}
        assistant_message = {
            "role": "assistant",
            "content": answer,
            "confidence": confidence,
            "is_template_fallback": is_template_fallback,
            "ts": datetime.now(tz=timezone.utc).isoformat(),
        }
        try:
            await self._repo.append_message(conversation_id, user_id, user_message)
            await self._repo.append_message(conversation_id, user_id, assistant_message)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "agent.query.persist_failed",
                conversation_id=str(conversation_id),
                error=str(exc),
            )

        # ── 7. Audit record ────────────────────────────────────────────
        try:
            await self._audit.log_event(
                actor_id=user_id,
                actor_role=actor_role,
                action="agent.query",
                resource_type="ai_conversations",
                resource_id=conversation_id,
                after_state={
                    "intent": intent.value,
                    "is_template_fallback": is_template_fallback,
                    "confidence": confidence,
                },
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("agent.query.audit_failed", error=str(exc))

        return AgentQueryResponse(
            answer=answer,
            confidence=confidence,
            context_refs=context_refs,
            conversation_id=conversation_id,
            is_template_fallback=is_template_fallback,
            created_at=now,
        )

    # ------------------------------------------------------------------
    # Conversation list
    # ------------------------------------------------------------------

    async def list_conversations(
        self,
        user_id: uuid.UUID,
        cursor: str | None = None,
        limit: int = 50,
    ) -> ConversationListResponse:
        """Return paginated conversations for *user_id*."""
        items_raw, next_cursor = await self._repo.list_conversations_by_user(
            user_id, cursor=cursor, limit=limit
        )

        items: list[ConversationSummary] = []
        for row in items_raw:
            messages = row.get("messages") or []
            if isinstance(messages, str):
                import json  # noqa: PLC0415
                messages = json.loads(messages)
            items.append(
                ConversationSummary(
                    id=row["id"],
                    preview=_make_preview(messages),
                    message_count=len(messages),
                    created_at=row["created_at"],
                    updated_at=row["updated_at"],
                )
            )

        return ConversationListResponse(items=items, next_cursor=next_cursor)

    # ------------------------------------------------------------------
    # Feedback
    # ------------------------------------------------------------------

    async def save_feedback(
        self,
        conversation_id: uuid.UUID,
        message_index: int,
        user_id: uuid.UUID,
        rating: str,
    ) -> AgentFeedbackResponse:
        """Persist a thumbs rating and verify conversation ownership."""
        conv = await self._repo.get_conversation_by_id(conversation_id)
        if conv is None:
            raise NotFoundError(f"Conversation {conversation_id} not found.")
        if conv.get("user_id") != user_id:
            raise ForbiddenError(
                "You do not have access to this conversation.",
                required_permission="agent.conversations.view",
            )

        await self._repo.save_feedback(
            conversation_id=conversation_id,
            message_index=message_index,
            user_id=user_id,
            rating=rating,
        )
        return AgentFeedbackResponse(status="recorded")
