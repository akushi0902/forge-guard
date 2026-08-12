"""Pydantic schemas for remediation recommendation API (WO-058)."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Literal, Optional

from forgeguard.core.validation import ForgeGuardBaseModel


class RemediationResponse(ForgeGuardBaseModel):
    """Response schema for GET /api/v1/findings/{finding_id}/remediation."""

    id: uuid.UUID
    finding_id: uuid.UUID
    recommendation_text: str
    implementation_guide: str
    business_impact: Optional[str] = None
    confidence_score: Optional[Decimal] = None
    source: str
    created_at: datetime
