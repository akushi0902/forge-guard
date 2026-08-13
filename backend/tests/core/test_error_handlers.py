"""Tests for ForgeGuard custom exception handlers.

Covers:
    1. Single field validation error returns structured format with field, message, received.
    2. Multiple field errors return all errors in the details array.
    3. Path parameter validation error returns structured format.
    4. Query parameter validation error returns structured format.
    5. Malformed JSON body returns HTTP 400 with error='invalid_json'.
    6. reference_id is present in all error responses.
    7. Integration: Request ID middleware + validation handler — reference_id
       matches X-Request-ID response header.
    8. Unknown extra fields return validation_error (extra='forbid').
    9. Handler never exposes stack traces or Python class names.

WO-020 additions:
    10. ForgeGuardError subclasses return correct status code and error_type.
    11. ForbiddenError response includes action and required_permission fields.
    12. Starlette HTTPException is wrapped in structured format.
    13. Unhandled RuntimeError returns HTTP 500 with generic message and reference_id.
    14. HTTP 500 body never contains traceback, class names, or exception message.
    15. Exception with sensitive data (DB URL) does not leak to response body.
    16. Integration: full middleware chain — error responses include X-Request-ID,
        security headers, and structured body.
"""

from __future__ import annotations

from typing import AsyncGenerator

import pytest
import pytest_asyncio
from fastapi import FastAPI, Path, Query
from fastapi.exceptions import HTTPException as FastAPIHTTPException
from httpx import ASGITransport, AsyncClient
from starlette.exceptions import HTTPException as StarletteHTTPException

from forgeguard.core.error_handlers import (
    format_validation_errors,
    register_error_handlers,
)
from forgeguard.core.exceptions import (
    BadRequestError,
    ConflictError,
    ForbiddenError,
    NotFoundError,
    RateLimitError,
    UnauthorizedError,
)
from forgeguard.core.validation import CommitSHAField, ForgeGuardBaseModel, ScoreField, UUIDField
from forgeguard.middleware.request_id import RequestIDMiddleware
from forgeguard.middleware.security_headers import SecurityHeadersMiddleware


# ---------------------------------------------------------------------------
# Sample request models
# ---------------------------------------------------------------------------

class _CommitRequest(ForgeGuardBaseModel):
    commit_sha: CommitSHAField  # type: ignore[valid-type]
    score: ScoreField  # type: ignore[valid-type]


class _ServiceRequest(ForgeGuardBaseModel):
    service_id: UUIDField  # type: ignore[valid-type]
    name: str


# ---------------------------------------------------------------------------
# Test app factory
# ---------------------------------------------------------------------------

def _make_validation_app(with_request_id: bool = False) -> FastAPI:
    app = FastAPI()
    register_error_handlers(app)

    if with_request_id:
        app.add_middleware(RequestIDMiddleware)

    @app.post("/commits")
    async def create_commit(body: _CommitRequest):
        return {"ok": True}

    @app.post("/services")
    async def create_service(body: _ServiceRequest):
        return {"ok": True}

    @app.get("/repos/{repo_id}")
    async def get_repo(repo_id: UUIDField):  # type: ignore[valid-type]
        return {"repo_id": repo_id}

    @app.get("/items")
    async def list_items(
        page: int = Query(..., ge=1, description="Page number, must be >= 1")
    ):
        return {"page": page}

    return app


@pytest_asyncio.fixture()
async def val_client() -> AsyncGenerator[AsyncClient, None]:
    app = _make_validation_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


@pytest_asyncio.fixture()
async def val_client_with_rid() -> AsyncGenerator[AsyncClient, None]:
    app = _make_validation_app(with_request_id=True)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


# ---------------------------------------------------------------------------
# format_validation_errors unit tests
# ---------------------------------------------------------------------------

