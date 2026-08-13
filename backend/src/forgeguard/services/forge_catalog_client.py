"""Forge Catalog async HTTP client with exponential-backoff retry and TTL cache.

Security requirements:
  - FORGE_CATALOG_API_KEY is NEVER logged, included in error responses, or stored
    anywhere beyond this module. Injected exclusively via X-Forge-Api-Key header.
  - All error messages reference only the endpoint path and HTTP status code.
"""

from __future__ import annotations

import asyncio
import uuid
from typing import Any, Optional

import httpx
import structlog
from cachetools import TTLCache

logger = structlog.get_logger(__name__)

_DEFAULT_TIMEOUT = 10.0
_RETRY_DELAYS = (1.0, 2.0, 4.0)
_CACHE_TTL = 3600
_CACHE_MAXSIZE = 256


class ForgeCatalogClientError(Exception):
    """Raised when a Forge Catalog API call fails after retries."""

    def __init__(
        self,
        message: str,
        *,
        endpoint: str,
        status_code: int,
        retried: bool = False,
    ) -> None:
        super().__init__(message)
        self.endpoint = endpoint
        self.status_code = status_code
        self.retried = retried


class ForgeCatalogHttpClient:
    """Async HTTP client for the Forge Catalog API.

    Retries 5xx and connection errors with exponential backoff (1s/2s/4s, 3 attempts).
    Caches last-known catalog state per service_id with a 1-hour TTL.

    Args:
        base_url: Forge Catalog API base URL.
        api_key:  API key transmitted as X-Forge-Api-Key header. Never logged.
        timeout:  HTTP request timeout in seconds.
    """

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        timeout: float = _DEFAULT_TIMEOUT,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._timeout = timeout
        self._cache: TTLCache = TTLCache(maxsize=_CACHE_MAXSIZE, ttl=_CACHE_TTL)

    def _make_client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=self._base_url,
            headers={
                "X-Forge-Api-Key": self._api_key,
                "Content-Type": "application/json",
            },
            timeout=self._timeout,
        )

    async def _request_with_retry(
        self,
        method: str,
        endpoint: str,
        *,
        json: Optional[dict[str, Any]] = None,
        params: Optional[dict[str, str]] = None,
        attempt: int = 0,
    ) -> dict[str, Any]:
        """Execute an HTTP request, retrying 5xx and timeouts with exponential backoff."""
        log = logger.bind(endpoint=endpoint, method=method, attempt=attempt)

        async with self._make_client() as client:
            try:
                response = await client.request(method, endpoint, json=json, params=params)
            except (httpx.ConnectError, httpx.TimeoutException) as exc:
                log.warning("forge_catalog_connection_error", error_type=type(exc).__name__)
                if attempt < len(_RETRY_DELAYS):
                    delay = _RETRY_DELAYS[attempt]
                    log.info("forge_catalog_retrying", delay=delay, retry_attempt=attempt + 1)
                    await asyncio.sleep(delay)
                    return await self._request_with_retry(
                        method, endpoint, json=json, params=params, attempt=attempt + 1
                    )
                raise ForgeCatalogClientError(
                    "Forge Catalog API connection failed after retries",
                    endpoint=endpoint,
                    status_code=0,
                    retried=True,
                ) from exc

        if response.status_code in (401, 403):
            log.critical(
                "forge_catalog_auth_failure",
                status_code=response.status_code,
                endpoint=endpoint,
            )
            raise ForgeCatalogClientError(
                f"Forge Catalog API authentication failed: HTTP {response.status_code}",
                endpoint=endpoint,
                status_code=response.status_code,
            )

        if response.status_code == 400:
            log.error("forge_catalog_bad_request", status_code=400, endpoint=endpoint)
            raise ForgeCatalogClientError(
                "Forge Catalog API rejected request: HTTP 400",
                endpoint=endpoint,
                status_code=400,
            )

        if response.status_code == 404:
            log.warning("forge_catalog_not_found", endpoint=endpoint)
            raise ForgeCatalogClientError(
                "Forge Catalog entity not found: HTTP 404",
                endpoint=endpoint,
                status_code=404,
            )

        if response.status_code == 409:
            # Entity already exists — caller must switch to PUT
            return {"_conflict": True, "status_code": 409}

        if response.status_code >= 500:
            log.warning(
                "forge_catalog_server_error",
                status_code=response.status_code,
                endpoint=endpoint,
            )
            if attempt < len(_RETRY_DELAYS):
                delay = _RETRY_DELAYS[attempt]
                log.info("forge_catalog_retrying", delay=delay, retry_attempt=attempt + 1)
                await asyncio.sleep(delay)
                return await self._request_with_retry(
                    method, endpoint, json=json, params=params, attempt=attempt + 1
                )
            raise ForgeCatalogClientError(
                f"Forge Catalog API returned HTTP {response.status_code} after retries",
                endpoint=endpoint,
                status_code=response.status_code,
                retried=True,
            )

        try:
            return response.json()
        except Exception as exc:
            raise ForgeCatalogClientError(
                "Forge Catalog API returned unexpected response schema",
                endpoint=endpoint,
                status_code=response.status_code,
            ) from exc

    # ------------------------------------------------------------------
    # Public API methods
    # ------------------------------------------------------------------

    async def create_entity(
        self,
        *,
        name: str,
        description: Optional[str],
        entity_type: str,
        metadata: dict[str, Any],
        owner: Optional[str],
    ) -> dict[str, Any]:
        """POST /entities — create a new catalog entity."""
        payload: dict[str, Any] = {"name": name, "type": entity_type, "metadata": metadata}
        if description:
            payload["description"] = description
        if owner:
            payload["owner"] = owner
        return await self._request_with_retry("POST", "/entities", json=payload)

    async def update_entity(
        self,
        catalog_id: str | uuid.UUID,
        *,
        name: str,
        description: Optional[str],
        metadata: dict[str, Any],
        owner: Optional[str],
    ) -> dict[str, Any]:
        """PUT /entities/{id} — update an existing catalog entity."""
        payload: dict[str, Any] = {"name": name, "metadata": metadata}
        if description:
            payload["description"] = description
        if owner:
            payload["owner"] = owner
        return await self._request_with_retry("PUT", f"/entities/{catalog_id}", json=payload)

    async def find_entity_by_name(self, name: str) -> Optional[dict[str, Any]]:
        """GET /entities?filter=name:{name} — look up entity by name."""
        result = await self._request_with_retry(
            "GET", "/entities", params={"filter": f"name:{name}"}
        )
        items = result.get("items", [])
        return items[0] if items else None

    async def get_entity_by_id(self, catalog_id: str | uuid.UUID) -> dict[str, Any]:
        """GET /entities/{id} — fetch entity by catalog ID."""
        return await self._request_with_retry("GET", f"/entities/{catalog_id}")

    # ------------------------------------------------------------------
    # Cache helpers
    # ------------------------------------------------------------------

    def cache_state(self, service_id: str | uuid.UUID, state: dict[str, Any]) -> None:
        """Store last-known catalog state for a service (TTL=1h)."""
        self._cache[str(service_id)] = state

    def get_cached_state(self, service_id: str | uuid.UUID) -> Optional[dict[str, Any]]:
        """Retrieve cached catalog state for a service, or None if absent/expired."""
        return self._cache.get(str(service_id))
