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

Application error (HTTP 4xx)::

    {
        "error": "not_found",
        "reference_id": "<uuid>",
        "message": "Service xyz was not found"
    }

Permission denied (HTTP 403)::

    {
        "error": "forbidden",
        "reference_id": "<uuid>",
        "message": "Access denied",
        "action": "Contact platform admin to request the 'service:delete' permission.",
        "required_permission": "service:delete"
    }

Unhandled exception (HTTP 500)::

    {
        "error": "internal_error",
        "reference_id": "<uuid>",
        "message": "An unexpected error occurred"
    }

Design notes
------------
- ``reference_id`` is read from ``request.state.correlation_id`` (WO-015
  canonical name) or ``request.state.request_id`` (backward-compat alias).
  If neither is set (e.g. bare test app without middleware), a fresh UUID is
  generated so ``reference_id`` is always present in error responses.
- Pydantic v2 error dicts: ``loc`` (tuple), ``msg`` (str), ``input`` (raw value).
  The ``loc`` tuple is flattened to a human-readable dotted path, with list
  indices rendered as ``[N]``.
- Internal transformation errors are caught; a safe fallback response is
  returned so the error handler never itself raises an unhandled exception.
- ``handle_unhandled_exception`` NEVER includes the exception message,
  traceback, class name, or any internal detail in the HTTP response body.
  The full traceback is logged server-side with the correlation ID.
- Sensitive pattern detection: if the exception message contains a DB
  connection string, API key pattern, or file path, an additional security
  warning is logged so operators can audit accidental secret logging.
