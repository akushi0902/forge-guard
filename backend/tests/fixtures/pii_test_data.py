"""PII masking test fixtures.

Each fixture is a tuple of (input_event_dict, assertions_callable_or_expected_dict).
The assertions are described as keyword expectations checked by the test suite.

Structure:
    MASKING_CASES — list of dicts with:
        id          : unique test case identifier for pytest parametrize
        input       : event_dict fed into the PII masking processor
        field       : which field in the output to inspect
        pattern     : regex the output field value must match (None = no check)
        exact       : exact string the output field value must equal (None = no check)
        unchanged   : True if the output field value must equal input value exactly
"""

from __future__ import annotations

MASKING_CASES: list[dict] = [
    # ---- Email masking ---------------------------------------------------- #
    {
        "id": "email_simple",
        "input": {"event": "test", "user_email": "alice@example.com"},
        "field": "user_email",
        "pattern": r"^a\*\*\*@example\.com$",
        "exact": None,
        "unchanged": False,
    },
    {
        "id": "email_subdomain",
        "input": {"event": "test", "email": "bob.smith@mail.corp.example.co.uk"},
        "field": "email",
        "pattern": r"^b\*\*\*@mail\.corp\.example\.co\.uk$",
        "exact": None,
        "unchanged": False,
    },
    {
        "id": "email_plus_addressing",
        "input": {"event": "test", "email": "user+tag@example.com"},
        "field": "email",
        "pattern": r"^u\*\*\*@example\.com$",
        "exact": None,
        "unchanged": False,
    },
    {
        "id": "email_embedded_in_text",
        "input": {"event": "Contact user@example.com for support"},
        "field": "event",
        "pattern": r"Contact u\*\*\*@example\.com for support",
        "exact": None,
        "unchanged": False,
    },
    {
        "id": "email_multiple_in_field",
        "input": {"event": "From john@a.com to jane@b.org"},
        "field": "event",
        "pattern": r"From j\*\*\*@a\.com to j\*\*\*@b\.org",
        "exact": None,
        "unchanged": False,
    },
    {
        "id": "email_single_char_local",
        "input": {"event": "test", "email": "a@example.com"},
        "field": "email",
        # Single char: 'a' → 'a***@example.com'
        "pattern": r"^a\*\*\*@example\.com$",
        "exact": None,
        "unchanged": False,
    },
    # ---- IPv4 masking ----------------------------------------------------- #
    {
        "id": "ipv4_remote_addr",
        "input": {"event": "test", "remote_addr": "192.168.1.100"},
        "field": "remote_addr",
        "pattern": r"^192\.\*\*\*\.\*\*\*\.\*\*\*$",
        "exact": None,
        "unchanged": False,
    },
    {
        "id": "ipv4_embedded_in_text",
        "input": {"event": "Request from 10.0.0.1 forwarded"},
        "field": "event",
        "pattern": r"Request from 10\.\*\*\*\.\*\*\*\.\*\*\* forwarded",
        "exact": None,
        "unchanged": False,
    },
    {
        "id": "ipv4_loopback_masked",
        "input": {"event": "test", "ip": "127.0.0.1"},
        "field": "ip",
        "pattern": r"^127\.\*\*\*\.\*\*\*\.\*\*\*$",
        "exact": None,
        "unchanged": False,
    },
    # ---- Name masking ----------------------------------------------------- #
    {
        "id": "full_name_two_words",
        "input": {"event": "test", "full_name": "John Doe"},
        "field": "full_name",
        "exact": "J*** D***",
        "pattern": None,
        "unchanged": False,
    },
    {
        "id": "name_single_word",
        "input": {"event": "test", "name": "Alice"},
        "field": "name",
        "exact": "A***",
        "pattern": None,
        "unchanged": False,
    },
    {
        "id": "name_three_parts",
        "input": {"event": "test", "full_name": "Mary Jane Watson"},
        "field": "full_name",
        "exact": "M*** J*** W***",
        "pattern": None,
        "unchanged": False,
    },
    # ---- Non-PII passthrough ---------------------------------------------- #
    {
        "id": "non_pii_integer",
        "input": {"event": "test", "count": 42},
        "field": "count",
        "exact": None,
        "pattern": None,
        "unchanged": True,
    },
    {
        "id": "non_pii_plain_text",
        "input": {"event": "policy evaluation complete", "status": "passed"},
        "field": "status",
        "exact": "passed",
        "pattern": None,
        "unchanged": True,
    },
    {
        "id": "non_pii_empty_string",
        "input": {"event": "test", "notes": ""},
        "field": "notes",
        "exact": "",
        "pattern": None,
        "unchanged": True,
    },
    {
        "id": "non_pii_none_value",
        "input": {"event": "test", "optional_field": None},
        "field": "optional_field",
        "exact": None,
        "pattern": None,
        "unchanged": True,
    },
    {
        "id": "non_pii_boolean",
        "input": {"event": "test", "is_active": True},
        "field": "is_active",
        "exact": None,
        "pattern": None,
        "unchanged": True,
    },
    # ---- Partial / non-matching strings that look like PII --------------- #
    {
        "id": "not_email_no_domain",
        "input": {"event": "invalid@"},
        "field": "event",
        # No valid domain → pattern should NOT match → value unchanged
        "exact": "invalid@",
        "pattern": None,
        "unchanged": True,
    },
    # ---- Nested dict values ---------------------------------------------- #
    {
        "id": "nested_dict_email",
        "input": {"event": "test", "user": {"email": "nested@example.com", "role": "admin"}},
        "field": "user",
        "exact": None,
        "pattern": None,
        "unchanged": False,
    },
    # ---- Multiple PII types in one event ---------------------------------- #
    {
        "id": "mixed_pii_in_event",
        "input": {
            "event": "User admin@corp.com logged in from 203.0.113.5",
            "actor": "admin@corp.com",
        },
        "field": "event",
        "pattern": r"User a\*\*\*@corp\.com logged in from 203\.\*\*\*\.\*\*\*\.\*\*\*",
        "exact": None,
        "unchanged": False,
    },
]

# Separate fixture for verifying that nested dict values are masked
NESTED_DICT_INPUT = {
    "event": "user_action",
    "user": {
        "email": "nested@example.com",
        "ip_address": "10.20.30.40",
        "name": "Bob Smith",
        "role": "developer",
    },
}

NESTED_DICT_EXPECTED_PATTERNS = {
    "email": r"^n\*\*\*@example\.com$",
    "ip_address": r"^10\.\*\*\*\.\*\*\*\.\*\*\*$",
    "name": r"^B\*\*\*",
    "role": "developer",  # not masked
}
