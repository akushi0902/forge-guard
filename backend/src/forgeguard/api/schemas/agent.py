"""Pydantic request/response schemas for the AI Agent API (WO-065)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Any, Literal, Optional

from pydantic import Field, field_validator

from forgeguard.core.validation import ForgeGuardBaseModel


class ContextReference(ForgeGuardBaseModel):
    """A domain entity referenced in an AI agent response."""

    type: str
    id: str
    title: str


class AgentQueryRequest(ForgeGuardBaseModel):
    """Request body for POST /api/v1/agent/query."""

    query: Annotated[str, Field(min_length=1, max_length=2000)]
    conversation_id: Optional[uuid.UUID] = None
    service_id: Optional[uuid.UUID] = None

    @field_validator("query")
    @classmethod
    def query_not_whitespace(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("query must not be empty or whitespace-only")
        return v


class AgentQueryResponse(ForgeGuardBaseModel):
    """Response for POST /api/v1/agent/query."""

    answer: str
    confidence: float
    context_refs: list[ContextReference]
    conversation_id: uuid.UUID
    is_template_fallback: bool
    created_at: datetime


class ConversationSummary(ForgeGuardBaseModel):
    """Single conversation entry in the list response."""

    id: uuid.UUID
    preview: str
    message_count: int
    created_at: datetime
    updated_at: datetime


class ConversationListResponse(ForgeGuardBaseModel):
    """Response for GET /api/v1/agent/conversations."""

    items: list[ConversationSummary]
    next_cursor: Optional[str] = None


class AgentFeedbackRequest(ForgeGuardBaseModel):
    """Request body for POST /api/v1/agent/query/feedback."""

    conversation_id: uuid.UUID
    message_index: Annotated[int, Field(ge=0)]
    rating: Literal["thumbs_up", "thumbs_down"]


class AgentFeedbackResponse(ForgeGuardBaseModel):
    """Response for POST /api/v1/agent/query/feedback."""

    status: Literal["recorded"] = "recorded"