class TestFormatValidationErrors:
    def test_single_error_structure(self) -> None:
        errors = [{"loc": ("body", "commit_sha"), "msg": "String should match pattern", "input": "abc"}]
        result = format_validation_errors(errors, reference_id="test-ref-123")
        assert result["error"] == "validation_error"
        assert result["message"] == "Request validation failed"
        assert result["reference_id"] == "test-ref-123"
        assert len(result["details"]) == 1
        d = result["details"][0]
        assert d["field"] == "commit_sha"
        assert "abc" in str(d["received"])

    def test_multiple_errors_all_included(self) -> None:
        errors = [
            {"loc": ("body", "commit_sha"), "msg": "msg1", "input": "x"},
            {"loc": ("body", "score"), "msg": "msg2", "input": 999},
        ]
        result = format_validation_errors(errors, reference_id=None)
        assert len(result["details"]) == 2
        fields = [d["field"] for d in result["details"]]
        assert "commit_sha" in fields
        assert "score" in fields

    def test_no_reference_id_omitted(self) -> None:
        errors = [{"loc": ("body", "name"), "msg": "required", "input": None}]
        result = format_validation_errors(errors, reference_id=None)
        assert "reference_id" not in result

    def test_nested_loc_flattened_to_dotted_path(self) -> None:
        errors = [{"loc": ("body", "items", 0, "name"), "msg": "required", "input": None}]
        result = format_validation_errors(errors, reference_id=None)
        assert result["details"][0]["field"] == "items[0].name"

    def test_query_param_loc_flattened(self) -> None:
        errors = [{"loc": ("query", "page"), "msg": "invalid", "input": "abc"}]
        result = format_validation_errors(errors, reference_id=None)
        assert result["details"][0]["field"] == "page"

    def test_path_param_loc_flattened(self) -> None:
        errors = [{"loc": ("path", "repo_id"), "msg": "invalid", "input": "bad"}]
        result = format_validation_errors(errors, reference_id=None)
        assert result["details"][0]["field"] == "repo_id"

    def test_long_string_truncated_in_received(self) -> None:
        errors = [{"loc": ("body", "field"), "msg": "too long", "input": "x" * 500}]
        result = format_validation_errors(errors, reference_id=None)
        received = result["details"][0]["received"]
        assert len(received) <= 210  # 200 chars + ellipsis


# ---------------------------------------------------------------------------
# HTTP-level validation error tests
# ---------------------------------------------------------------------------

class TestSingleFieldError:
    async def test_missing_required_field_returns_422(
        self, val_client: AsyncClient
    ) -> None:
        r = await val_client.post(
            "/commits",
            json={"commit_sha": "a" * 40},  # missing score
        )
        assert r.status_code == 422
        body = r.json()
        assert body["error"] == "validation_error"
        assert body["message"] == "Request validation failed"
        fields = [d["field"] for d in body["details"]]
        assert "score" in fields

    async def test_wrong_type_returns_422(self, val_client: AsyncClient) -> None:
        r = await val_client.post(
            "/commits",
            json={"commit_sha": "not-a-sha", "score": 50.0},
        )
        assert r.status_code == 422
        body = r.json()
        assert body["error"] == "validation_error"
        # The received value should appear in details
        assert any("commit_sha" in d["field"] for d in body["details"])


class TestMultipleFieldErrors:
    async def test_all_errors_returned_together(
        self, val_client: AsyncClient
    ) -> None:
        r = await val_client.post(
            "/commits",
            json={},  # both commit_sha and score missing
        )
        assert r.status_code == 422
        body = r.json()
        assert len(body["details"]) >= 2


class TestPathParamError:
    async def test_invalid_uuid_path_param_returns_422(
        self, val_client: AsyncClient
    ) -> None:
        r = await val_client.get("/repos/not-a-valid-uuid")
        assert r.status_code == 422
        body = r.json()
        assert body["error"] == "validation_error"
        assert any("repo_id" in d["field"] for d in body["details"])


class TestQueryParamError:
    async def test_invalid_query_param_returns_422(
        self, val_client: AsyncClient
    ) -> None:
        r = await val_client.get("/items?page=0")  # page must be >= 1
        assert r.status_code == 422
        body = r.json()
        assert body["error"] == "validation_error"
        assert any("page" in d["field"] for d in body["details"])

    async def test_missing_required_query_param(
        self, val_client: AsyncClient
    ) -> None:
        r = await val_client.get("/items")  # page is required
        assert r.status_code == 422
        body = r.json()
        assert body["error"] == "validation_error"


class TestMalformedJSON:
    async def test_malformed_json_returns_400(
        self, val_client: AsyncClient
    ) -> None:
        r = await val_client.post(
            "/commits",
            content=b"{invalid json!!!",
            headers={"Content-Type": "application/json"},
        )
        assert r.status_code == 400
        body = r.json()
        assert body["error"] == "invalid_json"
        assert "json" in body["message"].lower()

    async def test_malformed_json_no_stack_trace(
        self, val_client: AsyncClient
    ) -> None:
        r = await val_client.post(
            "/commits",
            content=b"<xml>not json</xml>",
            headers={"Content-Type": "application/json"},
        )
        body_text = r.text
        assert "Traceback" not in body_text
        assert "JSONDecodeError" not in body_text
        assert "File " not in body_text


