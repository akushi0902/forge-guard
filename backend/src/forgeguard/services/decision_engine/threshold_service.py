"""DecisionThresholdService: business logic for threshold CRUD (WO-049).

Wraps DecisionThresholdRepository with business-rule validation:
  - approve_health_min must be > conditional_health_min
  - approve_risk_max must be < conditional_risk_max
  - All threshold values must be in [0, 100]

The active threshold is not cached here — the engine resolves it per-call.
For production latency requirements the caller may pre-load it once.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

import structlog

from forgeguard.data.repositories.decision_threshold_repository import (
    DecisionThresholdRepository,
)
from forgeguard.services.decision_engine.engine import DEFAULT_THRESHOLDS

logger = structlog.get_logger(__name__)

_DEFAULT_SEED_ID = uuid.UUID("f0000000-0000-0000-0000-000000000001")
_DEFAULT_SEED_NAME = "Default Threshold"


class ThresholdValidationError(ValueError):
    """Raised when threshold values violate business rules."""


def _validate_thresholds(data: dict[str, Any]) -> None:
    """Raise ThresholdValidationError if *data* violates threshold business rules."""
    fields = (
        "approve_health_min",
        "approve_risk_max",
        "conditional_health_min",
        "conditional_risk_max",
    )
    for f in fields:
        if f in data:
            v = Decimal(str(data[f]))
            if not (Decimal("0") <= v <= Decimal("100")):
                raise ThresholdValidationError(
                    f"{f} must be in [0, 100], got {v}"
                )

    # Approve must be stricter than conditional (if both present in data).
    approve_h = data.get("approve_health_min")
    cond_h = data.get("conditional_health_min")
    if approve_h is not None and cond_h is not None:
        if Decimal(str(approve_h)) <= Decimal(str(cond_h)):
            raise ThresholdValidationError(
                "approve_health_min must be strictly greater than "
                "conditional_health_min"
            )

    approve_r = data.get("approve_risk_max")
    cond_r = data.get("conditional_risk_max")
    if approve_r is not None and cond_r is not None:
        if Decimal(str(approve_r)) >= Decimal(str(cond_r)):
            raise ThresholdValidationError(
                "approve_risk_max must be strictly less than "
                "conditional_risk_max"
            )


class DecisionThresholdService:
    """Business logic layer for decision threshold management."""

    def __init__(self, repo: DecisionThresholdRepository) -> None:
        self._repo = repo

    # ------------------------------------------------------------------
    # Read operations
    # ------------------------------------------------------------------

    async def get_by_id(self, id: str | uuid.UUID) -> dict[str, Any] | None:
        return await self._repo.get_by_id(id)

    async def get_active(self) -> dict[str, Any] | None:
        """Return the active threshold config, logging a warning if absent."""
        config = await self._repo.get_active()
        if config is None:
            logger.warning(
                "decision_engine.no_active_threshold",
                message="No active threshold configuration found — using hardcoded defaults",
                defaults={k: str(v) for k, v in DEFAULT_THRESHOLDS.items()},
            )
        return config

    async def list_all(
        self,
        *,
        cursor: str | None = None,
        limit: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        """Return (page, total_count) for the thresholds list endpoint."""
        rows = await self._repo.list(cursor=cursor, limit=limit)
        total = await self._repo.count_all()
        return rows, total

    # ------------------------------------------------------------------
    # Write operations
    # ------------------------------------------------------------------

    async def create(
        self,
        data: dict[str, Any],
        *,
        actor_id: str | uuid.UUID | None = None,
    ) -> dict[str, Any]:
        _validate_thresholds(data)
        payload: dict[str, Any] = {
            "name": data["name"],
            "approve_health_min": Decimal(str(data.get("approve_health_min", DEFAULT_THRESHOLDS["approve_health_min"]))),
            "approve_risk_max": Decimal(str(data.get("approve_risk_max", DEFAULT_THRESHOLDS["approve_risk_max"]))),
            "conditional_health_min": Decimal(str(data.get("conditional_health_min", DEFAULT_THRESHOLDS["conditional_health_min"]))),
            "conditional_risk_max": Decimal(str(data.get("conditional_risk_max", DEFAULT_THRESHOLDS["conditional_risk_max"]))),
            "is_active": False,
        }
        if actor_id is not None:
            payload["created_by"] = uuid.UUID(str(actor_id))
            payload["updated_by"] = uuid.UUID(str(actor_id))
        return await self._repo.create(payload)

    async def update(
        self,
        id: str | uuid.UUID,
        data: dict[str, Any],
        *,
        actor_id: str | uuid.UUID | None = None,
    ) -> dict[str, Any] | None:
        existing = await self._repo.get_by_id(id)
        if existing is None:
            return None

        # Merge existing values with updates for cross-field validation.
        merged: dict[str, Any] = {}
        for field in (
            "approve_health_min",
            "approve_risk_max",
            "conditional_health_min",
            "conditional_risk_max",
        ):
            merged[field] = data.get(field, existing.get(field))
        _validate_thresholds(merged)

        payload = {k: v for k, v in data.items() if k in (
            "name",
            "approve_health_min",
            "approve_risk_max",
            "conditional_health_min",
            "conditional_risk_max",
        )}
        if actor_id is not None:
            payload["updated_by"] = uuid.UUID(str(actor_id))
        return await self._repo.update(id, payload)

    async def activate(
        self,
        id: str | uuid.UUID,
        *,
        actor_id: str | uuid.UUID | None = None,
    ) -> dict[str, Any] | None:
        row = await self._repo.activate(id)
        if row and actor_id is not None:
            await self._repo.update(id, {"updated_by": uuid.UUID(str(actor_id))})
            row = await self._repo.get_by_id(id)
        return row

    async def deactivate(
        self,
        id: str | uuid.UUID,
        *,
        actor_id: str | uuid.UUID | None = None,
    ) -> dict[str, Any] | None:
        return await self._repo.deactivate(id)

    # ------------------------------------------------------------------
    # Startup seed
    # ------------------------------------------------------------------

    async def seed_defaults_if_absent(self) -> bool:
        """Seed the default threshold config if no active config exists.

        Returns True if a seed was performed, False if one already existed.
        """
        active = await self._repo.get_active()
        if active is not None:
            return False

        # Check if the well-known default row exists (idempotent).
        existing = await self._repo.get_by_id(_DEFAULT_SEED_ID)
        if existing is None:
            await self._repo.create({
                "id": _DEFAULT_SEED_ID,
                "name": _DEFAULT_SEED_NAME,
                "approve_health_min": DEFAULT_THRESHOLDS["approve_health_min"],
                "approve_risk_max": DEFAULT_THRESHOLDS["approve_risk_max"],
                "conditional_health_min": DEFAULT_THRESHOLDS["conditional_health_min"],
                "conditional_risk_max": DEFAULT_THRESHOLDS["conditional_risk_max"],
                "is_active": True,
            })
        else:
            # Row exists but is not active — activate it.
            await self._repo.activate(_DEFAULT_SEED_ID)

        logger.info(
            "decision_engine.default_thresholds_seeded",
            threshold_id=str(_DEFAULT_SEED_ID),
        )
        return True
