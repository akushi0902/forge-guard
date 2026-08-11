"""Integration tests for PII filter middleware and structlog processor.

Validates that when the pii_filter_processor is active in the structlog
pipeline, no raw PII (email, name, IP address) appears in captured log output.

Test strategy:
  1. Configure a structlog pipeline with pii_filter_processor + a custom
     capturing renderer that stores event dicts for inspection.
  2. Emit log events containing PII field names.
  3. Assert captured output contains masked values, not raw PII.
  4. Test one-level nested dict masking.
  5. Test that unknown field names pass through unchanged.
  6. Integration: HTTP request with PII in body triggers route handler that
     logs PII fields; captured output must not contain raw PII.
"""

from __future__ import annotations

from typing import Any, AsyncGenerator

import pytest
import pytest_asyncio
import structlog
from fastapi import FastAPI, Request
from httpx import ASGITransport, AsyncClient

from forgeguard.middleware.pii_filter import pii_filter_processor
from forgeguard.middleware.request_id import RequestIDMiddleware


# ---------------------------------------------------------------------------
# Log-capture infrastructure
# ---------------------------------------------------------------------------

class _LogCapture:
    """Accumulates processed event dicts emitted through the structlog chain."""

    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []

    def __call__(
        self,
        _logger: Any,
        _method: str,
        event_dict: dict[str, Any],
    ) -> dict[str, Any]:
        self.events.append(dict(event_dict))
        raise structlog.DropEvent()


def _configure_structlog_with_capture(capture: _LogCapture) -> None:
    """Reconfigure structlog to run the PII filter and then capture events."""
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            pii_filter_processor,
            capture,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(0),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=False,
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def log_capture() -> _LogCapture:
    """Fresh LogCapture instance with structlog reconfigured to use it."""
    capture = _LogCapture()
    _configure_structlog_with_capture(capture)
    return capture


def _make_logging_app() -> FastAPI:
    """Minimal app with routes that log PII fields."""
    app = FastAPI()
    app.add_middleware(RequestIDMiddleware)

    @app.post("/create-user")
    async def create_user(request: Request) -> dict:
        body = await request.json()
        log = structlog.get_logger("test.route")
        log.info(
            "user_created",
            email=body.get("email"),
            name=body.get("name"),
            ip_address=request.client.host if request.client else "unknown",
        )
        return {"status": "ok"}

    @app.get("/get-user")
    async def get_user() -> dict:
        log = structlog.get_logger("test.route")
        log.info("user_retrieved", email="alice@example.com", ip_address="192.168.1.1")
        return {"status": "ok"}

    return app


@pytest_asyncio.fixture()
async def logging_client(log_capture: _LogCapture) -> AsyncGenerator[AsyncClient, None]:
    app = _make_logging_app()
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        yield client


# ---------------------------------------------------------------------------
# Processor unit tests — directly invoke pii_filter_processor
# ---------------------------------------------------------------------------

