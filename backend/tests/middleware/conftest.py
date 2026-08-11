"""Shared fixtures for middleware tests.

Provides:
  MockBeforeStateRepository  — in-memory repo for audit pre-hook tests.
  make_audit_app             — factory for a minimal test FastAPI app
                               with AuditPreHookMiddleware registered.
"""

from __future__ import annotations

from typing import Optional

import pytest
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from httpx import ASGITransport, AsyncClient

from forgeguard.core.audit_models import AuditContext


# ---------------------------------------------------------------------------
# Mock repository
# ---------------------------------------------------------------------------

class MockBeforeStateRepository:
    """In-memory repository for testing the audit pre-hook middleware.

    Args:
        states:       Mapping of resource_id → before-state dict.  IDs not
                      present return ``None`` (resource not found).
        raise_for_ids: Set of resource IDs that should raise a RuntimeError
                      to simulate a database failure.
        timeout_ids:  Set of resource IDs whose lookup should never return
                      (to test the asyncio timeout path).
    """

    def __init__(
        self,
        states: Optional[dict[str, dict]] = None,
        raise_for_ids: Optional[set[str]] = None,
        timeout_ids: Optional[set[str]] = None,
    ) -> None:
        self._states: dict[str, dict] = states or {}
        self._raise_for: set[str] = raise_for_ids or set()
        self._timeout_ids: set[str] = timeout_ids or set()

    async def get_before_state(
        self, resource_type: str, resource_id: str
    ) -> Optional[dict]:
        if resource_id in self._raise_for:
            raise RuntimeError(f"Simulated DB failure for resource_id={resource_id!r}")
        if resource_id in self._timeout_ids:
            import asyncio  # noqa: PLC0415
            await asyncio.sleep(10)  # much longer than the 500 ms middleware timeout
        return self._states.get(resource_id)


# ---------------------------------------------------------------------------
# Test app factory
# ---------------------------------------------------------------------------

def make_audit_app(
    mock_repo: Optional[MockBeforeStateRepository] = None,
    include_request_id_middleware: bool = False,
) -> FastAPI:
    """Create a minimal FastAPI test application with AuditPreHookMiddleware.

    The app exposes two catch-all routes that return the serialised
    ``AuditContext`` (or ``{"audit_context": null}`` when absent) so tests
    can inspect the middleware output.

    Args:
        mock_repo: Repository instance to inject.  Defaults to a no-op.
        include_request_id_middleware: When True, also registers
            RequestIDMiddleware so ``request.state.correlation_id`` is
            populated (required for integration tests).
    """
    from forgeguard.middleware.audit_prehook import AuditPreHookMiddleware  # noqa: PLC0415

    app = FastAPI()

    @app.api_route(
        "/api/v1/{resource_type}/{resource_id}",
        methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    )
    async def resource_handler(
        request: Request,
        resource_type: str,
        resource_id: str,
    ) -> JSONResponse:
        ctx: Optional[AuditContext] = getattr(request.state, "audit_context", None)
        correlation_id = getattr(request.state, "correlation_id", None)
        return JSONResponse({
            "audit_context": ctx.model_dump(mode="json") if ctx else None,
            "correlation_id": correlation_id,
        })

    @app.api_route(
        "/api/v1/{resource_type}",
        methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    )
    async def collection_handler(
        request: Request,
        resource_type: str,
    ) -> JSONResponse:
        ctx: Optional[AuditContext] = getattr(request.state, "audit_context", None)
        correlation_id = getattr(request.state, "correlation_id", None)
        return JSONResponse({
            "audit_context": ctx.model_dump(mode="json") if ctx else None,
            "correlation_id": correlation_id,
        })

    repo_factory = (lambda: mock_repo) if mock_repo is not None else None
    app.add_middleware(AuditPreHookMiddleware, before_state_repo_factory=repo_factory)

    if include_request_id_middleware:
        from forgeguard.middleware.request_id import RequestIDMiddleware  # noqa: PLC0415
        app.add_middleware(RequestIDMiddleware)

    return app


# ---------------------------------------------------------------------------
# Pytest fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_repo() -> MockBeforeStateRepository:
    """Default mock repo with a single known service resource."""
    return MockBeforeStateRepository(
        states={
            "service-uuid-001": {"id": "service-uuid-001", "name": "Payment Service"},
        }
    )


@pytest.fixture
async def audit_client(mock_repo: MockBeforeStateRepository) -> AsyncClient:
    """httpx AsyncClient bound to a test app with AuditPreHookMiddleware."""
    app = make_audit_app(mock_repo=mock_repo)
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        yield client
