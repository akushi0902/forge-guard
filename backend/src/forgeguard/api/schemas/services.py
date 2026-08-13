"""Pydantic response schemas for the /api/v1/services endpoints.

ServiceResponse includes the is_demo flag from the SERVICES table so that
the frontend can render a visual demo badge on demo service cards without
making a secondary API call.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class ServiceResponse(BaseModel):
    """API representation of a single service record.

    The is_demo field is populated directly from the SERVICES.is_demo column.
    Consumers (frontend, CLI) use this to distinguish demo services from real
    governance-managed services and render appropriate visual indicators.
    """

    model_config = ConfigDict(
        strict=True,
        extra="ignore",
        populate_by_name=True,
    )

    id: uuid.UUID
    name: str
    description: Optional[str] = None
    repository_url: Optional[str] = None
    owner_team: Optional[str] = None
    is_demo: bool
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
