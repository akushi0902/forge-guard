"""Integration tests for demo mock Payment Service endpoints (WO-054).

Uses FastAPI dependency overrides to inject mock DemoAppService instances.
No real database connection is required.

Endpoints tested:
    POST /api/v1/demo/transactions          — 201, 422 validation
    GET  /api/v1/demo/transactions/{id}     — 200, 404, 422
    GET  /api/v1/demo/services/payment      — 200
    POST /api/v1/demo/reset                 — 200, 403
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from forgeguard.core.dependencies import get_demo_app_service
from forgeguard.core.exceptions import NotFoundError
from forgeguard.main import create_app
from tests.fixtures.demo.factories import make_service_row, make_transaction_row


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_ADMIN_HEADERS = {"X-User-Role": "platform_admin"}
_DEV_HEADERS = {"X-User-Role": "developer"}

_VALID_BODY = {
    "amount": "49.99",
    "currency": "USD",
    "merchant": "Acme Electronics Store",
    "card_last_four": "4242",
}


def _make_app(demo_service=None):
    """Return a configured app with the DemoAppService dependency overridden."""
    import forgeguard.core.config as config_module  # noqa: PLC0415
    from forgeguard.core.config import Settings  # noqa: PLC0415

    settings = Settings(
        database_url="postgresql+asyncpg://postgres:postgres@localhost:5432/forgeguard_test",
        jwt_secret_key="test-secret",
        log_level="DEBUG",
        app_env="testing",
        llm_api_key="",
        forge_catalog_url="http://localhost:9999/catalog",
    )
    config_module._settings_cache = settings

    app = create_app()

    if demo_service is not None:
        app.dependency_overrides[get_demo_app_service] = lambda: demo_service

    return app


def _mock_service(
    *,
    create_result=None,
    get_result=None,
    service_info_result=None,
    reset_result=None,
    get_raises=None,
):
    """Return a mock DemoAppService with configurable return values."""
    mock = AsyncMock()

    if create_result is not None:
        mock.create_transaction.return_value = create_result
    else:
        mock.create_transaction.return_value = make_transaction_row(status="approved")

    if get_raises is not None:
        mock.get_transaction.side_effect = get_raises
    elif get_result is not None:
        mock.get_transaction.return_value = get_result
    else:
        mock.get_transaction.return_value = make_transaction_row()

    if service_info_result is not None:
        mock.get_service_info.return_value = service_info_result
    else:
        svc = make_service_row()
        mock.get_service_info.return_value = {
            "id": svc["id"],
            "name": svc["name"],
            "description": svc["description"],
            "version": "1.0.0",
            "is_demo": True,
            "capabilities": ["mock-transactions", "synthetic-data"],
            "health_score": None,
            "last_evaluated": None,
        }

    if reset_result is not None:
        mock.reset_demo_data.return_value = reset_result
    else:
        mock.reset_demo_data.return_value = {
            "purged_count": 0,
            "message": "Demo data reset complete. 0 transaction(s) purged.",
            "reset_at": datetime.now(tz=timezone.utc),
        }

    return mock


# ---------------------------------------------------------------------------
# POST /api/v1/demo/transactions
# ---------------------------------------------------------------------------


class TestCreateTransaction:
    @pytest.mark.asyncio
    async def test_returns_201_with_valid_body(self):
        app = _make_app(demo_service=_mock_service())
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post(
                "/api/v1/demo/transactions",
                json=_VALID_BODY,
                headers=_ADMIN_HEADERS,
            )
        assert resp.status_code == 201

    @pytest.mark.asyncio
    async def test_response_contains_transaction_id(self):
        app = _make_app(demo_service=_mock_service())
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post(
                "/api/v1/demo/transactions",
                json=_VALID_BODY,
                headers=_DEV_HEADERS,
            )
        assert resp.status_code == 201
        body = resp.json()
        assert "id" in body
        assert "status" in body
        assert body["is_simulated"] is True

    @pytest.mark.asyncio
    async def test_returns_422_for_amount_below_minimum(self):
        app = _make_app(demo_service=_mock_service())
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post(
                "/api/v1/demo/transactions",
                json={**_VALID_BODY, "amount": "0.00"},
                headers=_ADMIN_HEADERS,
            )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_returns_422_for_amount_above_maximum(self):
        app = _make_app(demo_service=_mock_service())
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post(
                "/api/v1/demo/transactions",
                json={**_VALID_BODY, "amount": "10000.00"},
                headers=_ADMIN_HEADERS,
            )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_returns_422_for_invalid_currency(self):
        app = _make_app(demo_service=_mock_service())
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post(
                "/api/v1/demo/transactions",
                json={**_VALID_BODY, "currency": "XXX"},
                headers=_ADMIN_HEADERS,
            )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_returns_422_for_card_last_four_not_digits(self):
        app = _make_app(demo_service=_mock_service())
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post(
                "/api/v1/demo/transactions",
                json={**_VALID_BODY, "card_last_four": "ABCD"},
                headers=_ADMIN_HEADERS,
            )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_returns_403_when_no_role_header(self):
        app = _make_app(demo_service=_mock_service())
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post(
                "/api/v1/demo/transactions",
                json=_VALID_BODY,
            )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_minimum_valid_amount_accepted(self):
        app = _make_app(demo_service=_mock_service())
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post(
                "/api/v1/demo/transactions",
                json={**_VALID_BODY, "amount": "0.01"},
                headers=_ADMIN_HEADERS,
            )
        assert resp.status_code == 201

    @pytest.mark.asyncio
    async def test_maximum_valid_amount_accepted(self):
        app = _make_app(demo_service=_mock_service())
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post(
                "/api/v1/demo/transactions",
                json={**_VALID_BODY, "amount": "9999.99"},
                headers=_ADMIN_HEADERS,
            )
        assert resp.status_code == 201

    @pytest.mark.asyncio
    async def test_negative_amount_rejected(self):
        app = _make_app(demo_service=_mock_service())
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post(
                "/api/v1/demo/transactions",
                json={**_VALID_BODY, "amount": "-10.00"},
                headers=_ADMIN_HEADERS,
            )
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# GET /api/v1/demo/transactions/{id}
# ---------------------------------------------------------------------------


class TestGetTransaction:
    @pytest.mark.asyncio
    async def test_returns_200_for_existing_transaction(self):
        tx_id = uuid.uuid4()
        row = make_transaction_row(id=tx_id)
        app = _make_app(demo_service=_mock_service(get_result=row))
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get(
                f"/api/v1/demo/transactions/{tx_id}",
                headers=_DEV_HEADERS,
            )
        assert resp.status_code == 200
        assert resp.json()["id"] == str(tx_id)

    @pytest.mark.asyncio
    async def test_returns_404_for_missing_transaction(self):
        tx_id = uuid.uuid4()
        app = _make_app(
            demo_service=_mock_service(
                get_raises=NotFoundError(f"Transaction {tx_id} not found.")
            )
        )
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get(
                f"/api/v1/demo/transactions/{tx_id}",
                headers=_DEV_HEADERS,
            )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_returns_422_for_malformed_uuid(self):
        app = _make_app(demo_service=_mock_service())
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get(
                "/api/v1/demo/transactions/not-a-uuid",
                headers=_DEV_HEADERS,
            )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_response_has_is_simulated_true(self):
        tx_id = uuid.uuid4()
        row = make_transaction_row(id=tx_id)
        app = _make_app(demo_service=_mock_service(get_result=row))
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get(
                f"/api/v1/demo/transactions/{tx_id}",
                headers=_DEV_HEADERS,
            )
        assert resp.json()["is_simulated"] is True

    @pytest.mark.asyncio
    async def test_returns_403_without_role(self):
        tx_id = uuid.uuid4()
        app = _make_app(demo_service=_mock_service())
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get(f"/api/v1/demo/transactions/{tx_id}")
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# GET /api/v1/demo/services/payment
# ---------------------------------------------------------------------------


class TestGetPaymentService:
    @pytest.mark.asyncio
    async def test_returns_200(self):
        app = _make_app(demo_service=_mock_service())
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get(
                "/api/v1/demo/services/payment",
                headers=_DEV_HEADERS,
            )
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_is_demo_is_true(self):
        app = _make_app(demo_service=_mock_service())
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get(
                "/api/v1/demo/services/payment",
                headers=_DEV_HEADERS,
            )
        assert resp.json()["is_demo"] is True

    @pytest.mark.asyncio
    async def test_response_has_name(self):
        app = _make_app(demo_service=_mock_service())
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get(
                "/api/v1/demo/services/payment",
                headers=_DEV_HEADERS,
            )
        body = resp.json()
        assert "name" in body
        assert "description" in body
        assert "capabilities" in body

    @pytest.mark.asyncio
    async def test_returns_403_without_role(self):
        app = _make_app(demo_service=_mock_service())
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get("/api/v1/demo/services/payment")
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# POST /api/v1/demo/reset
# ---------------------------------------------------------------------------


class TestResetDemoData:
    @pytest.mark.asyncio
    async def test_returns_200_for_admin(self):
        app = _make_app(demo_service=_mock_service())
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post(
                "/api/v1/demo/reset",
                headers=_ADMIN_HEADERS,
            )
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_returns_purged_count(self):
        reset_result = {
            "purged_count": 7,
            "message": "Demo data reset complete. 7 transaction(s) purged.",
            "reset_at": datetime.now(tz=timezone.utc),
        }
        app = _make_app(demo_service=_mock_service(reset_result=reset_result))
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post(
                "/api/v1/demo/reset",
                headers=_ADMIN_HEADERS,
            )
        assert resp.json()["purged_count"] == 7

    @pytest.mark.asyncio
    async def test_returns_zero_count_when_no_data(self):
        reset_result = {
            "purged_count": 0,
            "message": "Demo data reset complete. 0 transaction(s) purged.",
            "reset_at": datetime.now(tz=timezone.utc),
        }
        app = _make_app(demo_service=_mock_service(reset_result=reset_result))
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post(
                "/api/v1/demo/reset",
                headers=_ADMIN_HEADERS,
            )
        assert resp.json()["purged_count"] == 0

    @pytest.mark.asyncio
    async def test_returns_403_for_developer_role(self):
        app = _make_app(demo_service=_mock_service())
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post(
                "/api/v1/demo/reset",
                headers=_DEV_HEADERS,
            )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_returns_403_without_role(self):
        app = _make_app(demo_service=_mock_service())
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post("/api/v1/demo/reset")
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_response_has_reset_at_field(self):
        app = _make_app(demo_service=_mock_service())
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post(
                "/api/v1/demo/reset",
                headers=_ADMIN_HEADERS,
            )
        assert "reset_at" in resp.json()
