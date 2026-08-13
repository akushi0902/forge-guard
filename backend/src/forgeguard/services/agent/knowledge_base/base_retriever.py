"""Abstract BaseRetriever and RetrievalContext for the knowledge base layer (WO-067).

Every domain-specific retriever must implement BaseRetriever.retrieve() and
return a RetrievalContext dataclass with the assembled query results.
"""

from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class RetrievalContext:
    """Structured result returned by a single domain retriever.

    Attributes:
        domain:         Which retriever produced this context (e.g. "health",
                        "findings", "policy", "release").
        data:           Domain-specific payload dict ready for prompt assembly.
        is_empty:       True when the domain has no data for this service/user
                        (e.g. no assessments yet).
        empty_reason:   Human-readable explanation for the empty result.
        is_degraded:    True when the retriever returned partial data due to a
                        transient error.
        degraded_reason: Error detail when is_degraded is True.
        retrieval_time_ms: How long the database query took in milliseconds.
    """

    domain: str
    data: dict[str, Any] = field(default_factory=dict)
    is_empty: bool = False
    empty_reason: str = ""
    is_degraded: bool = False
    degraded_reason: str = ""
    retrieval_time_ms: float = 0.0


class BaseRetriever(ABC):
    """Abstract base class for domain knowledge retrievers.

    Concrete retrievers receive an asyncpg pool and implement the ``retrieve``
    coroutine. All queries must use parameterised statements — no raw string
    interpolation of user-supplied values.
    """

    def __init__(self, pool: Any) -> None:
        self._pool = pool

    @abstractmethod
    async def retrieve(
        self,
        user_id: uuid.UUID,
        service_id: uuid.UUID,
        query_params: dict[str, Any] | None = None,
    ) -> RetrievalContext:
        """Retrieve domain-specific context for the given user and service.

        Args:
            user_id:      Authenticated user UUID (used for ownership scoping).
            service_id:   Target service UUID.
            query_params: Optional retriever-specific filter parameters
                          (e.g. ``{"severity": "critical", "dimension": "security"}``).

        Returns:
            A :class:`RetrievalContext` containing the assembled data, or an
            empty/degraded context if no data is available or an error occurred.
        """
        ...
