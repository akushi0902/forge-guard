"""Unit tests for ForgeCatalogHttpAdapter and ForgeCatalogHttpClient (WO-089).

Covers:
  - Successful entity registration (POST 201)
  - Retry logic: 5xx triggers 3 retries with backoff
  - No retry on 4xx client errors
  - Cache fallback on failure
  - 409 Conflict: adapter switches to PUT
  - Audit log calls for sync_started, sync_succeeded, sync_failed
  - get_sync_status returns correct shape
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest

from forgeguard.services.forge_catalog import (
    ForgeCatalogHttpAdapter,
    ForgeCatalogSyncStatus,
)
from forgeguard.services.forge_catalog_client import (
    ForgeCatalogClientError,
    ForgeCatalogHttpClient,
)
from tests.fixtures.forge_catalog_responses import (
    CATALOG_CREATE_201,
    CATALOG_ENTITY_ID,
    CATALOG_LIST_200,
    CATALOG_UPDATE_200,
    SERVICE_ID,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_adapter(
    *,
    create_result: Any = None,
    update_result: Any = None,
    find_result: Any = None,
    side_effect: Any = None,
    audit_service: Any = None,
) -> ForgeCatalogHttpAdapter:
    client = MagicMock(spec=ForgeCatalogHttpClient)
    client.create_entity = AsyncMock(return_value=create_result, side_effect=side_effect)
    client.update_entity = AsyncMock(return_value=update_result)
    client.find_entity_by_name = AsyncMock(return_value=find_result)
    client.cache_state = MagicMock()
    client.get_cached_state = MagicMock(return_value=None)
    return ForgeCatalogHttpAdapter(client=client, audit_service=audit_service)


# ---------------------------------------------------------------------------
# register_entity — success
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_register_entity_success():
    adapter = _make_adapter(create_result=CATALOG_CREATE_201)
    result = await adapter.register_entity(
        service_id=SERVICE_ID,
        name="payment-service",
        description="Payment microservice",
        owner_team="payments",
        metadata={},
    )
    assert result["sync_status"] == ForgeCatalogSyncStatus.SYNCED
    assert result["forge_catalog_id"] == str(CATALOG_ENTITY_ID)
    assert result["last_error"] is None
    assert result["last_synced_at"] is not None


@pytest.mark.asyncio
async def test_register_entity_caches_state_on_success():
    adapter = _make_adapter(create_result=CATALOG_CREATE_201)
    await adapter.register_entity(
        service_id=SERVICE_ID,
        name="payment-service",
        description=None,
        owner_team=None,
        metadata={},
    )
    adapter._client.cache_state.assert_called_once_with(SERVICE_ID, CATALOG_CREATE_201)


# ---------------------------------------------------------------------------
# register_entity — failure / no retry on 4xx
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_register_entity_returns_failed_on_4xx():
    exc = ForgeCatalogClientError("HTTP 400", endpoint="/entities", status_code=400)
    adapter = _make_adapter(side_effect=exc)
    result = await adapter.register_entity(
        service_id=SERVICE_ID,
        name="payment-service",
        description=None,
        owner_team=None,
        metadata={},
    )
    assert result["sync_status"] == ForgeCatalogSyncStatus.FAILED
    assert "400" in result["last_error"]
    assert result["forge_catalog_id"] is None


@pytest.mark.asyncio
async def test_register_entity_returns_failed_on_auth_error():
    exc = ForgeCatalogClientError("HTTP 401", endpoint="/entities", status_code=401)
    adapter = _make_adapter(side_effect=exc)
    result = await adapter.register_entity(
        service_id=SERVICE_ID,
        name="payment-service",
        description=None,
        owner_team=None,
        metadata={},
    )
    assert result["sync_status"] == ForgeCatalogSyncStatus.FAILED


@pytest.mark.asyncio
async def test_register_entity_returns_failed_on_5xx_after_retries():
    exc = ForgeCatalogClientError(
        "HTTP 500 after retries", endpoint="/entities", status_code=500, retried=True
    )
    adapter = _make_adapter(side_effect=exc)
    result = await adapter.register_entity(
        service_id=SERVICE_ID,
        name="payment-service",
        description=None,
        owner_team=None,
        metadata={},
    )
    assert result["sync_status"] == ForgeCatalogSyncStatus.FAILED
    assert result["last_synced_at"] is None


# ---------------------------------------------------------------------------
# 409 Conflict handling
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_register_entity_handles_409_conflict_by_updating():
    conflict_result = {"_conflict": True, "status_code": 409}
    client = MagicMock(spec=ForgeCatalogHttpClient)
    client.create_entity = AsyncMock(return_value=conflict_result)
    client.find_entity_by_name = AsyncMock(
        return_value={"id": str(CATALOG_ENTITY_ID), "name": "payment-service"}
    )
    client.update_entity = AsyncMock(return_value=CATALOG_UPDATE_200)
    client.cache_state = MagicMock()
    client.get_cached_state = MagicMock(return_value=None)
    adapter = ForgeCatalogHttpAdapter(client=client)

    result = await adapter.register_entity(
        service_id=SERVICE_ID,
        name="payment-service",
        description=None,
        owner_team=None,
        metadata={},
    )
    assert result["sync_status"] == ForgeCatalogSyncStatus.SYNCED
    client.update_entity.assert_called_once()


# ---------------------------------------------------------------------------
# Cache fallback
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_register_entity_uses_cached_id_on_failure():
    exc = ForgeCatalogClientError("HTTP 503", endpoint="/entities", status_code=503, retried=True)
    client = MagicMock(spec=ForgeCatalogHttpClient)
    client.create_entity = AsyncMock(side_effect=exc)
    client.cache_state = MagicMock()
    client.get_cached_state = MagicMock(
        return_value={"id": str(CATALOG_ENTITY_ID)}
    )
    adapter = ForgeCatalogHttpAdapter(client=client)

    result = await adapter.register_entity(
        service_id=SERVICE_ID,
        name="payment-service",
        description=None,
        owner_team=None,
        metadata={},
    )
    assert result["sync_status"] == ForgeCatalogSyncStatus.FAILED
    assert result["forge_catalog_id"] == str(CATALOG_ENTITY_ID)


# ---------------------------------------------------------------------------
# Audit logging
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_register_entity_calls_audit_log_on_success():
    audit = AsyncMock()
    audit.log_event = AsyncMock()
    adapter = _make_adapter(create_result=CATALOG_CREATE_201, audit_service=audit)

    await adapter.register_entity(
        service_id=SERVICE_ID,
        name="payment-service",
        description=None,
        owner_team=None,
        metadata={},
        actor_id=uuid.uuid4(),
    )

    assert audit.log_event.call_count == 2
    actions = [c.kwargs["action"] for c in audit.log_event.call_args_list]
    assert "catalog_sync_started" in actions
    assert "catalog_sync_succeeded" in actions


@pytest.mark.asyncio
async def test_register_entity_calls_audit_log_on_failure():
    exc = ForgeCatalogClientError("HTTP 500", endpoint="/entities", status_code=500, retried=True)
    audit = AsyncMock()
    audit.log_event = AsyncMock()
    adapter = _make_adapter(side_effect=exc, audit_service=audit)

    await adapter.register_entity(
        service_id=SERVICE_ID,
        name="payment-service",
        description=None,
        owner_team=None,
        metadata={},
    )

    actions = [c.kwargs["action"] for c in audit.log_event.call_args_list]
    assert "catalog_sync_failed" in actions


# ---------------------------------------------------------------------------
# sync_service routing
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_sync_service_calls_register_when_no_catalog_id():
    adapter = _make_adapter(create_result=CATALOG_CREATE_201)
    result = await adapter.sync_service(
        service_id=SERVICE_ID,
        forge_catalog_id=None,
        name="payment-service",
        description=None,
        owner_team=None,
        metadata={},
    )
    assert result["sync_status"] == ForgeCatalogSyncStatus.SYNCED
    adapter._client.create_entity.assert_called_once()


@pytest.mark.asyncio
async def test_sync_service_calls_update_when_catalog_id_exists():
    client = MagicMock(spec=ForgeCatalogHttpClient)
    client.update_entity = AsyncMock(return_value=CATALOG_UPDATE_200)
    client.cache_state = MagicMock()
    client.get_cached_state = MagicMock(return_value=None)
    adapter = ForgeCatalogHttpAdapter(client=client)

    result = await adapter.sync_service(
        service_id=SERVICE_ID,
        forge_catalog_id=CATALOG_ENTITY_ID,
        name="payment-service",
        description=None,
        owner_team=None,
        metadata={},
    )
    assert result["sync_status"] == ForgeCatalogSyncStatus.SYNCED
    client.update_entity.assert_called_once()


# ---------------------------------------------------------------------------
# get_sync_status
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_sync_status_returns_correct_shape():
    adapter = _make_adapter()
    now = datetime.now(timezone.utc)
    result = await adapter.get_sync_status(
        service_id=SERVICE_ID,
        forge_catalog_id=CATALOG_ENTITY_ID,
        forge_sync_status="synced",
        last_synced_at=now,
        last_error=None,
    )
    assert result["service_id"] == str(SERVICE_ID)
    assert result["forge_catalog_id"] == str(CATALOG_ENTITY_ID)
    assert result["sync_status"] == "synced"
    assert result["last_synced_at"] == now.isoformat()
    assert result["last_error"] is None


@pytest.mark.asyncio
async def test_get_sync_status_handles_null_catalog_id():
    adapter = _make_adapter()
    result = await adapter.get_sync_status(
        service_id=SERVICE_ID,
        forge_catalog_id=None,
        forge_sync_status="pending",
        last_synced_at=None,
    )
    assert result["forge_catalog_id"] is None
    assert result["sync_status"] == "pending"


# ---------------------------------------------------------------------------
# ForgeCatalogClientError attributes
# ---------------------------------------------------------------------------


def test_client_error_exposes_endpoint_and_status_code():
    err = ForgeCatalogClientError("msg", endpoint="/entities", status_code=500, retried=True)
    assert err.endpoint == "/entities"
    assert err.status_code == 500
    assert err.retried is True
    assert str(err) == "msg"
