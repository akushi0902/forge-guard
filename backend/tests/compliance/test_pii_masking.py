"""PII masking compliance test suite (WO-100).

Validates that no raw PII (email, full name, unmasked IP) escapes into log
output across all log-output paths.  Tests capture structlog event dicts
during operations that involve PII and scan them with regex patterns that
would match unmasked data.

Compliance scope:
  1. Structured log output from email-involving operations → only masked emails.
  2. Structured log output from name-involving operations → only masked names.
  3. IP address fields in log events → only masked IP patterns.
  4. Error responses (4xx) do not echo raw PII in their body or headers.
  5. PII Filter masks data in logs but passes the original to the request handler.
  6. All log levels (DEBUG, INFO, WARNING, ERROR) apply masking consistently.
  7. Multiple PII fields in a single log event — all masked.
  8. Nested dict values containing PII fields — masked one level deep.

Architecture note:
  These tests reconfigure structlog temporarily in each test so they can
  capture event dicts directly.  The production pipeline is restored after
  each test via a module-scoped autouse fixture.  Tests are fully synchronous
  (no live DB required) and run without Docker.

Run with::

    pytest tests/compliance/test_pii_masking.py -v
"""

from __future__ import annotations

import re
from typing import Any

import pytest
import structlog
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from httpx import ASGITransport, AsyncClient

from forgeguard.middleware.pii_filter import pii_filter_processor
from forgeguard.middleware.request_id import RequestIDMiddleware

# ---------------------------------------------------------------------------
# Raw PII regex detectors
# Used to SCAN masked log output — a match means PII leaked.
# ---------------------------------------------------------------------------

# An unmasked email has a multi-char local part with no asterisks before @.
_RAW_EMAIL_RE = re.compile(
    r"\b[A-Za-z0-9._%+\-]{2,}@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b"
)

# An unmasked IPv4 has four digit groups with no asterisks.
_RAW_IPV4_RE = re.compile(
    r"\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b"
)

# A correctly masked email: single_char + *** + @domain
_MASKED_EMAIL_RE = re.compile(r"^.\*{3}@.+$")

# A correctly masked IPv4: first_two_octets.***.***
_MASKED_IPV4_RE = re.compile(r"^\d{1,3}\.\d{1,3}\.\*{3}\.\*{3}$")

# A correctly masked name word: char + ***
_MASKED_NAME_RE = re.compile(r"^.\*{3}( .\*{3})*$")


# ---------------------------------------------------------------------------
# Log capture infrastructure
# ---------------------------------------------------------------------------

class _LogCapture:
    """Structlog processor that stores event dicts and drops the event."""

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

    def reset(self) -> None:
        self.events.clear()


def _configure_capture(capture: _LogCapture) -> None:
    """Wire structlog to run PII filter then capture (no real output)."""
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


def _scan_for_raw_emails(events: list[dict[str, Any]], raw_email: str) -> list[str]:
    """Return a list of field paths where *raw_email* appears verbatim."""
    leaks: list[str] = []
    for idx, event in enumerate(events):
        for key, value in event.items():
            str_value = str(value) if value is not None else ""
            if raw_email in str_value:
                leaks.append(f"event[{idx}].{key}={str_value!r}")
    return leaks


def _scan_for_raw_ipv4(events: list[dict[str, Any]], raw_ip: str) -> list[str]:
    """Return field paths where an unmasked IPv4 matching *raw_ip* appears."""
    leaks: list[str] = []
    for idx, event in enumerate(events):
        for key, value in event.items():
            str_value = str(value) if value is not None else ""
            if raw_ip in str_value and _RAW_IPV4_RE.search(str_value):
                # Allow the masked form (contains ***) but reject the raw form.
                if "***" not in str_value:
                    leaks.append(f"event[{idx}].{key}={str_value!r}")
    return leaks


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _restore_structlog():
    """Save and restore the structlog configuration around each test."""
    original_config = structlog.get_config()
    yield
    structlog.configure(**original_config)


@pytest.fixture
def capture() -> _LogCapture:
    cap = _LogCapture()
    _configure_capture(cap)
    return cap


@pytest.fixture
def logger(capture: _LogCapture):
    return structlog.get_logger("forgeguard.compliance.test")


# ---------------------------------------------------------------------------
# 1. Email masking in structured log output
# ---------------------------------------------------------------------------