class TestExtraFieldsRejected:
    async def test_extra_fields_return_validation_error(
        self, val_client: AsyncClient
    ) -> None:
        r = await val_client.post(
            "/commits",
            json={
                "commit_sha": "a" * 40,
                "score": 90.0,
                "injected_field": "malicious",
            },
        )
        assert r.status_code == 422
        body = r.json()
        assert body["error"] == "validation_error"


class TestNoInternalDetails:
    async def test_error_response_has_no_python_traceback(
        self, val_client: AsyncClient
    ) -> None:
        r = await val_client.post("/commits", json={"commit_sha": "bad", "score": -1})
        body_text = r.text
        assert "Traceback" not in body_text
        assert "File " not in body_text

    async def test_error_response_has_no_class_names(
        self, val_client: AsyncClient
    ) -> None:
        r = await val_client.post("/commits", json={})
        body_text = r.text
        assert "ValidationError" not in body_text
        assert "forgeguard." not in body_text


# ---------------------------------------------------------------------------
# Integration: Request ID middleware + error handler
# ---------------------------------------------------------------------------

class TestIntegrationWithRequestID:
    async def test_reference_id_matches_x_request_id_header(
        self, val_client_with_rid: AsyncClient
    ) -> None:
        r = await val_client_with_rid.post(
            "/commits",
            json={"commit_sha": "too-short", "score": 50.0},
        )
        assert r.status_code == 422

        x_request_id = r.headers.get("x-request-id")
        assert x_request_id, "X-Request-ID header must be set by RequestIDMiddleware"

        body = r.json()
        assert body.get("reference_id") == x_request_id

    async def test_malformed_json_reference_id_matches_header(
        self, val_client_with_rid: AsyncClient
    ) -> None:
        r = await val_client_with_rid.post(
            "/commits",
            content=b"{bad json",
            headers={"Content-Type": "application/json"},
        )
        assert r.status_code == 400

        x_request_id = r.headers.get("x-request-id")
        assert x_request_id

        body = r.json()
        assert body.get("reference_id") == x_request_id

    async def test_multiple_errors_all_have_same_reference_id(
        self, val_client_with_rid: AsyncClient
    ) -> None:
        r = await val_client_with_rid.post("/commits", json={})
        assert r.status_code == 422

        x_request_id = r.headers.get("x-request-id")
        body = r.json()
        assert body.get("reference_id") == x_request_id
        assert len(body["details"]) >= 2


# ===========================================================================
# WO-020: Global Error Handler with ForgeGuardError + HTTPException + catch-all
# ===========================================================================

def _make_exception_app(
    with_request_id: bool = False,
    with_security_headers: bool = False,
) -> FastAPI:
    """Minimal app with routes that raise each exception type."""
    app = FastAPI()
    register_error_handlers(app)

    if with_security_headers:
        app.add_middleware(SecurityHeadersMiddleware)
    if with_request_id:
        app.add_middleware(RequestIDMiddleware)

    @app.get("/not-found")
    async def raise_not_found():
        raise NotFoundError("The requested service was not found")

    @app.get("/forbidden")
    async def raise_forbidden():
        raise ForbiddenError(
            "Access denied",
            required_permission="service:delete",
            contact_role="platform admin",
        )

    @app.get("/forbidden-no-perm")
    async def raise_forbidden_no_perm():
        raise ForbiddenError("Access denied")

    @app.get("/conflict")
    async def raise_conflict():
        raise ConflictError("Service name already exists")

    @app.get("/unauthorized")
    async def raise_unauthorized():
        raise UnauthorizedError("Token is expired")

    @app.get("/bad-request")
    async def raise_bad_request():
        raise BadRequestError("Invalid commit reference")

    @app.get("/rate-limit")
    async def raise_rate_limit():
        raise RateLimitError("Too many requests")

    @app.get("/http-exception")
    async def raise_http_exc():
        raise StarletteHTTPException(status_code=405, detail="Method not allowed")

    @app.get("/fastapi-http-exception")
    async def raise_fastapi_exc():
        raise FastAPIHTTPException(status_code=410, detail="Resource gone")

    @app.get("/unhandled")
    async def raise_unhandled():
        raise RuntimeError("Internal engine failure")

    @app.get("/sensitive-error")
    async def raise_sensitive():
        raise RuntimeError(
            "DB error: postgresql://forgeguard_app:s3cr3t@db.internal:5432/forgeguard"
        )

    return app


@pytest_asyncio.fixture()
async def exc_client() -> AsyncGenerator[AsyncClient, None]:
    app = _make_exception_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


