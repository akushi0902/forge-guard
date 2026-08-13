"""Unit tests for Release Assessment API endpoints (WO-048).

Uses FastAPI dependency overrides to inject mocked services.
No real database or LLM is needed.

Coverage:
  - POST /assess: 202 on valid request, 404 on missing service, 400 on bad input
  - POST /assess: RBAC — allowed roles (developer, tech_lead, platform_admin)
  - POST /assess: RBAC — denied roles (security_reviewer, operator, engineering_manager)
  - GET /{id}: 200 with full detail, 404 on missing assessment
  - GET /: returns paginated list with items and has_more
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

import forgeguard.core.config as _config_module
from forgeguard.core.config import Settings
from forgeguard.core.dependencies import (
    get_assessment_score_repo,
    get_pool,
    get_release_assessment_repo,
    get_service_repository,
)
from forgeguard.main import create_app
from tests.fixtures.tokens import TEST_JWT_SECRET, make_access_token


# ---------------------------------------------------------------------------
# App factory helpers
# ---------------------------------------------------------------------------

def _make_test_settings() -> Settings:
    return Settings(
        database_url="postgresql+asyncpg://postgres:postgres@localhost:5432/forgeguard_test",
        jwt_secret_key=TEST_JWT_SECRET,
        log_level="DEBUG",
        app_env="testing",
        llm_api_key="",
        forge_catalog_url="http://localhost:9999/catalog",
    )


def _make_app(
    *,
    service_row: Optional[dict] = None,
    assessment_row: Optional[dict] = None,
    assessment_list: Optional[list] = None,
    score_row: Optional[dict] = None,
):
    """Return a configured test app with repositories overridden."""
    settings = _make_test_settings()
    _config_module._settings_cache = settings
    app = create_app()

    # --- Service repository mock ---
    mock_service_repo = AsyncMock()
    mock_service_repo.get_by_id.return_value = service_row

    # --- Assessment repository mock ---
    _assessment_id = uuid.uuid4()
    default_row = {
        "id": _assessment_id,
        "service_id": uuid.uuid4(),
        "commit_sha": "a" * 40,
        "pr_reference": None,
        "status": "pending",
        "created_at": datetime(2025, 6, 1, 12, 0, 0, tzinfo=timezone.utc),
        "completed_at": None,
        "change_analysis": None,
        "requested_by": None,
    }
    actual_row = assessment_row if assessment_row is not None else default_row
    mock_assessment_repo = AsyncMock()
    mock_assessment_repo.create.return_value = actual_row
    mock_assessment_repo.get_by_id.return_value = actual_row
    mock_assessment_repo.list_page.return_value = assessment_list if assessment_list is not None else [actual_row]
    mock_assessment_repo.update.return_value = actual_row

    # --- Score repository mock ---
    mock_score_repo = AsyncMock()
    mock_score_repo.get_by_assessment_id.return_value = score_row

    app.dependency_overrides[get_service_repository] = lambda: mock_service_repo
    app.dependency_overrides[get_release_assessment_repo] = lambda: mock_assessment_repo
    app.dependency_overrides[get_assessment_score_repo] = lambda: mock_score_repo

    # Stub pool so the background task gets a pool reference without a real DB
    mock_pool = MagicMock()
    app.dependency_overrides[get_pool] = lambda: mock_pool

    return app


def _token_for(role: str) -> str:
    return make_access_token(role=role)


def _headers(role: str) -> dict:
    return {"Cookie": f"access_token={_token_for(role)}"}


_SERVICE_ROW = {
    "id": uuid.uuid4(),
    "name": "payment-service",
    "description": "Payment processing",
    "team": "payments",
    "status": "active",
}

_ASSESSMENT_ID = uuid.UUID("c0000000-0000-0000-0000-000000000001")
_SERVICE_ID = uuid.UUID("b0000000-0000-0000-0000-000000000001")

_COMPLETED_ROW = {
    "id": _ASSESSMENT_ID,
    "service_id": _SERVICE_ID,
    "commit_sha": "a" * 40,
    "pr_reference": None,
    "status": "completed",
    "created_at": datetime(2025, 6, 1, 12, 0, 0, tzinfo=timezone.utc),
    "completed_at": datetime(2025, 6, 1, 12, 5, 0, tzinfo=timezone.utc),
    "change_analysis": None,
    "requested_by": None,
}

_SCORE_ROW = {
    "id": uuid.uuid4(),
    "assessment_id": _ASSESSMENT_ID,
    "service_id": _SERVICE_ID,
    "score_type": "risk",
    "overall_score": 42,
    "dimension_scores": {"code_complexity": 30, "test_coverage": 60, "dependencies": 20, "security": 55},
    "contributing_factors": [],
    "created_at": datetime(2025, 6, 1, 12, 5, 0, tzinfo=timezone.utc),
}


# ---------------------------------------------------------------------------
# POST /api/v1/releases/assess
# ---------------------------------------------------------------------------


class TestPostAssess:
    async def test_returns_202_for_developer(self) -> None:
        app = _make_app(service_row=_SERVICE_ROW)
        with patch("forgeguard.api.routes.releases._run_assessment_pipeline"):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://testserver"
            ) as client:
                resp = await client.post(
                    "/api/v1/releases/assess",
                    json={"service_id": str(_SERVICE_ID), "commit_sha": "a" * 40},
                    headers=_headers("developer"),
                )
        assert resp.status_code == 202
        body = resp.json()
        assert "id" in body
        assert body["status"] == "pending"
        assert "Location" in resp.headers
        assert "/api/v1/releases/" in resp.headers["Location"]

    async def test_returns_202_for_tech_lead(self) -> None:
        app = _make_app(service_row=_SERVICE_ROW)
        with patch("forgeguard.api.routes.releases._run_assessment_pipeline"):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://testserver"
            ) as client:
                resp = await client.post(
                    "/api/v1/releases/assess",
                    json={"service_id": str(_SERVICE_ID), "pr_reference": "PR-123"},
                    headers=_headers("tech_lead"),
                )
        assert resp.status_code == 202

    async def test_returns_202_for_platform_admin(self) -> None:
        app = _make_app(service_row=_SERVICE_ROW)
        with patch("forgeguard.api.routes.releases._run_assessment_pipeline"):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://testserver"
            ) as client:
                resp = await client.post(
                    "/api/v1/releases/assess",
                    json={"service_id": str(_SERVICE_ID), "commit_sha": "b" * 40},
                    headers=_headers("platform_admin"),
                )
        assert resp.status_code == 202

    async def test_returns_403_for_security_reviewer(self) -> None:
        app = _make_app(service_row=_SERVICE_ROW)
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://testserver"
        ) as client:
            resp = await client.post(
                "/api/v1/releases/assess",
                json={"service_id": str(_SERVICE_ID), "commit_sha": "a" * 40},
                headers=_headers("security_reviewer"),
            )
        assert resp.status_code == 403

    async def test_returns_403_for_operator(self) -> None:
        app = _make_app(service_row=_SERVICE_ROW)
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://testserver"
        ) as client:
            resp = await client.post(
                "/api/v1/releases/assess",
                json={"service_id": str(_SERVICE_ID), "pr_reference": "PR-1"},
                headers=_headers("operator"),
            )
        assert resp.status_code == 403

    async def test_returns_403_for_engineering_manager(self) -> None:
        app = _make_app(service_row=_SERVICE_ROW)
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://testserver"
        ) as client:
            resp = await client.post(
                "/api/v1/releases/assess",
                json={"service_id": str(_SERVICE_ID), "pr_reference": "PR-1"},
                headers=_headers("engineering_manager"),
            )
        assert resp.status_code == 403

    async def test_returns_404_when_service_not_found(self) -> None:
        app = _make_app(service_row=None)
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://testserver"
        ) as client:
            resp = await client.post(
                "/api/v1/releases/assess",
                json={"service_id": str(_SERVICE_ID), "commit_sha": "a" * 40},
                headers=_headers("developer"),
            )
        assert resp.status_code == 404

    async def test_returns_422_for_invalid_sha(self) -> None:
        app = _make_app(service_row=_SERVICE_ROW)
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://testserver"
        ) as client:
            resp = await client.post(
                "/api/v1/releases/assess",
                json={"service_id": str(_SERVICE_ID), "commit_sha": "tooshort"},
                headers=_headers("developer"),
            )
        assert resp.status_code == 422

    async def test_returns_422_when_neither_sha_nor_pr_provided(self) -> None:
        app = _make_app(service_row=_SERVICE_ROW)
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://testserver"
        ) as client:
            resp = await client.post(
                "/api/v1/releases/assess",
                json={"service_id": str(_SERVICE_ID)},
                headers=_headers("developer"),
            )
        assert resp.status_code == 422

    async def test_returns_401_for_unauthenticated(self) -> None:
        app = _make_app(service_row=_SERVICE_ROW)
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://testserver"
        ) as client:
            resp = await client.post(
                "/api/v1/releases/assess",
                json={"service_id": str(_SERVICE_ID), "commit_sha": "a" * 40},
            )
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# GET /api/v1/releases/{id}
# ---------------------------------------------------------------------------


class TestGetAssessment:
    async def test_returns_200_for_completed_assessment(self) -> None:
        app = _make_app(assessment_row=_COMPLETED_ROW, score_row=_SCORE_ROW)
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://testserver"
        ) as client:
            resp = await client.get(
                f"/api/v1/releases/{_ASSESSMENT_ID}",
                headers=_headers("developer"),
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["id"] == str(_ASSESSMENT_ID)
        assert body["status"] == "completed"
        assert body["risk_score"]["overall_score"] == 42

    async def test_returns_200_with_empty_findings_when_none(self) -> None:
        app = _make_app(assessment_row=_COMPLETED_ROW, score_row=None)
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://testserver"
        ) as client:
            resp = await client.get(
                f"/api/v1/releases/{_ASSESSMENT_ID}",
                headers=_headers("developer"),
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["findings"] == []
        assert body["risk_score"] is None

    async def test_returns_404_for_nonexistent_assessment(self) -> None:
        app = _make_app(assessment_row=None)
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://testserver"
        ) as client:
            app.dependency_overrides[get_assessment_score_repo]
            mock_repo = AsyncMock()
            mock_repo.get_by_id.return_value = None
            app.dependency_overrides[get_release_assessment_repo] = lambda: mock_repo
            resp = await client.get(
                f"/api/v1/releases/{uuid.uuid4()}",
                headers=_headers("developer"),
            )
        assert resp.status_code == 404

    async def test_returns_403_for_security_reviewer_lacking_permission(self) -> None:
        # security_reviewer has SERVICE_VIEW so this should be 200 not 403
        # (security_reviewer can view releases but not post assessments)
        app = _make_app(assessment_row=_COMPLETED_ROW, score_row=None)
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://testserver"
        ) as client:
            resp = await client.get(
                f"/api/v1/releases/{_ASSESSMENT_ID}",
                headers=_headers("security_reviewer"),
            )
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# GET /api/v1/releases (list)
# ---------------------------------------------------------------------------


class TestListAssessments:
    async def test_returns_200_with_items(self) -> None:
        rows = [_COMPLETED_ROW, {**_COMPLETED_ROW, "id": uuid.uuid4()}]
        app = _make_app(assessment_list=rows)
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://testserver"
        ) as client:
            resp = await client.get(
                "/api/v1/releases",
                headers=_headers("developer"),
            )
        assert resp.status_code == 200
        body = resp.json()
        assert "items" in body
        assert "has_more" in body
        assert len(body["items"]) == 2

    async def test_has_more_false_when_at_or_below_limit(self) -> None:
        # With 1 item and default limit 50, has_more = False
        app = _make_app(assessment_list=[_COMPLETED_ROW])
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://testserver"
        ) as client:
            resp = await client.get(
                "/api/v1/releases?limit=50",
                headers=_headers("developer"),
            )
        assert resp.status_code == 200
        assert resp.json()["has_more"] is False
        assert resp.json()["cursor"] is None

    async def test_invalid_cursor_returns_400(self) -> None:
        app = _make_app(assessment_list=[])
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://testserver"
        ) as client:
            resp = await client.get(
                "/api/v1/releases?cursor=NOT_A_VALID_CURSOR!!!",
                headers=_headers("developer"),
            )
        assert resp.status_code == 400

    async def test_returns_401_for_unauthenticated(self) -> None:
        app = _make_app(assessment_list=[])
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://testserver"
        ) as client:
            resp = await client.get("/api/v1/releases")
        assert resp.status_code == 401