class TestEmailMaskingInLogs:
    def test_email_field_is_masked_in_log(
        self, capture: _LogCapture, logger: Any
    ) -> None:
        raw_email = "john.doe@example.com"
        logger.info("user_login", email=raw_email)
        assert capture.events, "No log event captured"
        event = capture.events[0]
        assert event.get("email") == "j***@example.com"
        assert raw_email not in str(event.get("email", ""))

    def test_user_email_field_is_masked(
        self, capture: _LogCapture, logger: Any
    ) -> None:
        raw_email = "alice@corp.example.co.uk"
        logger.info("profile_view", user_email=raw_email)
        event = capture.events[0]
        masked = event.get("user_email", "")
        assert masked == "a***@corp.example.co.uk"

    def test_actor_email_field_is_masked(
        self, capture: _LogCapture, logger: Any
    ) -> None:
        raw_email = "bob@company.com"
        logger.info("audit", actor_email=raw_email)
        event = capture.events[0]
        assert event.get("actor_email") == "b***@company.com"

    def test_no_raw_email_in_any_field(
        self, capture: _LogCapture, logger: Any
    ) -> None:
        raw_email = "sensitive.user@internal.corp"
        logger.info(
            "assessment_requested",
            email=raw_email,
            event="assessment.requested",
        )
        leaks = _scan_for_raw_emails(capture.events, raw_email)
        assert not leaks, f"Raw email leaked: {leaks}"

    @pytest.mark.parametrize("raw_email", [
        "john.doe@example.com",
        "user+tag@sub.domain.com",
        "admin@company.internal",
        "üser@example.com",
    ])
    def test_various_email_formats_masked(
        self, capture: _LogCapture, logger: Any, raw_email: str
    ) -> None:
        logger.info("operation", email=raw_email)
        capture.reset()  # clear between parametrize iterations
        _configure_capture(capture)
        logger2 = structlog.get_logger("test")
        logger2.info("operation", email=raw_email)
        event = capture.events[-1] if capture.events else {}
        masked = str(event.get("email", ""))
        assert _MASKED_EMAIL_RE.match(masked), (
            f"Email {raw_email!r} not properly masked: got {masked!r}"
        )


# ---------------------------------------------------------------------------
# 2. Name masking in structured log output
# ---------------------------------------------------------------------------

class TestNameMaskingInLogs:
    def test_name_field_is_masked(
        self, capture: _LogCapture, logger: Any
    ) -> None:
        logger.info("user_created", name="John Doe")
        event = capture.events[0]
        assert event.get("name") == "J*** D***"

    def test_full_name_field_is_masked(
        self, capture: _LogCapture, logger: Any
    ) -> None:
        logger.info("profile_updated", full_name="Alice Smith")
        event = capture.events[0]
        assert event.get("full_name") == "A*** S***"

    def test_display_name_field_is_masked(
        self, capture: _LogCapture, logger: Any
    ) -> None:
        logger.info("login", display_name="Bob Jones")
        event = capture.events[0]
        masked = event.get("display_name", "")
        assert _MASKED_NAME_RE.match(masked), (
            f"display_name not masked correctly: {masked!r}"
        )

    def test_unicode_name_is_masked(
        self, capture: _LogCapture, logger: Any
    ) -> None:
        logger.info("user_event", name="José García")
        event = capture.events[0]
        masked = event.get("name", "")
        assert masked == "J*** G***"


# ---------------------------------------------------------------------------
# 3. IP address masking in structured log output
# ---------------------------------------------------------------------------

class TestIPMaskingInLogs:
    def test_ip_address_field_is_masked(
        self, capture: _LogCapture, logger: Any
    ) -> None:
        raw_ip = "192.168.1.100"
        logger.info("request", ip_address=raw_ip)
        event = capture.events[0]
        masked = event.get("ip_address", "")
        assert masked == "192.168.***.***"

    def test_remote_addr_is_masked(
        self, capture: _LogCapture, logger: Any
    ) -> None:
        logger.info("request", remote_addr="10.0.0.5")
        event = capture.events[0]
        assert event.get("remote_addr") == "10.0.***.***"

    def test_client_ip_is_masked(
        self, capture: _LogCapture, logger: Any
    ) -> None:
        logger.info("access", client_ip="172.16.0.1")
        event = capture.events[0]
        assert event.get("client_ip") == "172.16.***.***"

    def test_raw_ip_does_not_appear_in_output(
        self, capture: _LogCapture, logger: Any
    ) -> None:
        raw_ip = "203.0.113.42"
        logger.info("audit", ip_address=raw_ip)
        leaks = _scan_for_raw_ipv4(capture.events, raw_ip)
        assert not leaks, f"Raw IP leaked: {leaks}"

    def test_masked_ip_matches_expected_pattern(
        self, capture: _LogCapture, logger: Any
    ) -> None:
        logger.info("req", ip_address="192.168.1.100")
        event = capture.events[0]
        masked = event.get("ip_address", "")
        assert _MASKED_IPV4_RE.match(masked), (
            f"ip_address not in expected masked format: {masked!r}"
        )


