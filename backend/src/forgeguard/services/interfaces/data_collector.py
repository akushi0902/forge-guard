"""DataCollector abstract interface (WO-042).

Defines the contract for collecting normalized service data that the rule
evaluation engine will use as input.  Implement a concrete subclass for each
data source (mock, GitHub API, CI platform, etc.) and inject via FastAPI
Depends().

The MVP uses MockDataCollector; real adapters replace it without changing the
orchestration layer.
"""

from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from typing import Any


class DataCollector(ABC):
    """Abstract data collector for the health assessment pipeline.

    Implementations must be async-safe and stateless (or thread-safe if stateful).
    The return value is a flat dict whose keys are the ``data_key`` values
    referenced in policy rule ``threshold_config`` fields.
    """

    @abstractmethod
    async def collect(self, service_id: uuid.UUID) -> dict[str, Any]:
        """Collect normalized input data for the given service.

        Args:
            service_id: UUID of the service being assessed.

        Returns:
            A flat dict mapping data-key strings to their current values.
            Example::

                {
                    "unit_test_coverage": 62.5,
                    "dependency_vulnerabilities": 7,
                    "has_readme": False,
                    "cyclomatic_complexity_avg": 8.2,
                }

        Raises:
            Exception: Any exception propagates to the orchestrator, which sets
                the assessment status to 'failed'.
        """
        ...
