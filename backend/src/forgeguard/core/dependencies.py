"""FastAPI dependency providers for service-layer modules.

Each ``Depends()`` provider in this module is the canonical injection point
for its corresponding service.  Route handlers must obtain service instances
exclusively through these providers — direct instantiation in route handlers
is prohibited to ensure testability and consistent lifecycle management.

Usage::

    from fastapi import Depends
    from forgeguard.core.dependencies import get_settings

    @router.get("/health")
    async def health(settings: Settings = Depends(get_settings)) -> dict:
        return {"version": settings.app_version}
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends

from forgeguard.core.config import Settings, get_settings

# Re-export the settings dependency under a convenient alias.
SettingsDep = Annotated[Settings, Depends(get_settings)]

__all__ = [
    "SettingsDep",
    "get_settings",
]
