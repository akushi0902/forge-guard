"""Request and response schemas for demo (mock Payment Service) endpoints."""

from __future__ import annotations

import re
import uuid
from datetime import datetime
from decimal import Decimal
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

# Commonly used ISO 4217 currency codes accepted by the mock service.
_ISO_4217_CODES: frozenset[str] = frozenset({
    "USD", "EUR", "GBP", "JPY", "AUD", "CAD", "CHF", "CNY", "SEK", "NZD",
    "MXN", "SGD", "HKD", "NOK", "KRW", "TRY", "INR", "RUB", "BRL", "ZAR",
    "DKK", "PLN", "THB", "IDR", "HUF", "CZK", "ILS", "CLP", "PHP", "AED",
    "COP", "SAR", "MYR", "RON", "PEN", "EGP", "QAR", "KWD", "BHD", "OMR",
})

_CARD_LAST_FOUR_RE = re.compile(r"^\d{4}$")


class TransactionCreateRequest(BaseModel):
    """Payload for POST /api/v1/demo/transactions.

    Uses non-strict mode to allow JSON numeric values to be coerced to Decimal.
    All other validations are enforced via field validators.
    """

    model_config = ConfigDict(
        strict=False,
        extra="forbid",
        str_strip_whitespace=True,
        populate_by_name=True,
    )

    amount: Decimal = Field(
        description="Transaction amount (0.01 – 9999.99).",
        examples=["49.99"],
    )
    currency: str = Field(
        min_length=3,
        max_length=3,
        description="ISO 4217 three-letter currency code.",
        examples=["USD"],
    )
    merchant: str = Field(
        min_length=1,
        max_length=255,
        description="Merchant name.",
        examples=["Acme Electronics Store"],
    )
    card_last_four: str = Field(
        min_length=4,
        max_length=4,
        description="Last four digits of the card number.",
        examples=["4242"],
    )

    @field_validator("amount")
    @classmethod
    def _validate_amount(cls, v: Decimal) -> Decimal:
        if v < Decimal("0.01") or v > Decimal("9999.99"):
            raise ValueError("amount must be between 0.01 and 9999.99")
        return v

    @field_validator("currency")
    @classmethod
    def _validate_currency(cls, v: str) -> str:
        upper = v.upper()
        if upper not in _ISO_4217_CODES:
            raise ValueError(
                f"'{v}' is not a supported ISO 4217 currency code. "
                f"Accepted codes include USD, EUR, GBP, JPY, AUD, CAD."
            )
        return upper

    @field_validator("card_last_four")
    @classmethod
    def _validate_card_last_four(cls, v: str) -> str:
        if not _CARD_LAST_FOUR_RE.match(v):
            raise ValueError(
                "card_last_four must be exactly 4 digits (0-9). "
                "Full card numbers are not accepted."
            )
        return v


class TransactionResponse(BaseModel):
    """Response model for a single mock transaction."""

    model_config = ConfigDict(
        strict=True,
        extra="ignore",
        frozen=False,
        str_strip_whitespace=True,
        populate_by_name=True,
    )

    id: uuid.UUID
    amount: Decimal
    currency: str
    merchant: str
    card_last_four: str
    status: str
    authorization_code: Optional[str] = None
    is_simulated: bool = True
    created_at: datetime


class PaymentServiceInfoResponse(BaseModel):
    """Response model for GET /api/v1/demo/services/payment."""

    model_config = ConfigDict(
        strict=True,
        extra="ignore",
        frozen=False,
        str_strip_whitespace=True,
        populate_by_name=True,
    )

    id: uuid.UUID
    name: str
    description: str
    version: str
    is_demo: bool
    capabilities: List[str]
    health_score: Optional[float] = None
    last_evaluated: Optional[datetime] = None


class ResetResponse(BaseModel):
    """Response model for POST /api/v1/demo/reset."""

    model_config = ConfigDict(
        strict=False,
        extra="forbid",
        str_strip_whitespace=True,
        populate_by_name=True,
    )

    purged_count: int
    message: str
    reset_at: datetime