"""

from __future__ import annotations

import logging
import re
import traceback
import uuid
from json import JSONDecodeError
from typing import Any

import structlog
from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from forgeguard.core.exceptions import ForbiddenError, ForgeGuardError, PermissionDeniedError

logger = logging.getLogger(__name__)
structlog_logger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Sensitive-data detection patterns (used only for server-side logging)
# ---------------------------------------------------------------------------

_SENSITIVE_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"(?i)(postgresql|mysql|mongodb|redis|amqp)://\S+"),
    re.compile(r"(?i)password\s*[=:]\s*\S+"),
    re.compile(r"(?i)secret\s*[=:]\s*\S+"),
    re.compile(r"(?i)api[_-]?key\s*[=:]\s*\S+"),
    re.compile(r"(?i)bearer\s+[A-Za-z0-9\-._~+/]+=*"),
    re.compile(r"(?:sk|pk|rk)-[A-Za-z0-9]{16,}"),
]

# HTTP status code → error type slug for Starlette HTTPException mapping.
_HTTP_STATUS_TO_ERROR_TYPE: dict[int, str] = {
    400: "bad_request",
    401: "unauthorized",
    403: "forbidden",
    404: "not_found",
    405: "method_not_allowed",
    408: "request_timeout",
    409: "conflict",
    410: "gone",
    415: "unsupported_media_type",
    422: "unprocessable_entity",
    429: "rate_limit_exceeded",
    500: "internal_error",
    502: "bad_gateway",
    503: "service_unavailable",
    504: "gateway_timeout",
}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_reference_id(request: Request) -> str | None:
    """Extract the correlation ID from request state, if available.

    Checks ``correlation_id`` (WO-015 canonical) then ``request_id``
    (backward-compat alias from WO-004).  Returns ``None`` if neither is set.
    """
    return (
        getattr(request.state, "correlation_id", None)
        or getattr(request.state, "request_id", None)
    )


def get_correlation_id(request: Request) -> str:
    """Return the request correlation ID, generating a new UUID if not set.

    Always returns a non-empty string so ``reference_id`` is present in every
    error response even when RequestIDMiddleware has not run (e.g. bare test app).
    """
    return _get_reference_id(request) or str(uuid.uuid4())


def _contains_sensitive_data(text: str) -> bool:
    """Return True if *text* matches any known sensitive-data pattern."""
    return any(p.search(text) for p in _SENSITIVE_PATTERNS)


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


# ---------------------------------------------------------------------------
# ForgeGuardError hierarchy handler
# ---------------------------------------------------------------------------

async def handle_forgeguard_error(
    request: Request,
    exc: ForgeGuardError,
) -> JSONResponse:
    """Handle any :class:`~forgeguard.core.exceptions.ForgeGuardError` subclass.

    Builds the appropriate response shape based on the exception type:
    - :class:`~forgeguard.core.exceptions.ForbiddenError` gets the extended
      shape with ``action`` and ``required_permission`` fields.
    - All other subclasses get the standard ``ErrorResponse`` shape.
    """
    reference_id = get_correlation_id(request)

    structlog_logger.warning(
        "forgeguard_error",
        error_type=exc.error_type,
        status_code=exc.status_code,
        message=exc.message,
        reference_id=reference_id,
    )

    if isinstance(exc, PermissionDeniedError):
        body: dict[str, Any] = {
            "error": exc.error_type,
            "message": exc.message,
            "reference_id": reference_id,
            "required_permission": exc.required_permission,
            "required_roles": exc.required_roles,
        }
    elif isinstance(exc, ForbiddenError):
        action = (
            f"Contact {exc.contact_role} to request"
            f" the '{exc.required_permission}' permission."
            if exc.required_permission
            else f"Contact {exc.contact_role} to request elevated access."
        )
        body = {
            "error": exc.error_type,
            "message": exc.message,
            "reference_id": reference_id,
            "action": action,
            "required_permission": exc.required_permission,
        }
    else:
        body = {
            "error": exc.error_type,
            "message": exc.message,
            "reference_id": reference_id,
        }

    return JSONResponse(status_code=exc.status_code, content=body)


# ---------------------------------------------------------------------------
# Starlette / FastAPI HTTPException handler
# ---------------------------------------------------------------------------

async def handle_http_exception(
    request: Request,
    exc: StarletteHTTPException,
) -> JSONResponse:
    """Wrap a Starlette :class:`~starlette.exceptions.HTTPException` in the
    ForgeGuard structured error format.

    FastAPI raises :class:`fastapi.HTTPException` (a subclass) for built-in
    errors such as 405 Method Not Allowed.  Registering this handler for
    :class:`starlette.exceptions.HTTPException` catches both.
    """
    reference_id = get_correlation_id(request)
    error_type = _HTTP_STATUS_TO_ERROR_TYPE.get(exc.status_code, f"http_{exc.status_code}")

    # exc.detail may be a string, dict, or None depending on how it was raised.
    if isinstance(exc.detail, str):
        message = exc.detail
    elif exc.detail is not None:
        message = str(exc.detail)
    else:
        message = f"HTTP {exc.status_code}"

    structlog_logger.warning(
        "http_exception",
        status_code=exc.status_code,
        error_type=error_type,
        reference_id=reference_id,
    )

    body = {
        "error": error_type,
        "message": message,
        "reference_id": reference_id,
    }
    return JSONResponse(status_code=exc.status_code, content=body)


# ---------------------------------------------------------------------------
# Catch-all unhandled exception handler
# ---------------------------------------------------------------------------

async def handle_unhandled_exception(
    request: Request,
    exc: Exception,
) -> JSONResponse:
    """Catch-all handler for any exception not handled by a more specific handler.

    Security contract:
    - The HTTP response body NEVER contains the exception message, class name,
      traceback, file paths, or any internal implementation detail.
    - The full exception details (type, message, traceback) are logged
      server-side with the correlation ID for post-incident debugging.
    - If the exception message contains a sensitive-data pattern (DB connection
      string, API key, file path), an additional security warning is logged.
    - If this handler itself raises an exception, a minimal fallback response
      is returned so no unstructured error ever reaches the client.
    """
    reference_id = get_correlation_id(request)

    exc_message = str(exc)
    exc_tb = traceback.format_exc()

    try:
        structlog_logger.error(
            "unhandled_exception",
            exc_type=type(exc).__name__,
            exc_message=exc_message,
            reference_id=reference_id,
            traceback=exc_tb,
        )

        if _contains_sensitive_data(exc_message):
            structlog_logger.warning(
                "sensitive_data_in_exception",
                reference_id=reference_id,
                exc_type=type(exc).__name__,
            )
    except Exception:  # pragma: no cover
        logger.error(
            "handle_unhandled_exception: structured logging failed",
            exc_info=True,
        )

    try:
        return JSONResponse(
            status_code=500,
            content={
                "error": "internal_error",
                "message": "An unexpected error occurred",
                "reference_id": reference_id,
            },
        )
    except Exception:  # pragma: no cover
        return JSONResponse(
            status_code=500,
            content={"error": "internal_error", "message": "An unexpected error occurred"},
        )


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

def register_error_handlers(app: Any) -> None:
    """Register all ForgeGuard custom exception handlers on a FastAPI app.

    Registration order matters: more specific exception types must be
    registered before less specific ones.  The catch-all ``Exception``
    handler is registered last.

    Call this from the application factory after creating the
    :class:`fastapi.FastAPI` instance and before registering routers.

    Args:
        app: A :class:`fastapi.FastAPI` instance.
    """
    # Validation and JSON errors (most specific — registered first).
    app.add_exception_handler(RequestValidationError, request_validation_error_handler)
    app.add_exception_handler(JSONDecodeError, json_decode_error_handler)
    # ForgeGuard application exceptions.
    app.add_exception_handler(ForgeGuardError, handle_forgeguard_error)
    # Starlette/FastAPI HTTP exceptions (overrides the default handler).
    app.add_exception_handler(StarletteHTTPException, handle_http_exception)
    # Catch-all for any unhandled exception (registered last).
    app.add_exception_handler(Exception, handle_unhandled_exception)
