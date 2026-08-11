"""Faker-based factory functions for demo test data generation.

All factories use a fixed seed (42) for deterministic assertions.
Pass a different seed to generate distinct but reproducible data sets.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from forgeguard.services.mock_data_generator import (
    generate_authorization_code,
    generate_card_last_four,
    generate_currency_code,
    generate_merchant_name,
    generate_transaction_amount,
    make_faker,
)

_DEFAULT_SEED = 42


def make_transaction_create_body(
    *,
    amount: str | None = None,
    currency: str | None = None,
    merchant: str | None = None,
    card_last_four: str | None = None,
    seed: int = _DEFAULT_SEED,
) -> dict[str, Any]:
    """Return a valid TransactionCreateRequest payload dict."""
    fake = make_faker(seed)
    return {
        "amount": str(amount or generate_transaction_amount(seed)),
        "currency": currency or generate_currency_code(seed),
        "merchant": merchant or generate_merchant_name(fake, seed),
        "card_last_four": card_last_four or generate_card_last_four(seed),
    }


def make_transaction_row(
    *,
    id: str | uuid.UUID | None = None,
    amount: Decimal | None = None,
    currency: str | None = None,
    merchant: str | None = None,
    card_last_four: str | None = None,
    status: str = "approved",
    authorization_code: str | None = None,
    seed: int = _DEFAULT_SEED,
) -> dict[str, Any]:
    """Return a dict that mimics a demo_transactions DB row."""
    fake = make_faker(seed)
    tx_id = id if id is not None else uuid.uuid4()
    auth_code = authorization_code
    if auth_code is None and status == "approved":
        auth_code = generate_authorization_code(seed)
    return {
        "id": uuid.UUID(str(tx_id)),
        "amount": amount or generate_transaction_amount(seed),
        "currency": currency or generate_currency_code(seed),
        "merchant": merchant or generate_merchant_name(fake, seed),
        "card_last_four": card_last_four or generate_card_last_four(seed),
        "status": status,
        "authorization_code": auth_code,
        "metadata": {"is_simulated": True},
        "is_simulated": True,
        "created_at": datetime.now(tz=timezone.utc),
        "updated_at": datetime.now(tz=timezone.utc),
    }


def make_service_row(
    *,
    id: str | uuid.UUID | None = None,
) -> dict[str, Any]:
    """Return a dict that mimics a services DB row for the Payment Service."""
    return {
        "id": uuid.UUID(str(id)) if id else uuid.UUID("d0000000-0000-0000-0000-000000000001"),
        "name": "ForgeGuard Payment Service",
        "description": "Mock payment processing service for governance demonstration.",
        "repository_url": "https://git.forgeguard.demo/platform/payment-service",
        "owner_team": "Payments Platform Team",
        "metadata": {
            "language": "Python",
            "framework": "FastAPI",
            "team_size": 6,
            "tier": "critical",
            "pci_scope": True,
            "version": "1.0.0",
            "capabilities": ["mock-transactions", "synthetic-data"],
        },
        "is_demo": True,
        "created_at": datetime.now(tz=timezone.utc),
        "updated_at": datetime.now(tz=timezone.utc),
        "deleted_at": None,
    }
