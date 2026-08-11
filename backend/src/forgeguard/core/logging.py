"""Structured logging configuration for ForgeGuard.

This module owns the complete structlog processor pipeline, PII masking,
and stdlib-logging bridge. Import and call :func:`configure_logging` once
at application startup (in :func:`forgeguard.main.create_app`).

Pipeline order (applied left-to-right):
    1. merge_contextvars         — attach request_id, actor, resource, operation
    2. add_log_level             — add ``level`` field
    3. TimeStamper               — add ``timestamp`` in ISO 8601 UTC
    4. StackInfoRenderer         — render stack_info if present
    5. pii_masking_processor     — mask emails, IPs, name fields
    6. JSONRenderer (prod)       — SIEM-consumable JSON to stdout
       ConsoleRenderer (dev)     — colour-coded human-readable output

PII masking contract:
    - Email in any string field value → first char + *** + @domain
      e.g.  ``user@example.com``  →  ``u***@example.com``
    - IPv4 addresses               → first octet only
      e.g.  ``192.168.1.100``     →  ``192.***.***.***``
    - Values of known PII field names (email, name, ip_address, …)
      are fully masked with the appropriate pattern or redacted
    - Masking is deterministic: identical inputs produce identical outputs
    - Masking never raises — on error it prefixes the value with
      ``[MASKING_ERROR]`` and continues
"""

from __future__ import annotations

import logging
import re
import sys
from typing import Any

import structlog

# ---------------------------------------------------------------------------
# PII regex patterns
# ---------------------------------------------------------------------------

# RFC 5322-simplified email pattern.  Matches email addresses embedded in
# longer strings so surrounding text is preserved.
_EMAIL_RE = re.compile(
    r"\b([A-Za-z0-9._%+\-]+)@([A-Za-z0-9.\-]+\.[A-Za-z]{2,})\b"
)

# IPv4 dotted-decimal address.  We intentionally do NOT mask IPv6 in v1.
_IPV4_RE = re.compile(
    r"\b(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})\b"
)

# Field names whose values should be treated as PII regardless of pattern.
_PII_FIELD_NAMES: frozenset[str] = frozenset(
    {
        "email",
        "name",
        "full_name",
        "first_name",
        "last_name",
        "username",
        "user_name",
        "display_name",
        "ip_address",
        "remote_addr",
        "client_ip",
        "x_forwarded_for",
    }
)

# Internal logger used to emit masking errors — bypasses the PII pipeline
# to avoid infinite recursion.
_masking_error_logger = logging.getLogger("forgeguard.pii_masking")


def _mask_email(match: re.Match[str]) -> str:
    """Replace email local-part (except first char) with asterisks."""
    local, domain = match.group(1), match.group(2)
    masked_local = local[0] + "***" if local else "***"
    return f"{masked_local}@{domain}"


def _mask_ipv4(match: re.Match[str]) -> str:
    """Replace last three IPv4 octets with asterisks."""
    return f"{match.group(1)}.***.***.***"


def _mask_string(value: str) -> str:
    """Apply all masking patterns to a string in sequence."""
    value = _EMAIL_RE.sub(_mask_email, value)
    value = _IPV4_RE.sub(_mask_ipv4, value)
    return value


def _mask_name_value(value: str) -> str:
    """Mask a name field: keep first char of each word, replace rest with ***."""
    parts = value.split()
    masked = " ".join(
        (word[0] + "***" if len(word) > 1 else word) for word in parts
    )
    return masked


def _mask_value(field_name: str, value: Any) -> Any:  # noqa: ANN401
    """Mask a single event_dict value, dispatching on field name and type."""
    if value is None or isinstance(value, bool | int | float):
        return value

    if isinstance(value, bytes):
        try:
            value = value.decode("utf-8", errors="replace")
        except Exception:
            return value

    if isinstance(value, str):
        lower_field = field_name.lower()
        # Fields that carry names get word-level masking.
        if lower_field in ("name", "full_name", "first_name", "last_name", "display_name"):
            return _mask_name_value(value)
        # All other known PII fields get pattern masking on their full value.
        if lower_field in _PII_FIELD_NAMES:
            return _mask_string(value)
        # For non-PII field names, still scan the string for embedded PII.
        return _mask_string(value)

    if isinstance(value, dict):
        return {k: _mask_value(k, v) for k, v in value.items()}

    if isinstance(value, list | tuple):
        masked = [_mask_value(field_name, item) for item in value]
        return type(value)(masked)

    # Unknown types (e.g. custom objects) — convert to string and mask.
    try:
        return _mask_string(str(value))
    except Exception:
        return value


def pii_masking_processor(
    _logger: Any,  # noqa: ANN401
    _method_name: str,
    event_dict: dict[str, Any],
) -> dict[str, Any]:
    """Structlog processor that masks PII from all event_dict values.

    This processor runs *before* serialisation so that PII is removed
    from both stdout and any downstream log shipper.

    Contract:
        - Never raises; on error wraps the offending value in
          ``[MASKING_ERROR]: <original>`` and continues.
        - Deterministic: same input → same output.
        - Handles nested dicts, lists, bytes, None, and scalar types.
    """
    masked: dict[str, Any] = {}
    for key, value in event_dict.items():
        try:
            masked[key] = _mask_value(key, value)
        except Exception as exc:  # pragma: no cover — defensive guard
            _masking_error_logger.warning(
                "PII masking failed for field %r: %s", key, exc
            )
            masked[key] = f"[MASKING_ERROR]: {value!r}"
    return masked


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def configure_logging(log_level: str = "INFO", app_env: str = "production") -> None:
    """Configure structlog and stdlib logging for ForgeGuard.

    Must be called **once** at application startup, before the first log
    statement.  Subsequent calls reconfigure logging in-place (safe for
    testing but unusual in production).

    Args:
        log_level: Python log level string (DEBUG, INFO, WARNING, …).
        app_env:   Deployment environment; "development" → ConsoleRenderer,
                   anything else → JSONRenderer.
    """
    level = getattr(logging, log_level.upper(), logging.INFO)
    is_dev = app_env == "development"

    # ---- structlog shared processors (used by both structlog and stdlib) --
    shared_processors: list[Any] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        pii_masking_processor,
    ]

    # ---- Final renderer depends on environment ----------------------------
    final_renderer: Any = (
        structlog.dev.ConsoleRenderer(colors=sys.stderr.isatty())
        if is_dev
        else structlog.processors.JSONRenderer()
    )

    # ---- Configure structlog ----------------------------------------------
    structlog.configure(
        processors=[
            *shared_processors,
            final_renderer,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(file=sys.stdout),
        cache_logger_on_first_use=True,
    )

    # ---- Bridge stdlib logging through structlog -------------------------
    # This ensures uvicorn, sqlalchemy, alembic, etc. also go through the
    # PII masking pipeline.
    formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=shared_processors,
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            structlog.processors.JSONRenderer()
            if not is_dev
            else structlog.dev.ConsoleRenderer(colors=sys.stderr.isatty()),
        ],
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.handlers = [handler]
    root_logger.setLevel(level)

    # Silence noisy uvicorn access logs in production (structlog replaces them).
    if not is_dev:
        logging.getLogger("uvicorn.access").propagate = False
