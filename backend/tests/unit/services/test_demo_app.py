"""Unit tests for DemoAppService (WO-054).

All tests use a mocked DemoTransactionRepository injected into DemoAppService.
No real database connections are made.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from forgeguard.core.exceptions import NotFoundError
from forgeguard.services.demo_app import DemoAppService
from tests.fixtures.demo.factories import make_service_row, make_transaction_row


def _make_service() -> DemoAppService:
    repo = AsyncMock()
    return DemoAppService(repo), repo


class TestCreateTransaction:
    @pytest.mark.asyncio
    async def test_returns_dict_with_expected_keys(self):
        service, repo = _make_service()
        row = make_transaction_row(status="approved")
        repo.create.return_value = row
        result = await service.create_transaction(
            amount=Decimal("49.99"),
            currency="USD",
            merchant="Acme Electronics",
            card_last_four="4242",
        )
        assert "id" in result
        assert "status" in result
        assert result["is_simulated"] is True

    @pytest.mark.asyncio
    async def test_calls_repository_create(self):
        service, repo = _make_service()
        row = make_transaction_row(status="approved")
        repo.create.return_value = row
        await service.create_transaction(
            amount=Decimal("99.00"),
            currency="EUR",
            merchant="Test Shop",
            card_last_four="1111",
        )
        repo.create.assert_called_once()

    @pytest.mark.asyncio
    async def test_approved_transaction_has_authorization_code(self):
        service, repo = _make_service()
        row = make_transaction_row(status="approved", authorization_code="AUTHABCDE123")
        repo.create.return_value = row
        result = await service.create_transaction(
            amount=Decimal("20.00"),
            currency="GBP",
            merchant="London Shop",
            card_last_four="9999",
        )
        assert result["status"] == "approved"
        assert result["authorization_code"] is not None

    @pytest.mark.asyncio
    async def test_declined_transaction_has_no_authorization_code(self):
        service, repo = _make_service()
        row = make_transaction_row(status="declined", authorization_code=None)
        repo.create.return_value = row
        result = await service.create_transaction(
            amount=Decimal("20.00"),
            currency="USD",
            merchant="Some Shop",
            card_last_four="1234",
        )
        assert result["status"] == "declined"
        assert result["authorization_code"] is None

    @pytest.mark.asyncio
    async def test_data_sent_to_repo_contains_currency(self):
        service, repo = _make_service()
        row = make_transaction_row(currency="JPY", status="approved")
        repo.create.return_value = row
        await service.create_transaction(
            amount=Decimal("500.00"),
            currency="JPY",
            merchant="Tokyo Shop",
            card_last_four="5678",
        )
        call_args = repo.create.call_args[0][0]
        assert call_args["currency"] == "JPY"

    @pytest.mark.asyncio
    async def test_data_sent_to_repo_contains_card_last_four(self):
        service, repo = _make_service()
        row = make_transaction_row(card_last_four="7777", status="approved")
        repo.create.return_value = row
        await service.create_transaction(
            amount=Decimal("10.00"),
            currency="USD",
            merchant="Any Shop",
            card_last_four="7777",
        )
        call_args = repo.create.call_args[0][0]
        assert call_args["card_last_four"] == "7777"


class TestGetTransaction:
    @pytest.mark.asyncio
    async def test_returns_transaction_when_found(self):
        service, repo = _make_service()
        tx_id = uuid.uuid4()
        row = make_transaction_row(id=tx_id)
        repo.get_by_id.return_value = row
        result = await service.get_transaction(tx_id)
        assert result["id"] == tx_id
        assert result["is_simulated"] is True

    @pytest.mark.asyncio
    async def test_raises_not_found_when_missing(self):
        service, repo = _make_service()
        repo.get_by_id.return_value = None
        with pytest.raises(NotFoundError):
            await service.get_transaction(uuid.uuid4())

    @pytest.mark.asyncio
    async def test_calls_repo_with_correct_id(self):
        service, repo = _make_service()
        tx_id = uuid.uuid4()
        row = make_transaction_row(id=tx_id)
        repo.get_by_id.return_value = row
        await service.get_transaction(tx_id)
        repo.get_by_id.assert_called_once_with(tx_id)


class TestGetServiceInfo:
    @pytest.mark.asyncio
    async def test_returns_service_info_from_db(self):
        service, repo = _make_service()
        repo.get_demo_service_info.return_value = make_service_row()
        result = await service.get_service_info()
        assert result["name"] == "ForgeGuard Payment Service"
        assert result["is_demo"] is True
        assert isinstance(result["capabilities"], list)

    @pytest.mark.asyncio
    async def test_returns_fallback_when_service_missing(self):
        service, repo = _make_service()
        repo.get_demo_service_info.return_value = None
        result = await service.get_service_info()
        assert result["name"] == "ForgeGuard Payment Service"
        assert result["is_demo"] is True
        assert result["version"] == "1.0.0"

    @pytest.mark.asyncio
    async def test_capabilities_is_list(self):
        service, repo = _make_service()
        repo.get_demo_service_info.return_value = make_service_row()
        result = await service.get_service_info()
        assert isinstance(result["capabilities"], list)
        assert len(result["capabilities"]) > 0

    @pytest.mark.asyncio
    async def test_health_score_is_none(self):
        service, repo = _make_service()
        repo.get_demo_service_info.return_value = make_service_row()
        result = await service.get_service_info()
        assert result["health_score"] is None

    @pytest.mark.asyncio
    async def test_handles_string_metadata(self):
        """Service must parse JSON string metadata from asyncpg row."""
        import json

        service, repo = _make_service()
        svc_row = make_service_row()
        svc_row["metadata"] = json.dumps(svc_row["metadata"])
        repo.get_demo_service_info.return_value = svc_row
        result = await service.get_service_info()
        assert result["version"] == "1.0.0"


class TestResetDemoData:
    @pytest.mark.asyncio
    async def test_returns_purged_count(self):
        service, repo = _make_service()
        repo.delete_all_demo_transactions.return_value = 5
        result = await service.reset_demo_data()
        assert result["purged_count"] == 5

    @pytest.mark.asyncio
    async def test_returns_zero_when_no_data(self):
        service, repo = _make_service()
        repo.delete_all_demo_transactions.return_value = 0
        result = await service.reset_demo_data()
        assert result["purged_count"] == 0

    @pytest.mark.asyncio
    async def test_returns_message_string(self):
        service, repo = _make_service()
        repo.delete_all_demo_transactions.return_value = 3
        result = await service.reset_demo_data()
        assert isinstance(result["message"], str)
        assert "3" in result["message"]

    @pytest.mark.asyncio
    async def test_returns_reset_at_datetime(self):
        service, repo = _make_service()
        repo.delete_all_demo_transactions.return_value = 0
        result = await service.reset_demo_data()
        assert isinstance(result["reset_at"], datetime)

    @pytest.mark.asyncio
    async def test_calls_delete_all(self):
        service, repo = _make_service()
        repo.delete_all_demo_transactions.return_value = 2
        await service.reset_demo_data()
        repo.delete_all_demo_transactions.assert_called_once()
