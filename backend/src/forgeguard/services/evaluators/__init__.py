"""Abstract base class for rule evaluators (WO-038).

Each concrete evaluator implements the strategy pattern for one rule_type.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class RuleEvaluator(ABC):
    """Abstract base for strategy-pattern rule evaluators.

    Concrete subclasses implement evaluate() for a single rule_type.
    All methods are async to allow asyncio.wait_for timeout enforcement.
    """

    @abstractmethod
    async def evaluate(self, rule: Any, input_data: dict[str, Any]) -> Any:
        """Evaluate one rule against input_data and return a RuleEvaluationResult."""
        ...