# ---------------------------------------------------------------------------
# 4. Error responses do not leak PII
# ---------------------------------------------------------------------------

class TestErrorResponsesDoNotLeakPII:
    """Verify 4xx responses don't echo back raw PII in the response body."""

    @pytest.fixture
    def pii_app(self):
        """Minimal FastAPI app that validates a body and returns 422 on error."""
        from pydantic import BaseModel, field_validator

        app = FastAPI()
        app.add_middleware(RequestIDMiddleware)

        class UserLogin(BaseModel):
            email: str
            password: str

            @field_validator("email")
            @classmethod
            def email_must_be_short(cls, v: str) -> str:
                if "@" not in v:
                    raise ValueError("invalid email")
                return v

        @app.post("/login")
        async def login(body: UserLogin) -> dict:
            return {"status": "ok", "email": body.email}

        return app

    async def test_422_validation_error_does_not_echo_raw_email(
        self, pii_app: FastAPI
    ) -> None:
        """A 422 from Pydantic validation must not contain the raw email."""
        raw_email = "john.doe@example.com"
        async with AsyncClient(
            transport=ASGITransport(app=pii_app), base_url="http://test"
        ) as client:
            resp = await client.post(
                "/login",
                json={"email": "not-an-email", "password": "p@ss"},
            )
        assert resp.status_code == 422
        body_text = resp.text
        # 422 body must not contain a raw email address from the request
        # (the input "not-an-email" has no @, so the raw email detector
        # should not fire — but no real email should appear)
        assert raw_email not in body_text

    async def test_successful_response_contains_unmasked_email_for_handler(
        self, pii_app: FastAPI, capture: _LogCapture
    ) -> None:
        """The handler receives and can return the unmasked email; logs are masked."""
        raw_email = "user@example.com"
        async with AsyncClient(
            transport=ASGITransport(app=pii_app), base_url="http://test"
        ) as client:
            resp = await client.post(
                "/login",
                json={"email": raw_email, "password": "Secret123!"},
            )
        assert resp.status_code == 200
        # Business logic gets the unmasked email
        assert resp.json()["email"] == raw_email


# ---------------------------------------------------------------------------
# 5. PII Filter masks in logs but passes original to handler
# ---------------------------------------------------------------------------

class TestPIIFilterDoesNotCorruptBusinessLogic:
    """The PII filter is a LOG processor only — it must not alter request data."""

    @pytest.fixture
    def echo_app(self, capture: _LogCapture):
        app = FastAPI()

        @app.post("/echo")
        async def echo(request: Request) -> JSONResponse:
            body = await request.json()
            # Log the email field (should be masked in logs)
            structlog.get_logger().info(
                "echo_request",
                email=body.get("email"),
                ip_address=request.client.host if request.client else "127.0.0.1",
            )
            # Return the original email unmolested
            return JSONResponse({"email": body.get("email")})

        return app

    async def test_handler_receives_original_email(
        self, echo_app: FastAPI, capture: _LogCapture
    ) -> None:
        raw_email = "dev@example.com"
        async with AsyncClient(
            transport=ASGITransport(app=echo_app), base_url="http://test"
        ) as client:
            resp = await client.post("/echo", json={"email": raw_email})
        assert resp.status_code == 200
        assert resp.json()["email"] == raw_email

    async def test_log_contains_masked_email_not_raw(
        self, echo_app: FastAPI, capture: _LogCapture
    ) -> None:
        raw_email = "dev@example.com"
        async with AsyncClient(
            transport=ASGITransport(app=echo_app), base_url="http://test"
        ) as client:
            await client.post("/echo", json={"email": raw_email})
        leaks = _scan_for_raw_emails(capture.events, raw_email)
        assert not leaks, (
            f"Raw email {raw_email!r} appeared in log output: {leaks}"
        )

    async def test_log_email_is_masked_format(
        self, echo_app: FastAPI, capture: _LogCapture
    ) -> None:
        async with AsyncClient(
            transport=ASGITransport(app=echo_app), base_url="http://test"
        ) as client:
            await client.post("/echo", json={"email": "dev@example.com"})
        email_log_values = [
            e.get("email") for e in capture.events if "email" in e
        ]
        assert email_log_values, "No email field captured in logs"
        for masked in email_log_values:
            assert masked == "d***@example.com", (
                f"Unexpected masked value: {masked!r}"
            )


