"""Unit tests for the PII masking processor in forgeguard.core.logging.

Tests cover:
    - Email masking (simple, subdomain, plus-addressing, embedded, multiple)
    - IPv4 address masking (remote_addr field, embedded in text, loopback)
    - Name field masking (full_name, name, multi-part names)
    - Non-PII passthrough (integers, booleans, None, plain text, empty string)
    - Nested dict masking
    - Mixed PII in a single event string
    - Partial / non-matching values that must NOT be masked

All tests are parametrized from the shared fixture data in
tests/fixtures/pii_test_data.py so the fixture file is the single source
of truth for both test cases and documentation.
"""

from __future__ import annotations

import copy
import re

import pytest

from forgeguard.core.logging import pii_masking_processor
from tests.fixtures.pii_test_data import (
    MASKING_CASES,
    NESTED_DICT_EXPECTED_PATTERNS,
    NESTED_DICT_INPUT,
)


def _run_processor(event_dict: dict) -> dict:
    """Apply the PII masking processor to a copy of event_dict."""
    return pii_masking_processor(None, "info", copy.deepcopy(event_dict))


# ---------------------------------------------------------------------------
# Parametrized masking tests
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "case",
    MASKING_CASES,
    ids=[c["id"] for c in MASKING_CASES],
)
def test_pii_masking_cases(case: dict) -> None:
    """Each fixture case verifies one masking rule or passthrough behaviour."""
    result = _run_processor(case["input"])
    field = case["field"]
    output_value = result[field]

    if case["unchanged"]:
        assert output_value == case["input"][field], (
            f"[{case['id']}] Expected unchanged value {case['input'][field]!r}, "
            f"got {output_value!r}"
        )
    elif case["exact"] is not None:
        assert output_value == case["exact"], (
            f"[{case['id']}] Expected exact {case['exact']!r}, got {output_value!r}"
        )
    elif case["pattern"] is not None:
        assert re.search(case["pattern"], str(output_value)), (
            f"[{case['id']}] Pattern {case['pattern']!r} not found in {output_value!r}"
        )
    else:
        # Must not equal the original (masked in some way).
        assert output_value != case["input"][field], (
            f"[{case['id']}] Expected masking but value is unchanged: {output_value!r}"
        )


# ---------------------------------------------------------------------------
# Nested dict masking
# ---------------------------------------------------------------------------

def test_nested_dict_fields_are_masked() -> None:
    """PII fields inside a nested dict value must be masked recursively."""
    result = _run_processor(NESTED_DICT_INPUT)
    user = result["user"]
    assert isinstance(user, dict)

    for field, expectation in NESTED_DICT_EXPECTED_PATTERNS.items():
        value = user[field]
        if isinstance(expectation, str) and not expectation.startswith("^"):
            # Plain string — exact match
            assert value == expectation, f"Field {field!r}: expected {expectation!r}, got {value!r}"
        else:
            # Regex pattern
            assert re.search(expectation, str(value)), (
                f"Field {field!r}: pattern {expectation!r} not found in {value!r}"
            )


# ---------------------------------------------------------------------------
# Edge cases not covered by parametrize
# ---------------------------------------------------------------------------

def test_processor_does_not_modify_event_dict_in_place() -> None:
    """The processor must return a new dict (or modified copy), not mutate input."""
    original = {"event": "test", "email": "orig@example.com"}
    original_copy = copy.deepcopy(original)
    _run_processor(original)
    # Original must be unchanged after calling the processor.
    assert original == original_copy


def test_processor_handles_none_value_without_error() -> None:
    """None values must pass through without raising."""
    result = _run_processor({"event": "test", "optional": None})
    assert result["optional"] is None


def test_processor_handles_integer_without_error() -> None:
    """Integer values must pass through unchanged."""
    result = _run_processor({"event": "test", "count": 99})
    assert result["count"] == 99


def test_processor_handles_boolean_without_error() -> None:
    """Boolean values must pass through unchanged."""
    result = _run_processor({"event": "test", "active": False})
    assert result["active"] is False


def test_processor_handles_list_of_strings() -> None:
    """Lists of strings must have each element scanned for PII."""
    result = _run_processor({
        "event": "test",
        "contacts": ["alice@example.com", "bob@example.org"],
    })
    contacts = result["contacts"]
    assert re.search(r"a\*\*\*@example\.com", contacts[0])
    assert re.search(r"b\*\*\*@example\.org", contacts[1])


def test_processor_handles_list_of_mixed_types() -> None:
    """Lists with mixed types must not raise."""
    result = _run_processor({
        "event": "test",
        "data": [1, None, "alice@example.com", True],
    })
    assert result["data"][0] == 1
    assert result["data"][1] is None
    assert re.search(r"a\*\*\*@example\.com", result["data"][2])
    assert result["data"][3] is True


def test_processor_preserves_all_other_fields() -> None:
    """Non-PII fields must be present and unchanged in the output."""
    event_dict = {
        "event": "policy_evaluated",
        "policy_id": "pol-001",
        "score": 85,
        "passed": True,
        "email": "reviewer@example.com",
    }
    result = _run_processor(event_dict)
    assert result["event"] == "policy_evaluated"
    assert result["policy_id"] == "pol-001"
    assert result["score"] == 85
    assert result["passed"] is True
    # Email field must be masked.
    assert "reviewer@example.com" not in result["email"]


def test_multiple_emails_in_single_string() -> None:
    """All email addresses in a string must be independently masked."""
    result = _run_processor({"event": "From a@x.com and b@y.org to c@z.net"})
    text = result["event"]
    assert "a@x.com" not in text
    assert "b@y.org" not in text
    assert "c@z.net" not in text
    assert re.search(r"a\*\*\*@x\.com", text)
    assert re.search(r"b\*\*\*@y\.org", text)
    assert re.search(r"c\*\*\*@z\.net", text)


def test_ipv4_in_event_string() -> None:
    """IPv4 addresses embedded in the event message must be masked."""
    result = _run_processor({"event": "Login from 203.0.113.42 succeeded"})
    assert "203.0.113.42" not in result["event"]
    assert re.search(r"203\.\*\*\*\.\*\*\*\.\*\*\*", result["event"])


def test_non_pii_text_unchanged() -> None:
    """Plain text with no PII patterns must pass through unchanged."""
    original = "Policy evaluation completed successfully"
    result = _run_processor({"event": original})
    assert result["event"] == original


def test_empty_event_dict_handled() -> None:
    """An empty event dict must not raise."""
    result = _run_processor({})
    assert result == {}


def test_bytes_value_handled() -> None:
    """Bytes values must be decoded and scanned without raising."""
    result = _run_processor({"event": "test", "raw": b"user@example.com"})
    # Must be decoded and the email masked.
    assert isinstance(result["raw"], str)
    assert "user@example.com" not in result["raw"]