@pytest_asyncio.fixture()
async def exc_client_full() -> AsyncGenerator[AsyncClient, None]:
    """App with full middleware: RequestID + SecurityHeaders + error handlers."""
    app = _make_exception_app(with_request_id=True, with_security_headers=True)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


# ---------------------------------------------------------------------------
# ForgeGuardError subclasses → correct status + body
# ---------------------------------------------------------------------------

class TestForgeGuardErrorHandler:
    async def test_not_found_returns_404(self, exc_client: AsyncClient) -> None:
        r = await exc_client.get("/not-found")
        assert r.status_code == 404
        body = r.json()
        assert body["error"] == "not_found"
        assert "reference_id" in body

    async def test_not_found_message_in_body(self, exc_client: AsyncClient) -> None:
        r = await exc_client.get("/not-found")
        body = r.json()
        assert "service" in body["message"].lower()

    async def test_unauthorized_returns_401(self, exc_client: AsyncClient) -> None:
        r = await exc_client.get("/unauthorized")
        assert r.status_code == 401
        assert r.json()["error"] == "unauthorized"

    async def test_conflict_returns_409(self, exc_client: AsyncClient) -> None:
        r = await exc_client.get("/conflict")
        assert r.status_code == 409
        assert r.json()["error"] == "conflict"

    async def test_bad_request_returns_400(self, exc_client: AsyncClient) -> None:
        r = await exc_client.get("/bad-request")
        assert r.status_code == 400
        assert r.json()["error"] == "bad_request"

    async def test_rate_limit_returns_429(self, exc_client: AsyncClient) -> None:
        r = await exc_client.get("/rate-limit")
        assert r.status_code == 429
        assert r.json()["error"] == "rate_limit_exceeded"

    async def test_reference_id_always_present(self, exc_client: AsyncClient) -> None:
        for path in ["/not-found", "/unauthorized", "/conflict", "/bad-request"]:
            r = await exc_client.get(path)
            assert "reference_id" in r.json(), f"reference_id missing for {path}"


# ---------------------------------------------------------------------------
# ForbiddenError → action + required_permission
# ---------------------------------------------------------------------------

class TestForbiddenErrorHandler:
    async def test_forbidden_returns_403(self, exc_client: AsyncClient) -> None:
        r = await exc_client.get("/forbidden")
        assert r.status_code == 403

    async def test_forbidden_error_type(self, exc_client: AsyncClient) -> None:
        r = await exc_client.get("/forbidden")
        assert r.json()["error"] == "forbidden"

    async def test_forbidden_has_action_field(self, exc_client: AsyncClient) -> None:
        r = await exc_client.get("/forbidden")
        body = r.json()
        assert "action" in body, "403 response must include 'action' field"
        assert body["action"] != ""

    async def test_forbidden_has_required_permission(self, exc_client: AsyncClient) -> None:
        r = await exc_client.get("/forbidden")
        body = r.json()
        assert "required_permission" in body
        assert body["required_permission"] == "service:delete"

    async def test_action_references_contact_role(self, exc_client: AsyncClient) -> None:
        r = await exc_client.get("/forbidden")
        body = r.json()
        assert "platform admin" in body["action"]

    async def test_action_references_permission(self, exc_client: AsyncClient) -> None:
        r = await exc_client.get("/forbidden")
        body = r.json()
        assert "service:delete" in body["action"]

    async def test_forbidden_no_perm_still_has_action(
        self, exc_client: AsyncClient
    ) -> None:
        r = await exc_client.get("/forbidden-no-perm")
        assert r.status_code == 403
        assert "action" in r.json()


# ---------------------------------------------------------------------------
# Starlette / FastAPI HTTPException → structured format
# ---------------------------------------------------------------------------

class TestHTTPExceptionHandler:
    async def test_starlette_405_wrapped(self, exc_client: AsyncClient) -> None:
        r = await exc_client.get("/http-exception")
        assert r.status_code == 405
        body = r.json()
        assert body["error"] == "method_not_allowed"
        assert "reference_id" in body

    async def test_fastapi_410_wrapped(self, exc_client: AsyncClient) -> None:
        r = await exc_client.get("/fastapi-http-exception")
        assert r.status_code == 410
        body = r.json()
        assert body["error"] == "gone"
        assert "reference_id" in body

    async def test_http_exception_has_message(self, exc_client: AsyncClient) -> None:
        r = await exc_client.get("/http-exception")
        body = r.json()
        assert body.get("message") != ""

    async def test_unknown_route_404_wrapped(self, exc_client: AsyncClient) -> None:
        r = await exc_client.get("/this-route-does-not-exist")
        assert r.status_code == 404
        body = r.json()
        assert "error" in body
        assert "reference_id" in body