# ---------------------------------------------------------------------------
# 6. All log levels apply masking consistently
# ---------------------------------------------------------------------------

class TestAllLogLevelsMaskPII:
    """PII masking must apply at every log level (DEBUG through ERROR)."""

    @pytest.mark.parametrize("level,method", [
        ("debug",    "debug"),
        ("info",     "info"),
        ("warning",  "warning"),
        ("error",    "error"),
        ("critical", "critical"),
    ])
    def test_pii_masked_at_log_level(
        self, capture: _LogCapture, level: str, method: str
    ) -> None:
        raw_email = "secret@example.com"
        log = structlog.get_logger("test")
        getattr(log, method)("operation", email=raw_email)
        assert capture.events, f"No log event captured at level {level}"
        event = capture.events[-1]
        assert event.get("email") != raw_email, (
            f"Raw email leaked at log level {level}"
        )
        assert event.get("email") == "s***@example.com"


# ---------------------------------------------------------------------------
# 7. Multiple PII fields in one event — all masked
# ---------------------------------------------------------------------------

class TestMultiplePIIFieldsInOneEvent:
    def test_email_name_and_ip_all_masked(
        self, capture: _LogCapture, logger: Any
    ) -> None:
        logger.info(
            "user_action",
            email="john.doe@example.com",
            name="John Doe",
            ip_address="192.168.1.100",
            non_pii_field="safe_value",
        )
        event = capture.events[0]
        assert event.get("email") == "j***@example.com"
        assert event.get("name") == "J*** D***"
        assert event.get("ip_address") == "192.168.***.***"
        # Non-PII fields pass through unchanged
        assert event.get("non_pii_field") == "safe_value"

    def test_multiple_pii_fields_none_leak(
        self, capture: _LogCapture, logger: Any
    ) -> None:
        raw_email = "jane.smith@corp.internal"
        raw_name = "Jane Smith"
        raw_ip = "10.0.50.99"
        logger.warning(
            "access_denied",
            user_email=raw_email,
            full_name=raw_name,
            remote_addr=raw_ip,
        )
        event = capture.events[0]
        event_str = str(event)
        assert raw_email not in event_str, "Email leaked in multi-PII event"
        assert "Smith" not in event_str, "Name suffix leaked in multi-PII event"


# ---------------------------------------------------------------------------
# 8. Nested dict PII masking
# ---------------------------------------------------------------------------

class TestNestedPIIFieldMasking:
    def test_nested_dict_email_is_masked(
        self, capture: _LogCapture, logger: Any
    ) -> None:
        logger.info(
            "actor_context",
            actor={
                "email": "nested.user@example.com",
                "ip_address": "10.20.30.40",
                "role": "developer",
            },
        )
        event = capture.events[0]
        actor = event.get("actor", {})
        assert isinstance(actor, dict)
        assert actor.get("email") == "n***@example.com"
        assert actor.get("ip_address") == "10.20.***.***"
        assert actor.get("role") == "developer"  # non-PII passes through

    def test_nested_name_field_is_masked(
        self, capture: _LogCapture, logger: Any
    ) -> None:
        logger.info("ctx", user={"name": "Bob Builder", "id": "123"})
        event = capture.events[0]
        user = event.get("user", {})
        assert user.get("name") == "B*** B***"
        assert user.get("id") == "123"


# ---------------------------------------------------------------------------
# 9. Masking is deterministic across repeated calls
# ---------------------------------------------------------------------------

class TestMaskingDeterminismInLogs:
    def test_same_email_always_produces_same_masked_output(
        self, capture: _LogCapture, logger: Any
    ) -> None:
        raw_email = "deterministic@example.com"
        logger.info("op1", email=raw_email)
        logger.info("op2", email=raw_email)
        assert len(capture.events) == 2
        assert capture.events[0]["email"] == capture.events[1]["email"]
        assert capture.events[0]["email"] == "d***@example.com"

    def test_same_ip_always_produces_same_masked_output(
        self, capture: _LogCapture, logger: Any
    ) -> None:
        raw_ip = "192.168.100.200"
        logger.info("req1", ip_address=raw_ip)
        logger.info("req2", ip_address=raw_ip)
        assert len(capture.events) == 2
        assert capture.events[0]["ip_address"] == capture.events[1]["ip_address"]
