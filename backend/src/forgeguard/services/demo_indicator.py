"""Helpers for propagating simulation indicators to response dicts.

This module provides utilities that enrich API response dictionaries with
simulation metadata when the underlying data originates from a demo service
(SERVICES.is_demo = TRUE).

Design:
  * Pure synchronous helper (enrich_with_simulation_fields) for enriching
    any dict that is already known to be demo-originated.
  * Async helper (enrich_with_simulation_metadata) that looks up the service
    record and conditionally adds simulation fields — used by endpoints that
    serve both real and demo data from the same code path.
"""

from __future__ import annotations

import uuid
from typing import Any

import structlog

from forgeguard.constants.demo import DATA_CLASSIFICATION_SIMULATED, SIMULATION_DISCLAIMER

logger = structlog.get_logger(__name__)


def enrich_with_simulation_fields(response_dict: dict[str, Any]) -> dict[str, Any]:
    """Add simulation indicator fields to *response_dict* in-place and return it.

    Adds three keys:
      * ``is_simulated``        — bool, always True
      * ``data_classification`` — str, always "simulated"
      * ``simulation_disclaimer`` — str, the canonical disclaimer text

    Args:
        response_dict: Any mutable dict representing an API response payload.

    Returns:
        The same dict with simulation fields added (mutated in-place).
    """
    response_dict["is_simulated"] = True
    response_dict["data_classification"] = DATA_CLASSIFICATION_SIMULATED
    response_dict["simulation_disclaimer"] = SIMULATION_DISCLAIMER
    return response_dict


async def enrich_with_simulation_metadata(
    response_dict: dict[str, Any],
    service_id: uuid.UUID,
    *,
    pool: Any,
) -> dict[str, Any]:
    """Conditionally enrich *response_dict* based on the service's is_demo flag.

    Queries the SERVICES table for the given ``service_id``. If the service
    has ``is_demo = True``, the three simulation indicator fields are added to
    ``response_dict`` in-place. Non-demo services are returned unchanged.

    Database errors during the lookup are caught, logged as warnings, and
    treated as non-demo (fail-open strategy: prefer not to mismark real data
    as simulated over failing to mark demo data).

    Args:
        response_dict: Mutable dict for the API response payload.
        service_id:    UUID of the parent service to check.
        pool:          asyncpg connection pool (from ``get_pool()``).

    Returns:
        The (possibly enriched) response dict.
    """
    try:
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT is_demo FROM services WHERE id = $1 AND deleted_at IS NULL",
                service_id,
            )
        if row and row["is_demo"]:
            enrich_with_simulation_fields(response_dict)
            logger.debug(
                "demo_indicator.simulation_fields_added",
                service_id=str(service_id),
            )
    except Exception as exc:
        logger.warning(
            "demo_indicator.service_lookup_failed",
            service_id=str(service_id),
            error=str(exc),
        )
    return response_dict


def is_demo_route(path: str) -> bool:
    """Return True if *path* is under the /api/v1/demo/ prefix.

    Used by middleware and utilities that need to detect demo-originated
    responses without inspecting the service record.

    Args:
        path: The request URL path (e.g. "/api/v1/demo/transactions/...").

    Returns:
        True when the path starts with "/api/v1/demo/".
    """
    return path.startswith("/api/v1/demo/") or path == "/api/v1/demo"
