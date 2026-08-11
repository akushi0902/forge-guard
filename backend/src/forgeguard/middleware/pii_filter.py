"""PII filter — structlog processor at middleware pipeline position 8.

This module exposes :func:`pii_filter_processor`, a structlog processor that
scans every log event_dict for known PII field names and applies the
appropriate masking function from :mod:`forgeguard.utils.pii_masking`.

The processor is designed to be inserted into the structlog processor chain
**before** the final renderer so that PII is masked in both JSON (production)
and console (development) log output.

Pipeline position:
  The architecture spec places PII filtering at position 8 (before the audit
  pre-hook at position 9).  In the structlog processor chain this corresponds
  to the last step before serialisation.

Integration:
  Add :func:`pii_filter_processor` to the ``processors`` list passed to
  :func:`structlog.configure` in :mod:`forgeguard.core.logging`.  The
  existing :func:`~forgeguard.core.logging.pii_masking_processor` in
  ``core.logging`` provides the same behaviour for the core pipeline; this
  module provides a standalone import for other consumers (e.g. audit hooks)
  that want the same contract backed by the public :mod:`utils.pii_masking`
  API.

Usage::

    import structlog
    from forgeguard.middleware.pii_filter import pii_filter_processor

    structlog.configure(processors=[..., pii_filter_processor, renderer])
"""

from __future__ import annotations

import logging
from typing import Any

from forgeguard.utils.pii_masking import PII_FIELD_NAMES, mask_field

_error_logger = logging.getLogger("forgeguard.pii_filter")


def pii_filter_processor(
    _logger: Any,
    _method_name: str,
    event_dict: dict[str, Any],
) -> dict[str, Any]:
    """Structlog processor that masks PII fields in every log event.

    Iterates over all keys in *event_dict*.  Keys whose lowercased name
    appears in :data:`~forgeguard.utils.pii_masking.PII_FIELD_NAMES` have
    their values replaced by the masked equivalent.  All other keys are
    passed through unchanged.

    One level of nested dicts is also inspected: if a value is a ``dict``,
    any of its keys that are PII field names are masked.

    Contract:
      - Never raises — any masking error wraps the value in
        ``[PII_MASK_ERROR]`` and continues.
      - Deterministic: same event_dict → same masked output.

    Args:
        _logger:      The bound structlog logger (unused).
        _method_name: The log method name (``"info"``, ``"error"``, …).
        event_dict:   The mutable log event dictionary.

    Returns:
        The same ``event_dict`` with PII field values replaced.
    """
    masked: dict[str, Any] = {}
    for key, value in event_dict.items():
        try:
            masked[key] = _mask_event_value(key, value)
        except Exception as exc:  # pragma: no cover — defensive guard
            _error_logger.warning(
                "pii_filter: masking failed for field %r: %s", key, exc
            )
            masked[key] = "[PII_MASK_ERROR]"
    return masked


def _mask_event_value(field_name: str, value: Any) -> Any:
    """Mask a single event_dict value.

    Handles strings (PII field dispatch or pass-through), dicts (one level
    of nesting), lists/tuples (element-wise), and scalar types (pass-through).
    """
    if value is None or isinstance(value, bool | int | float):
        return value

    if isinstance(value, bytes):
        try:
            value = value.decode("utf-8", errors="replace")
        except Exception:
            return value

    if isinstance(value, str):
        lower_key = field_name.lower()
        if lower_key in PII_FIELD_NAMES:
            result = mask_field(lower_key, value)
            return result if result is not None else value
        return value

    if isinstance(value, dict):
        return {k: _mask_event_value(k, v) for k, v in value.items()}

    if isinstance(value, list | tuple):
        masked = [_mask_event_value(field_name, item) for item in value]
        return type(value)(masked)

    try:
        return str(value)
    except Exception:
        return value
