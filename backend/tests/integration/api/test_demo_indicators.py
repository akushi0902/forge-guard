"""Integration tests verifying simulation indicators on demo API responses (WO-057).

Every response from /api/v1/demo/* endpoints must carry three simulation
fields at the top level:
  * is_simulated        — bool, always True
  * data_classification — "simulated"
  * simulation_disclaimer — exact SIMULATION_DISCLAIMER constant text

Additionally, GET /api/v1/demo/services/payment must carry is_demo: true.

Uses the same FastAPI dependency-override pattern as test_demo_endpoints.py.
No real database connection is required.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest
from httpx import ASGITransport, AsyncClient

from forgeguard.constants.demo import DATA_CLASSIFICATION_SIMULATED, SIMULATION_DISCLAIMER
from forgeguard.core.dependencies import get_demo_app_service
from forgeguard.main import create_app
from tests.fixtures.demo.factories import make_service_row, make_transaction_row


# ---------------------------------------------------------------------------
# Shared helpers (identical pattern to test_demo_endpoints.py)
# ---------------------------------------------------------------------------

_ADMIN_HEADERS = {"X-User-Role": "platform_admin"}
_DEV_HEADERS = {"X-User-Role": "developer"}

_VALID_BODY = {
    "amount": "49.99",
    "currency": "USD",
    "merchant": "Acme Test Store",
    "card_last_four": "1234",
}


def _make_app(demo_service):
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
    app.dependency_overrides[get_demo_app_service] = lambda: demo_service
    return app


def _mock_service():
    """Return a fully configured mock DemoAppService for all 4 existing endpoints."""
    mock = AsyncMock()
    mock.create_transaction.return_value = make_transaction_row(status="approved")
    mock.get_transaction.return_value = make_transaction_row()
    svc = make_service_row()
    mock.get_service_info.return_value = {
        "id": svc["id"],
        "name": svc["name"],
        "description": svc["description"],
        "version": "1.0.0",
        "is_demo": True,
        "capabilities": ["mock-transactions"],
        "health_score": None,
        "last_evaluated": None,
    }
    mock.reset_demo_data.return_value = {
        "purged_count": 3,
        "message": "Demo data reset complete. 3 transaction(s) purged.",
        "reset_at": datetime.now(tz=timezone.utc),
    }
    return mock


# ---------------------------------------------------------------------------
# Helper: assert all three simulation indicators are present and correct
# ---------------------------------------------------------------------------

def _assert_simulation_indicators(body: dict) -> None:
    assert body.get("is_simulated") is True, (
        f"Expected is_simulated=True, got {body.get('is_simulated')!r}"
    )
    assert body.get("data_classification") == "simulated", (
        f"Expected data_classification='simulated', got {body.get('data_classification')!r}"
    )
    assert body.get("simulation_disclaimer") == SIMULATION_DISCLAIMER, (
        f"simulation_disclaimer mismatch. Got: {body.get('simulation_disclaimer')!r}"
    )


# ---------------------------------------------------------------------------
# POST /api/v1/demo/transactions — simulation indicators
# ---------------------------------------------------------------------------


class TestCreateTransactionSimulationIndicators:
    @pytest.mark.asyncio
    async def test_is_simulated_true(self):
        app = _make_app(_mock_service())
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.post(
                "/api/v1/demo/transactions", json=_VALID_BODY, headers=_DEV_HEADERS
            )
        assert resp.status_code == 201
        assert resp.json()["is_simulated"] is True

    @pytest.mark.asyncio
    async def test_data_classification_simulated(self):
        app = _make_app(_mock_service())
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.post(
                "/api/v1/demo/transactions", json=_VALID_BODY, headers=_DEV_HEADERS
            )
        assert resp.json()["data_classification"] == DATA_CLASSIFICATION_SIMULATED

    @pytest.mark.asyncio
    async def test_simulation_disclaimer_present_and_correct(self):
        app = _make_app(_mock_service())
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.post(
                "/api/v1/demo/transactions", json=_VALID_BODY, headers=_DEV_HEADERS
            )
        assert resp.json()["simulation_disclaimer"] == SIMULATION_DISCLAIMER

    @pytest.mark.asyncio
    async def test_all_three_simulation_indicators(self):
        app = _make_app(_mock_service())
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.post(
                "/api/v1/demo/transactions", json=_VALID_BODY, headers=_ADMIN_HEADERS
            )
        _assert_simulation_indicators(resp.json())


# ---------------------------------------------------------------------------
# GET /api/v1/demo/transactions/{id} — simulation indicators
# ---------------------------------------------------------------------------


class TestGetTransactionSimulationIndicators:
    @pytest.mark.asyncio
    async def test_all_three_simulation_indicators(self):
        tx_id = uuid.uuid4()
        mock = _mock_service()
        mock.get_transaction.return_value = make_transaction_row(id=tx_id)
        app = _make_app(mock)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.get(
                f"/api/v1/demo/transactions/{tx_id}", headers=_DEV_HEADERS
            )
        assert resp.status_code == 200
        _assert_simulation_indicators(resp.json())


# ---------------------------------------------------------------------------
# GET /api/v1/demo/services/payment — simulation indicators + is_demo
# ---------------------------------------------------------------------------


class TestGetPaymentServiceSimulationIndicators:
    @pytest.mark.asyncio
    async def test_all_three_simulation_indicators(self):
        app = _make_app(_mock_service())
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.get(
                "/api/v1/demo/services/payment", headers=_DEV_HEADERS
            )
        assert resp.status_code == 200
        _assert_simulation_indicators(resp.json())

    @pytest.mark.asyncio
    async def test_is_demo_true_on_service_object(self):
        """AC4: service objects in demo endpoints carry is_demo: true."""
        app = _make_app(_mock_service())
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.get(
                "/api/v1/demo/services/payment", headers=_DEV_HEADERS
            )
        assert resp.json()["is_demo"] is True


# ---------------------------------------------------------------------------
# POST /api/v1/demo/reset — simulation indicators
# ---------------------------------------------------------------------------


class TestResetSimulationIndicators:
    @pytest.mark.asyncio
    async def test_all_three_simulation_indicators(self):
        app = _make_app(_mock_service())
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.post("/api/v1/demo/reset", headers=_ADMIN_HEADERS)
        assert resp.status_code == 200
        _assert_simulation_indicators(resp.json())


# ---------------------------------------------------------------------------
# Non-demo isolation — non-demo routes must NOT have simulation fields
# ---------------------------------------------------------------------------


class TestNonDemoEndpointIsolation:
    @pytest.mark.asyncio
    async def test_health_endpoint_has_no_simulation_fields(self):
        """AC6: non-demo endpoints must not include simulation indicators."""
        import forgeguard.core.config as config_module  # noqa: PLC0415
        from forgeguard.core.config import Settings  # noqa: PLC0415

        settings = Settings(
            database_url="postgresql+asyncpg://postgres:postgres@localhost:5432/test",
            jwt_secret_key="test-secret",
            log_level="DEBUG",
            app_env="testing",
            llm_api_key="",
            forge_catalog_url="http://localhost:9999/catalog",
        )
        config_module._settings_cache = settings
        app = create_app()

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.get("/health")

        body = resp.json()
        assert "is_simulated" not in body
        assert "data_classification" not in body
        assert "simulation_disclaimer" not in body

    @pytest.mark.asyncio
    async def test_all_demo_endpoints_share_same_disclaimer_text(self):
        """All four demo endpoints return the exact same disclaimer constant."""
        tx_id = uuid.uuid4()
        mock = _mock_service()
        mock.get_transaction.return_value = make_transaction_row(id=tx_id)
        app = _make_app(mock)

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            r_create = await c.post(
                "/api/v1/demo/transactions", json=_VALID_BODY, headers=_DEV_HEADERS
            )
            r_get = await c.get(
                f"/api/v1/demo/transactions/{tx_id}", headers=_DEV_HEADERS
            )
            r_svc = await c.get(
                "/api/v1/demo/services/payment", headers=_DEV_HEADERS
            )
            r_reset = await c.post("/api/v1/demo/reset", headers=_ADMIN_HEADERS)

        disclaimers = {
            r_create.json().get("simulation_disclaimer"),
            r_get.json().get("simulation_disclaimer"),
            r_svc.json().get("simulation_disclaimer"),
            r_reset.json().get("simulation_disclaimer"),
        }
        assert disclaimers == {SIMULATION_DISCLAIMER}, (
            f"Inconsistent disclaimers across endpoints: {disclaimers}"
        )