# ---------------------------------------------------------------------------
# Unhandled exception → HTTP 500 with generic message
# ---------------------------------------------------------------------------

class TestUnhandledExceptionHandler:
    async def test_unhandled_returns_500(self, exc_client: AsyncClient) -> None:
        r = await exc_client.get("/unhandled")
        assert r.status_code == 500

    async def test_500_error_type(self, exc_client: AsyncClient) -> None:
        r = await exc_client.get("/unhandled")
        assert r.json()["error"] == "internal_error"

    async def test_500_has_generic_message(self, exc_client: AsyncClient) -> None:
        r = await exc_client.get("/unhandled")
        body = r.json()
        assert body["message"] == "An unexpected error occurred"

    async def test_500_has_reference_id(self, exc_client: AsyncClient) -> None:
        r = await exc_client.get("/unhandled")
        assert "reference_id" in r.json()

    async def test_500_no_traceback_in_body(self, exc_client: AsyncClient) -> None:
        r = await exc_client.get("/unhandled")
        text = r.text
        assert "Traceback" not in text
        assert "File " not in text
        assert "raise RuntimeError" not in text

    async def test_500_no_exception_class_in_body(
        self, exc_client: AsyncClient
    ) -> None:
        r = await exc_client.get("/unhandled")
        text = r.text
        assert "RuntimeError" not in text
        assert "forgeguard." not in text

    async def test_500_no_exception_message_in_body(
        self, exc_client: AsyncClient
    ) -> None:
        """The exception's own message must NOT appear in the HTTP response."""
        r = await exc_client.get("/unhandled")
        assert "Internal engine failure" not in r.text


# ---------------------------------------------------------------------------
# Security: sensitive data in exception message never leaks to response
# ---------------------------------------------------------------------------

class TestSensitiveDataSuppression:
    async def test_db_url_not_in_response(self, exc_client: AsyncClient) -> None:
        """Exception message contains a DB URL — it must not appear in the body."""
        r = await exc_client.get("/sensitive-error")
        assert r.status_code == 500
        text = r.text
        assert "postgresql://" not in text
        assert "s3cr3t" not in text
        assert "db.internal" not in text

    async def test_sensitive_error_still_has_reference_id(
        self, exc_client: AsyncClient
    ) -> None:
        r = await exc_client.get("/sensitive-error")
        assert "reference_id" in r.json()

    async def test_sensitive_error_generic_message(
        self, exc_client: AsyncClient
    ) -> None:
        r = await exc_client.get("/sensitive-error")
        assert r.json()["message"] == "An unexpected error occurred"


# ---------------------------------------------------------------------------
# Integration: full middleware chain — X-Request-ID + security headers
# ---------------------------------------------------------------------------

class TestIntegrationFullMiddlewareChain:
    async def test_error_response_has_x_request_id(
        self, exc_client_full: AsyncClient
    ) -> None:
        r = await exc_client_full.get("/not-found")
        assert "x-request-id" in r.headers

    async def test_reference_id_matches_x_request_id_on_forgeguard_error(
        self, exc_client_full: AsyncClient
    ) -> None:
        r = await exc_client_full.get("/not-found")
        x_rid = r.headers.get("x-request-id")
        body = r.json()
        assert body["reference_id"] == x_rid

    async def test_reference_id_matches_x_request_id_on_500(
        self, exc_client_full: AsyncClient
    ) -> None:
        r = await exc_client_full.get("/unhandled")
        x_rid = r.headers.get("x-request-id")
        body = r.json()
        assert body["reference_id"] == x_rid

    async def test_error_response_has_security_headers(
        self, exc_client_full: AsyncClient
    ) -> None:
        r = await exc_client_full.get("/not-found")
        assert "x-content-type-options" in r.headers
        assert "x-frame-options" in r.headers

    async def test_500_error_has_security_headers(
        self, exc_client_full: AsyncClient
    ) -> None:
        r = await exc_client_full.get("/unhandled")
        assert "x-content-type-options" in r.headers

    async def test_x_request_id_present_on_forbidden(
        self, exc_client_full: AsyncClient
    ) -> None:
        r = await exc_client_full.get("/forbidden")
        assert "x-request-id" in r.headers
        body = r.json()
        assert body["reference_id"] == r.headers["x-request-id"]
