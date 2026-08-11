"""Unit tests for DemoResponseEnvelope generic wrapper (WO-057).

Verifies:
  * Envelope adds is_simulated, data_classification, simulation_disclaimer
  * Generic type parameter T preserves inner model validation
  * Simulation fields use the canonical constant values
  * Non-demo payloads returned directly (without envelope) contain no sim fields
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal

import pytest
from pydantic import BaseModel

from forgeguard.api.schemas.demo_wrapper import DemoResponseEnvelope
from forgeguard.constants.demo import DATA_CLASSIFICATION_SIMULATED, SIMULATION_DISCLAIMER


# ---------------------------------------------------------------------------
# Sample inner models
# ---------------------------------------------------------------------------

class _SimplePing(BaseModel):
    message: str
    count: int


class _TransactionLike(BaseModel):
    id: uuid.UUID
    amount: Decimal
    currency: str


# ---------------------------------------------------------------------------
# Tests for DemoResponseEnvelope
# ---------------------------------------------------------------------------

class TestDemoResponseEnvelopeFields:
    def test_is_simulated_defaults_to_true(self):
        ping = _SimplePing(message="hello", count=1)
        envelope = DemoResponseEnvelope[_SimplePing](data=ping)
        assert envelope.is_simulated is True

    def test_data_classification_is_simulated_literal(self):
        ping = _SimplePing(message="hello", count=1)
        envelope = DemoResponseEnvelope[_SimplePing](data=ping)
        assert envelope.data_classification == "simulated"

    def test_data_classification_matches_constant(self):
        ping = _SimplePing(message="hello", count=1)
        envelope = DemoResponseEnvelope[_SimplePing](data=ping)
        assert envelope.data_classification == DATA_CLASSIFICATION_SIMULATED

    def test_simulation_disclaimer_matches_constant(self):
        ping = _SimplePing(message="hello", count=1)
        envelope = DemoResponseEnvelope[_SimplePing](data=ping)
        assert envelope.simulation_disclaimer == SIMULATION_DISCLAIMER

    def test_simulation_disclaimer_is_non_empty_string(self):
        ping = _SimplePing(message="hello", count=1)
        envelope = DemoResponseEnvelope[_SimplePing](data=ping)
        assert isinstance(envelope.simulation_disclaimer, str)
        assert len(envelope.simulation_disclaimer) > 0

    def test_disclaimer_contains_no_raw_payment_credentials_text(self):
        ping = _SimplePing(message="hello", count=1)
        envelope = DemoResponseEnvelope[_SimplePing](data=ping)
        assert "payment credentials" in envelope.simulation_disclaimer.lower()


class TestDemoResponseEnvelopeGenericPreservation:
    def test_data_field_preserves_inner_type(self):
        ping = _SimplePing(message="test", count=42)
        envelope = DemoResponseEnvelope[_SimplePing](data=ping)
        assert isinstance(envelope.data, _SimplePing)
        assert envelope.data.message == "test"
        assert envelope.data.count == 42

    def test_data_field_with_transaction_like_model(self):
        tx_id = uuid.uuid4()
        tx = _TransactionLike(id=tx_id, amount=Decimal("99.99"), currency="USD")
        envelope = DemoResponseEnvelope[_TransactionLike](data=tx)
        assert envelope.data.id == tx_id
        assert envelope.data.amount == Decimal("99.99")
        assert envelope.data.currency == "USD"

    def test_envelope_serialises_to_dict_with_all_fields(self):
        ping = _SimplePing(message="world", count=7)
        envelope = DemoResponseEnvelope[_SimplePing](data=ping)
        d = envelope.model_dump()
        assert "data" in d
        assert "is_simulated" in d
        assert "data_classification" in d
        assert "simulation_disclaimer" in d

    def test_envelope_json_round_trip(self):
        ping = _SimplePing(message="json", count=99)
        envelope = DemoResponseEnvelope[_SimplePing](data=ping)
        json_str = envelope.model_dump_json()
        restored = DemoResponseEnvelope[_SimplePing].model_validate_json(json_str)
        assert restored.is_simulated is True
        assert restored.data.message == "json"

    def test_data_nested_in_envelope_dict(self):
        ping = _SimplePing(message="nested", count=3)
        envelope = DemoResponseEnvelope[_SimplePing](data=ping)
        d = envelope.model_dump()
        assert d["data"]["message"] == "nested"
        assert d["data"]["count"] == 3


class TestDemoResponseEnvelopeIsolation:
    def test_direct_non_demo_model_has_no_sim_fields(self):
        """Non-demo payloads returned without DemoResponseEnvelope have no sim fields."""
        class RealServiceInfo(BaseModel):
            id: uuid.UUID
            name: str
            is_demo: bool = False

        real = RealServiceInfo(id=uuid.uuid4(), name="Auth Service")
        d = real.model_dump()
        assert "is_simulated" not in d
        assert "data_classification" not in d
        assert "simulation_disclaimer" not in d

    def test_two_envelopes_are_independent(self):
        ping1 = _SimplePing(message="first", count=1)
        ping2 = _SimplePing(message="second", count=2)
        e1 = DemoResponseEnvelope[_SimplePing](data=ping1)
        e2 = DemoResponseEnvelope[_SimplePing](data=ping2)
        assert e1.data.message == "first"
        assert e2.data.message == "second"
        assert e1.is_simulated == e2.is_simulated


class TestDemoResponseEnvelopeConstants:
    def test_simulation_disclaimer_no_json_breaking_chars(self):
        """Disclaimer must not contain characters that break JSON serialisation."""
        import json  # noqa: PLC0415
        ping = _SimplePing(message="ok", count=0)
        envelope = DemoResponseEnvelope[_SimplePing](data=ping)
        # Should not raise
        serialised = json.dumps(envelope.model_dump())
        restored = json.loads(serialised)
        assert restored["simulation_disclaimer"] == SIMULATION_DISCLAIMER

    def test_data_classification_is_exactly_simulated(self):
        ping = _SimplePing(message="ok", count=0)
        envelope = DemoResponseEnvelope[_SimplePing](data=ping)
        assert envelope.data_classification == "simulated"
