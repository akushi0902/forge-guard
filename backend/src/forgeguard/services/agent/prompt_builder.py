"""Conversation-aware prompt builder for the AI agent (WO-065).

Constructs the final LLM prompt from: system instructions, conversation
history (truncated to token budget), retrieved context, and the user query.
"""

from __future__ import annotations

from typing import Any

from forgeguard.services.agent.intent_classifier import IntentCategory

_SYSTEM_PROMPT = (
    "You are ForgeGuard, an AI assistant for software engineering governance. "
    "You help developers, tech leads, and engineering managers understand their "
    "service health scores, policy violations, remediation guidance, and release "
    "readiness. Answer concisely and factually based on the provided context. "
    "If specific data is not available, say so clearly rather than guessing."
)

_INTENT_CONTEXT: dict[IntentCategory, str] = {
    IntentCategory.HEALTH_SCORE: (
        "The user is asking about Engineering Health Scores. Focus on the overall "
        "score, dimension breakdown (code_quality, test_coverage, security, "
        "documentation, operations_readiness), and what is driving changes."
    ),
    IntentCategory.FINDINGS: (
        "The user is asking about policy findings or violations. Focus on active "
        "findings, their severities (critical, high, medium, low), affected "
        "dimensions, and the evidence behind each finding."
    ),
    IntentCategory.REMEDIATION: (
        "The user needs help fixing a policy violation. Provide specific, actionable "
        "remediation steps. Include code examples if relevant. Refer to the "
        "implementation guide in the context."
    ),
    IntentCategory.RELEASE_STATUS: (
        "The user is asking about release readiness. Focus on the release decision "
        "(APPROVE, CONDITIONAL_APPROVE, or BLOCK), the Release Risk Score, and any "
        "blocking findings that must be resolved before release."
    ),
    IntentCategory.POLICY_RULES: (
        "The user is asking about policy rules or configuration. Focus on active "
        "rules, their thresholds, dimensions, severity levels, and weights."
    ),
    IntentCategory.GENERAL_HELP: (
        "The user has a general question about ForgeGuard. Provide a helpful "
        "overview of the platform's capabilities and guide them to the relevant feature."
    ),
}

# Maximum number of historical messages to include (to stay within token budget).
_MAX_HISTORY_MESSAGES = 10


class PromptBuilder:
    """Builds structured prompts for the AI agent conversation endpoint."""

    def build(
        self,
        query: str,
        intent: IntentCategory,
        history: list[dict[str, Any]],
        context: list[dict[str, Any]] | None = None,
        service_context: str | None = None,
    ) -> str:
        """Assemble a complete LLM prompt.

        Args:
            query:           The user's current query.
            intent:          Classified intent for context injection.
            history:         Previous messages in this conversation.
            context:         Retrieved domain context (services, findings, etc.).
            service_context: Optional pre-formatted service info string.

        Returns:
            A single string prompt ready to pass to the LLM.
        """
        parts: list[str] = []

        # System instructions
        parts.append(f"[SYSTEM]\n{_SYSTEM_PROMPT}")
        parts.append(f"\n[INTENT CONTEXT]\n{_INTENT_CONTEXT.get(intent, '')}")

        # Domain context from retrieval
        if context:
            context_lines = []
            for item in context[:10]:  # cap at 10 items
                context_lines.append(
                    f"- {item.get('type', 'item')}: {item.get('title', '')} "
                    f"(id={item.get('id', 'unknown')})"
                )
            if context_lines:
                parts.append("\n[RETRIEVED CONTEXT]\n" + "\n".join(context_lines))

        if service_context:
            parts.append(f"\n[SERVICE DATA]\n{service_context}")

        # Conversation history (most recent _MAX_HISTORY_MESSAGES)
        recent = history[-_MAX_HISTORY_MESSAGES:] if history else []
        if recent:
            hist_lines = []
            for msg in recent:
                role = msg.get("role", "user")
                content = msg.get("content", "")
                hist_lines.append(f"{role.upper()}: {content}")
            parts.append("\n[CONVERSATION HISTORY]\n" + "\n".join(hist_lines))

        # Current query
        parts.append(f"\n[USER QUERY]\n{query}")
        parts.append("\n[ASSISTANT RESPONSE]")

        return "\n".join(parts)
