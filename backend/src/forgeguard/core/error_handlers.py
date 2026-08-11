"""Custom exception handlers that transform FastAPI/Pydantic errors into
the ForgeGuard structured error contract.

Error response shapes
---------------------
Validation error (HTTP 422)::

    {
        "error": "validation_error",
        "reference_id": "<uuid>",
        "message": "Request validation failed",
        "details": [
            {"field": "commit_sha", "message": "...", "received": "abc"},
            ...
        ]
    }

Malformed JSON body (HTTP 400)::

    {
        "error": "invalid_json",
        "reference_id": "<uuid>",
        "message": "Request body contains invalid JSON"
    }

Design notes
------------
- ``reference_id`` is read from ``request.state.request_id`` set by
  :class:`~forgeguard.middleware.request_id.RequestIDMiddleware`.  If the
  middleware has not run (e.g. bare test app), the field is omitted gracefully.
- Pydantic v2 error dicts: ``loc`` (tuple), ``msg`` (str), ``input`` (raw value).
  The ``loc`` tuple is flattened to a human-readable dotted path, with list
  indices rendered as ``[N]``.
- Internal transformation errors are caught; a safe fallback 422 response is
  returned so the error handler never itself raises an unhandled exception.
"""

from __future__ import annotations

import logging
from json import JSONDecodeError
from typing import Any

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_reference_id(request: Request) -> str | None:
    """Extract the server-assigned request ID from request state, if available."""
    return getattr(request.state, "request_id", None)


def _flatten_loc(loc: tuple[str | int, ...]) -> str:
    """Convert a Pydantic v2 ``loc`` tuple to a dot-notation field path.

    Examples::

        ('body', 'commit_sha')      → 'commit_sha'
        ('body', 'items', 0, 'name') → 'items[0].name'
        ('query', 'page')           → 'page'
        ('path', 'repo_id')         → 'repo_id'
    """
    if not loc:
        return "(root)"

    parts: list[str] = []
    # Skip the leading source hint ('body', 'query', 'path', 'header').
    items = loc[1:] if loc and loc[0] in ("body", "query", "path", "header", "cookie") else loc

    for segment in items:
        if isinstance(segment, int):
            # List index — append as [N] to the previous part.
            if parts:
                parts[-1] = f"{parts[-1]}[{segment}]"
            else:
                parts.append(f"[{segment}]")
        else:
            parts.append(str(segment))

    return ".".join(parts) if parts else str(loc[0])


def _sanitize_received(value: Any) -> Any:
    """Return a safe representation of the received value for error responses.

    Avoids leaking large payloads; truncates strings longer than 200 chars.
    """
    if isinstance(value, str) and len(value) > 200:
        return value[:200] + "…"
    return value


def format_validation_errors(
    errors: list[dict[str, Any]],
    reference_id: str | None,
) -> dict[str, Any]:
    """Convert a Pydantic v2 error list into the ForgeGuard structured format.

    Args:
        errors: The list returned by ``ValidationError.errors()``.
        reference_id: Correlation ID from the request state.

    Returns:
        A dict matching the validation_error response schema.
    """
    details: list[dict[str, Any]] = []
    for err in errors:
        loc: tuple[str | int, ...] = err.get("loc", ())
        field = _flatten_loc(loc)
        details.append(
            {
                "field": field,
                "message": err.get("msg", "Invalid value"),
                "received": _sanitize_received(err.get("input")),
            }
        )

    body: dict[str, Any] = {
        "error": "validation_error",
        "message": "Request validation failed",
        "details": details,
    }
    if reference_id is not None:
        body["reference_id"] = reference_id
    return body


# ---------------------------------------------------------------------------
# Exception handlers
# ---------------------------------------------------------------------------

async def request_validation_error_handler(
    request: Request,
    exc: RequestValidationError,
) -> JSONResponse:
    """Handle Pydantic RequestValidationError — body, query, and path params."""
    reference_id = _get_reference_id(request)
    try:
        body = format_validation_errors(exc.errors(), reference_id)
    except Exception as inner:
        logger.warning(
            "error_handler_transform_failed: %s", inner, exc_info=True
        )
        fallback: dict[str, Any] = {
            "error": "validation_error",
            "message": "Request validation failed",
            "details": [],
        }
        if reference_id is not None:
            fallback["reference_id"] = reference_id
        return JSONResponse(status_code=422, content=fallback)

    return JSONResponse(status_code=422, content=body)


async def json_decode_error_handler(
    request: Request,
    exc: Exception,
) -> JSONResponse:
    """Handle malformed JSON request bodies — returns HTTP 400."""
    reference_id = _get_reference_id(request)
    body: dict[str, Any] = {
        "error": "invalid_json",
        "message": "Request body contains invalid JSON",
    }
    if reference_id is not None:
        body["reference_id"] = reference_id
    return JSONResponse(status_code=400, content=body)


def register_error_handlers(app: Any) -> None:
    """Register all ForgeGuard custom exception handlers on a FastAPI app.

    Call this from the application factory after creating the
    :class:`fastapi.FastAPI` instance and before registering routers.

    Args:
        app: A :class:`fastapi.FastAPI` instance.
    """
    app.add_exception_handler(RequestValidationError, request_validation_error_handler)
    app.add_exception_handler(JSONDecodeError, json_decode_error_handler)
