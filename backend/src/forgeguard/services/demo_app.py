"""DemoAppService: business logic for mock Payment Service endpoints.

Simulates payment authorization with a 90% approval rate.
No real payment network calls are made — all data is synthetic.
"""

from __future__ import annotations

import json
import random
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

import structlog

from forgeguard.core.exceptions import NotFoundError
from forgeguard.data.repositories.demo_repository import DemoTransactionRepository
from forgeguard.services.mock_data_generator import generate_authorization_code

logger = structlog.get_logger(__name__)

_PAYMENT_SERVICE_ID = uuid.UUID("d0000000-0000-0000-0000-000000000001")
_PAYMENT_SERVICE_VERSION = "1.0.0"
_PAYMENT_SERVICE_CAPABILITIES = [
    "mock-transactions",
    "synthetic-data",
    "governance-demo",
    "release-readiness-demo",
]

# Fraction of transactions that receive an "approved" status.
_APPROVAL_RATE = 0.90


class DemoAppService:
    """Service layer for the mock Payment Service demo application."""

    def __init__(self, repository: DemoTransactionRepository) -> None:
        self._repository = repository

    async def create_transaction(
        self,
        *,
        amount: Decimal,
        currency: str,
        merchant: str,
        card_last_four: str,
    ) -> dict[str, Any]:
        """Simulate a payment authorization and persist the synthetic transaction."""
        tx_id = uuid.uuid4()
        status = "approved" if random.random() < _APPROVAL_RATE else "declined"
        authorization_code = (
            generate_authorization_code() if status == "approved" else None
        )

        data: dict[str, Any] = {
            "id": str(tx_id),
            "amount": float(amount),
            "currency": currency,
            "merchant": merchant,
            "card_last_four": card_last_four,
            "status": status,
            "authorization_code": authorization_code,
            "metadata": json.dumps({"is_simulated": True}),
        }

        row = await self._repository.create(data)
        row["is_simulated"] = True

        logger.info(
            "demo_transaction_created",
            transaction_id=str(tx_id),
            status=status,
            amount=str(amount),
            currency=currency,
        )
        return row

    async def get_transaction(
        self, transaction_id: uuid.UUID
    ) -> dict[str, Any]:
        """Fetch a single demo transaction by UUID."""
        row = await self._repository.get_by_id(transaction_id)
        if row is None:
            raise NotFoundError(
                f"Transaction {transaction_id} not found.",
                details={"transaction_id": str(transaction_id)},
            )
        row["is_simulated"] = True
        return row

    async def get_service_info(self) -> dict[str, Any]:
        """Return Payment Service metadata from the services table."""
        service = await self._repository.get_demo_service_info()
        if service is None:
            return {
                "id": _PAYMENT_SERVICE_ID,
                "name": "ForgeGuard Payment Service",
                "description": (
                    "Mock payment processing service for governance demonstration."
                ),
                "version": _PAYMENT_SERVICE_VERSION,
                "is_demo": True,
                "capabilities": _PAYMENT_SERVICE_CAPABILITIES,
                "health_score": None,
                "last_evaluated": None,
            }

        meta = service.get("metadata") or {}
        if isinstance(meta, str):
            try:
                meta = json.loads(meta)
            except (json.JSONDecodeError, TypeError):
                meta = {}

        return {
            "id": service["id"],
            "name": service["name"],
            "description": service.get("description") or "",
            "version": meta.get("version", _PAYMENT_SERVICE_VERSION),
            "is_demo": bool(service.get("is_demo", True)),
            "capabilities": meta.get("capabilities", _PAYMENT_SERVICE_CAPABILITIES),
            "health_score": None,
            "last_evaluated": None,
        }

    async def reset_demo_data(self) -> dict[str, Any]:
        """Delete all demo transactions and return a reset confirmation."""
        count = await self._repository.delete_all_demo_transactions()
        reset_at = datetime.now(tz=timezone.utc)

        logger.info("demo_data_reset", purged_count=count)
        return {
            "purged_count": count,
            "message": (
                f"Demo data reset complete. {count} transaction(s) purged."
            ),
            "reset_at": reset_at,
        }
