"""Forge Scorecard Health Score publishing adapter (WO-090).

Publishes Health Scores to the Forge Scorecard API after every assessment.
Implements exponential-backoff retry via the database-backed SyncQueueService.

Security:
    FORGE_SCORECARD_API_KEY is NEVER logged, included in error messages, or
    stored beyond this module. Injected exclusively via X-Forge-Api-Key header.

Dimension mapping (ForgeGuard → Forge Scorecard identifiers):
    code_quality          → code_quality
    test_coverage         → test_coverage
    security              → security
    documentation         → documentation
    operations_readiness  → operations_readiness

Sync status values (stored in assessment_scores.forge_sync_status):
    pending               — not yet attempted
    synced                — successfully published
    failed                — non-retryable failure (4xx)
    stale                 — all retries exhausted
    blocked_no_catalog_id — service has no forge_catalog_id
"""

from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any, Optional

import structlog

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Sync status constants
# ---------------------------------------------------------------------------

class ScorecardSyncStatus:
    PENDING = "pending"
    SYNCED = "synced"
    FAILED = "failed"
    STALE = "stale"
    BLOCKED_NO_CATALOG_ID = "blocked_no_catalog_id"


# ---------------------------------------------------------------------------
# Dimension mapping
# ---------------------------------------------------------------------------

# Maps ForgeGuard policy dimension names to Forge Scorecard dimension identifiers.
# Configurable — override by passing a custom mapping to the adapter.
DEFAULT_DIMENSION_MAP: dict[str, str] = {
    "code_quality": "code_quality",
    "test_coverage": "test_coverage",
    "security": "security",
    "documentation": "documentation",
    "operations_readiness": "operations_readiness",
}


def map_dimensions(
    dimension_scores: dict[str, Any],
    dimension_map: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    """Convert ForgeGuard dimension scores to Forge Scorecard payload format.

    Args:
        dimension_scores: Dict of {dimension_name: DimensionScore-like dict}
                          from the assessment result.
        dimension_map:    Optional override mapping.

    Returns:
        List of {name, score, weight} dicts for the Forge Scorecard API.
    """
    mapping = dimension_map or DEFAULT_DIMENSION_MAP
    result: list[dict[str, Any]] = []
    for fg_dim, sc_dim in mapping.items():
        ds = dimension_scores.get(fg_dim)
        if ds is None:
            continue
        score = ds.get("score") if isinstance(ds, dict) else getattr(ds, "score", None)
        weight = ds.get("weight", 1.0) if isinstance(ds, dict) else getattr(ds, "weight", 1.0)
        if score is None:
            continue
        result.append({"name": sc_dim, "score": float(score), "weight": float(weight or 1.0)})
    return result


# ---------------------------------------------------------------------------
# Abstract adapter
# ---------------------------------------------------------------------------

class ForgeScorecardAdapter(ABC):
    """Abstract interface for Forge Scorecard integration.

    Concrete: ForgeScorecardHttpAdapter (production).
    Tests use: MockForgeScorecardAdapter.
    """

    @abstractmethod
    async def publish_score(
        self,
        *,
        scorecard_id: str,
        service_id: uuid.UUID,
        assessment_id: uuid.UUID,
        overall_score: float,
        dimension_scores: dict[str, Any],
        assessed_at: datetime,
    ) -> dict[str, Any]:
        """Publish a health score to the Forge Scorecard API.

        Returns:
            Dict with keys: success (bool), status_code (int), error (str|None).

        Must not raise — failures are returned in the result dict.
        """

    @abstractmethod
    async def get_scorecard_status(self, *, scorecard_id: str) -> dict[str, Any]:
        """Fetch the current status of a scorecard from the API.

        Returns dict with keys: id, name, dimensions, latest_scores.
        Must not raise — failures returned as {error: ...}.
        """


# ---------------------------------------------------------------------------
# HTTP adapter
# ---------------------------------------------------------------------------

class ForgeScorecardHttpAdapter(ForgeScorecardAdapter):
    """Production HTTP adapter for the Forge Scorecard API.

    Args:
        base_url:      Base URL of the Forge Scorecard API.
        api_key:       X-Forge-Api-Key value. NEVER logged.
        http_timeout:  Request timeout in seconds.
        dimension_map: Optional override for dimension name mapping.
    """

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        http_timeout: float = 10.0,
        dimension_map: dict[str, str] | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._timeout = http_timeout
        self._dimension_map = dimension_map or DEFAULT_DIMENSION_MAP

    def _headers(self) -> dict[str, str]:
        return {
            "X-Forge-Api-Key": self._api_key,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    async def publish_score(
        self,
        *,
        scorecard_id: str,
        service_id: uuid.UUID,
        assessment_id: uuid.UUID,
        overall_score: float,
        dimension_scores: dict[str, Any],
        assessed_at: datetime,
    ) -> dict[str, Any]:
        """POST /scorecards/{scorecard_id}/scores to the Forge Scorecard API."""
        import httpx  # noqa: PLC0415

        dimensions = map_dimensions(dimension_scores, self._dimension_map)
        payload = {
            "overall_score": round(float(overall_score), 4),
            "dimensions": dimensions,
            "assessed_at": assessed_at.isoformat(),
            "service_id": str(service_id),
        }

        url = f"{self._base_url}/scorecards/{scorecard_id}/scores"
        log = logger.bind(
            assessment_id=str(assessment_id),
            service_id=str(service_id),
            scorecard_id=scorecard_id,
        )
        log.info("forge_scorecard.publish_started")

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.post(url, json=payload, headers=self._headers())
        except httpx.TimeoutException as exc:
            log.warning("forge_scorecard.publish_timeout", error=str(exc))
            return {"success": False, "status_code": None, "error": "timeout", "retryable": True}
        except httpx.RequestError as exc:
            log.warning("forge_scorecard.publish_network_error", error=str(exc))
            return {"success": False, "status_code": None, "error": str(exc), "retryable": True}

        status = resp.status_code
        if status in (200, 201, 204):
            log.info("forge_scorecard.publish_succeeded", status_code=status)
            return {"success": True, "status_code": status, "error": None, "retryable": False}

        # 4xx — client error, do not retry
        if 400 <= status < 500:
            log.error("forge_scorecard.publish_client_error", status_code=status)
            return {"success": False, "status_code": status, "error": f"HTTP {status}", "retryable": False}

        # 5xx — server error, retry
        log.warning("forge_scorecard.publish_server_error", status_code=status)
        return {"success": False, "status_code": status, "error": f"HTTP {status}", "retryable": True}

    async def get_scorecard_status(self, *, scorecard_id: str) -> dict[str, Any]:
        """GET /scorecards/{scorecard_id} from the Forge Scorecard API."""
        import httpx  # noqa: PLC0415

        url = f"{self._base_url}/scorecards/{scorecard_id}"
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.get(url, headers=self._headers())
            if resp.status_code == 200:
                return resp.json()
            return {"error": f"HTTP {resp.status_code}"}
        except httpx.RequestError as exc:
            logger.warning("forge_scorecard.get_status_error", error=str(exc))
            return {"error": str(exc)}
