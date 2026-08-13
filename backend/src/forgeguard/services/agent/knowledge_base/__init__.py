"""Knowledge base retrieval layer for the AI agent (WO-067).

Provides intent-aware, ownership-scoped, performance-optimized data retrieval
across all domain tables. Given a classified intent and authenticated user
context, assembles a structured ContextBundle for LLM prompt generation.
"""

from forgeguard.services.agent.knowledge_base.base_retriever import (
    BaseRetriever,
    RetrievalContext,
)
from forgeguard.services.agent.knowledge_base.context_assembler import (
    ContextAssembler,
    ContextBundle,
)
from forgeguard.services.agent.knowledge_base.service_access_resolver import (
    ServiceAccessResolver,
)

__all__ = [
    "BaseRetriever",
    "RetrievalContext",
    "ContextAssembler",
    "ContextBundle",
    "ServiceAccessResolver",
]
