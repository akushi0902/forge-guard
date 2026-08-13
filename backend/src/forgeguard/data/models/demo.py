"""Demo domain SQLAlchemy ORM models.

Supports the Mock Payment Service demo application (WO-054).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any, Optional

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Index,
    Numeric,
    String,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from forgeguard.data.models import Base


class DemoTransaction(Base):
    """A synthetic payment transaction created by the mock Payment Service."""

    __tablename__ = "demo_transactions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    merchant: Mapped[str] = mapped_column(String(255), nullable=False)
    card_last_four: Mapped[str] = mapped_column(String(4), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default="pending"
    )
    authorization_code: Mapped[Optional[str]] = mapped_column(
        String(20), nullable=True
    )
    transaction_metadata: Mapped[Optional[dict[str, Any]]] = mapped_column(
        "metadata", JSONB, nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'approved', 'declined')",
            name="demo_transactions_status",
        ),
        CheckConstraint(
            "char_length(currency) = 3",
            name="demo_transactions_currency_len",
        ),
        CheckConstraint(
            "char_length(card_last_four) = 4",
            name="demo_transactions_card_four_len",
        ),
        CheckConstraint(
            "amount >= 0.01 AND amount <= 9999.99",
            name="demo_transactions_amount_range",
        ),
        Index("ix_demo_transactions_created_at", "created_at"),
        Index("ix_demo_transactions_status", "status"),
    )
