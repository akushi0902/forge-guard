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
"""

from __future__ import annotations

from typing import AsyncGenerator

import pytest
import pytest_asyncio
from fastapi import FastAPI, Path, Query
from httpx import ASGITransport, AsyncClient

from forgeguard.core.error_handlers import (
    format_validation_errors,
    register_error_handlers,
)
from forgeguard.core.validation import CommitSHAField, ForgeGuardBaseModel, ScoreField, UUIDField
from forgeguard.middleware.request_id import RequestIDMiddleware


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