class TestPIIFilterProcessorDirect:
    def test_email_field_masked(self) -> None:
        event = {"event": "login", "email": "alice@example.com"}
        result = pii_filter_processor(None, "info", event)
        assert result["email"] != "alice@example.com"
        assert "@" in result["email"]
        assert result["email"].startswith("a")
        assert "***" in result["email"]

    def test_name_field_masked(self) -> None:
        event = {"event": "signup", "name": "John Doe"}
        result = pii_filter_processor(None, "info", event)
        assert result["name"] == "J*** D***"

    def test_ip_address_field_masked(self) -> None:
        event = {"event": "request", "ip_address": "192.168.1.100"}
        result = pii_filter_processor(None, "info", event)
        assert result["ip_address"] == "192.168.***.***"

    def test_client_ip_masked(self) -> None:
        event = {"event": "request", "client_ip": "10.0.0.5"}
        result = pii_filter_processor(None, "info", event)
        assert result["client_ip"] == "10.0.***.***"

    def test_unknown_field_unchanged(self) -> None:
        event = {"event": "test", "service_name": "my-service"}
        result = pii_filter_processor(None, "info", event)
        assert result["service_name"] == "my-service"

    def test_event_message_unchanged(self) -> None:
        event = {"event": "user_created"}
        result = pii_filter_processor(None, "info", event)
        assert result["event"] == "user_created"

    def test_nested_dict_pii_masked(self) -> None:
        event = {
            "event": "audit",
            "user": {"email": "bob@example.com", "role": "admin"},
        }
        result = pii_filter_processor(None, "info", event)
        # Nested dict under "user" — values with PII key names are masked
        nested = result["user"]
        assert nested["email"] != "bob@example.com"
        assert nested["role"] == "admin"

    def test_multiple_pii_fields_all_masked(self) -> None:
        event = {
            "event": "request_received",
            "email": "carol@example.com",
            "name": "Carol White",
            "ip_address": "172.16.0.1",
        }
        result = pii_filter_processor(None, "info", event)
        assert "carol@example.com" not in str(result)
        assert "Carol White" not in str(result)
        assert "172.16.0.1" not in str(result)

    def test_none_value_handled(self) -> None:
        event = {"event": "test", "email": None}
        result = pii_filter_processor(None, "info", event)
        assert result["email"] is None  # None is not masked

    def test_integer_value_passed_through(self) -> None:
        event = {"event": "test", "count": 42}
        result = pii_filter_processor(None, "info", event)
        assert result["count"] == 42

    def test_list_of_emails_masked(self) -> None:
        event = {
            "event": "bulk",
            "email": ["alice@example.com", "bob@example.com"],
        }
        result = pii_filter_processor(None, "info", event)
        # List of strings in PII field — each element processed
        assert result["email"] != ["alice@example.com", "bob@example.com"]


# ---------------------------------------------------------------------------
# Structlog integration — captured output contains no raw PII
# ---------------------------------------------------------------------------

class TestStructlogCapture:
    def test_email_not_in_captured_output(self, log_capture: _LogCapture) -> None:
        logger = structlog.get_logger("test")
        logger.info("login", email="testuser@example.com")
        assert log_capture.events, "No events captured"
        last = log_capture.events[-1]
        assert last.get("email") != "testuser@example.com"
        assert "***" in str(last.get("email", ""))

    def test_name_not_in_captured_output(self, log_capture: _LogCapture) -> None:
        logger = structlog.get_logger("test")
        logger.info("profile_updated", name="Jane Smith")
        last = log_capture.events[-1]
        assert last.get("name") == "J*** S***"

    def test_ip_not_in_captured_output(self, log_capture: _LogCapture) -> None:
        logger = structlog.get_logger("test")
        logger.info("request", ip_address="10.20.30.40")
        last = log_capture.events[-1]
        assert last.get("ip_address") == "10.20.***.***"

    def test_non_pii_field_in_captured_output(self, log_capture: _LogCapture) -> None:
        logger = structlog.get_logger("test")
        logger.info("check", service_id="abc-123")
        last = log_capture.events[-1]
        assert last.get("service_id") == "abc-123"


# ---------------------------------------------------------------------------
# HTTP integration — request → route handler logs → captured output
# ---------------------------------------------------------------------------

class TestHTTPIntegration:
    async def test_email_masked_in_logs(
        self, logging_client: AsyncClient, log_capture: _LogCapture
    ) -> None:
        r = await logging_client.post(
            "/create-user",
            json={"email": "user@example.com", "name": "Test User"},
        )
        assert r.status_code == 200

        raw_emails = [
            e for e in log_capture.events
            if e.get("email") == "user@example.com"
        ]
        assert raw_emails == [], (
            "Raw email should not appear in log events; "
            f"found: {raw_emails}"
        )

    async def test_ip_masked_in_logs(
        self, logging_client: AsyncClient, log_capture: _LogCapture
    ) -> None:
        await logging_client.get("/get-user")
        raw_ips = [
            e for e in log_capture.events
            if e.get("ip_address") == "192.168.1.1"
        ]
        assert raw_ips == [], f"Raw IP should not appear in logs; found: {raw_ips}"

    async def test_masked_values_present_in_logs(
        self, logging_client: AsyncClient, log_capture: _LogCapture
    ) -> None:
        await logging_client.post(
            "/create-user",
            json={"email": "alice@example.com", "name": "Alice Wonder"},
        )
        email_events = [e for e in log_capture.events if "email" in e]
        assert email_events, "Expected at least one log event with 'email' field"
        for event in email_events:
            assert "***" in str(event["email"]), (
                f"Email should be masked; got: {event['email']}"
            )
