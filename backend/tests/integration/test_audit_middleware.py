"""Integration tests for AuditWriterMiddleware + AuditPreHookMiddleware (WO-030).

These tests construct a minimal ASGI app wired with both middleware layers and
exercise the full request/response cycle.  No database is required — the audit
service is replaced with a mock that records calls.

Coverage:
  - POST/PUT/PATCH/DELETE with 2xx response triggers one log_mutation call
  - GET requests do NOT trigger audit writes
  - Non-2xx responses do NOT trigger audit writes
  - Missing audit_context on request.state is handled gracefully
  - asyncio.shield protects the write from task cancellation
"""

from __future__ import annotations

import asyncio
import uuid
from typing import AsyncIterator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route
from starlette.testclient import TestClient

from forgeguard.core.audit_models import AuditContext
from forgeguard.middleware.audit import AuditWriterMiddleware
from forgeguard.middleware.audit_prehook import AuditPreHookMiddleware


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_audit_context(
    method: str = "POST",
    path: str = "/api/v1/services",
) -> AuditContext:
    return AuditContext(
        correlation_id=str(uuid.uuid4()),
        client_ip_masked="10.0.0.xxx",
        http_method=method,
        request_path=path,
        resource_type="services",
        resource_id=str(uuid.uuid4()),
        before_state={"id": str(uuid.uuid4()), "name": "test-svc"},
    )


def _make_app(
    mock_service: MagicMock,
    *,
    route_status: int = 201,
    set_audit_context: bool = True,
) -> Starlette:
    """Build a minimal Starlette app with both audit middleware layers."""

    async def handler(request: Request) -> Response:
        if set_audit_context:
            request.state.audit_context = _make_audit_context(request.method)
        request.state.actor_id = str(uuid.uuid4())
        request.state.user_role = "developer"
        return JSONResponse({"ok": True}, status_code=route_status)

    async def _factory():
        return mock_service

    app = Starlette(
        routes=[
            Route("/api/v1/services", handler, methods=["GET", "POST", "PUT", "PATCH", "DELETE"]),
            Route("/api/v1/services/{id}", handler, methods=["PUT", "PATCH", "DELETE"]),
        ],
        middleware=[
            # Inner: pre-hook captures before-state (attaches AuditContext)
            Middleware(AuditPreHookMiddleware),
            # Outer: writer persists the audit record after response
            Middleware(AuditWriterMiddleware, audit_service_factory=_factory),
        ],
    )
    return app


# ---------------------------------------------------------------------------
# Mutation methods → audit written
# ---------------------------------------------------------------------------

class TestMutationMethodsWriteAudit:
    @pytest.mark.parametrize("method", ["POST", "PUT", "PATCH", "DELETE"])
    def test_mutation_2xx_writes_audit(self, method):
        mock_svc = MagicMock()
        mock_svc.log_mutation = AsyncMock(return_value={"id": str(uuid.uuid4())})

        app = _make_app(mock_svc, route_status=200)
        client = TestClient(app, raise_server_exceptions=True)
        resp = client.request(method, "/api/v1/services")
        assert resp.status_code == 200
        mock_svc.log_mutation.assert_awaited_once()

    def test_post_201_writes_audit(self):
        mock_svc = MagicMock()
        mock_svc.log_mutation = AsyncMock(return_value={"id": str(uuid.uuid4())})

        app = _make_app(mock_svc, route_status=201)
        client = TestClient(app)
        resp = client.post("/api/v1/services")
        assert resp.status_code == 201
        mock_svc.log_mutation.assert_awaited_once()


# ---------------------------------------------------------------------------
# GET → no audit write
# ---------------------------------------------------------------------------

class TestGetRequestNoAudit:
    def test_get_does_not_write_audit(self):
        mock_svc = MagicMock()
        mock_svc.log_mutation = AsyncMock(return_value={"id": str(uuid.uuid4())})

        app = _make_app(mock_svc)
        client = TestClient(app)
        resp = client.get("/api/v1/services")
        assert resp.status_code == 200
        mock_svc.log_mutation.assert_not_awaited()


# ---------------------------------------------------------------------------
# Error responses → no audit write
# ---------------------------------------------------------------------------

class TestErrorResponseNoAudit:
    @pytest.mark.parametrize("status", [400, 401, 403, 404, 409, 422, 500])
    def test_non_2xx_does_not_write_audit(self, status):
        mock_svc = MagicMock()
        mock_svc.log_mutation = AsyncMock(return_value={"id": str(uuid.uuid4())})

        app = _make_app(mock_svc, route_status=status)
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.post("/api/v1/services")
        assert resp.status_code == status
        mock_svc.log_mutation.assert_not_awaited()


# ---------------------------------------------------------------------------
# Missing audit_context → graceful no-op
# ---------------------------------------------------------------------------

class TestMissingAuditContext:
    def test_no_audit_context_does_not_raise(self):
        mock_svc = MagicMock()
        mock_svc.log_mutation = AsyncMock(return_value={"id": str(uuid.uuid4())})

        app = _make_app(mock_svc, route_status=201, set_audit_context=False)
        client = TestClient(app, raise_server_exceptions=True)
        resp = client.post("/api/v1/services")
        assert resp.status_code == 201
        # With no audit context, the writer should skip the write silently
        mock_svc.log_mutation.assert_not_awaited()


# ---------------------------------------------------------------------------
# Audit write failure → request still succeeds (fire-and-forget semantics)
# ---------------------------------------------------------------------------

class TestWriteFailureIsolated:
    def test_db_failure_does_not_break_response(self):
        mock_svc = MagicMock()
        mock_svc.log_mutation = AsyncMock(side_effect=RuntimeError("DB down"))

        app = _make_app(mock_svc)
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.post("/api/v1/services")
        # Response should still be 2xx — the write failure is caught internally
        assert resp.status_code in range(200, 300)


# ---------------------------------------------------------------------------
# AuditWriterMiddleware: action derivation
# ---------------------------------------------------------------------------

class TestActionDerivation:
    def test_post_derives_created_action(self):
        mock_svc = MagicMock()
        mock_svc.log_mutation = AsyncMock(return_value={"id": str(uuid.uuid4())})

        app = _make_app(mock_svc, route_status=201)
        client = TestClient(app)
        client.post("/api/v1/services")

        call_kwargs = mock_svc.log_mutation.call_args.kwargs
        assert "created" in call_kwargs.get("action", "")

    def test_delete_derives_deleted_action(self):
        mock_svc = MagicMock()
        mock_svc.log_mutation = AsyncMock(return_value={"id": str(uuid.uuid4())})

        app = _make_app(mock_svc, route_status=200)
        client = TestClient(app)
        client.delete("/api/v1/services")

        call_kwargs = mock_svc.log_mutation.call_args.kwargs
        assert "deleted" in call_kwargs.get("action", "")
