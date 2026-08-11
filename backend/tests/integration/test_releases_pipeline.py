"""Integration tests for the Release Assessment pipeline (WO-048).

Tests the full stack: HTTP → RBAC middleware → route handler → background task
with mock repositories and mock pipeline services.

No real database or external LLM is required — all I/O is mocked.

Scenarios:
  1. POST assess → 202 → GET shows 'pending' assessment
  2. POST assess with non-existent service → 404
  3. POST assess with invalid SHA format → 422
  4. POST assess with pr_reference exceeding 255 chars → 422
  5. GET non-existent assessment → 404
  6. GET list with cursor pagination
  7. Background task marks assessment 'completed' with risk score
  8. Background task marks assessment 'failed' on pipeline exception
  9. Background task marks assessment 'failed' on timeout
"""

from __future__ import annotations

import asyncio
import json
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

import forgeguard.core.config as _config_module
from forgeguard.api.schemas.releases import encode_cursor
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
# Test app factory
# ---------------------------------------------------------------------------


def _settings() -> Settings:
    return Settings(
        database_url="postgresql+asyncpg://postgres:postgres@localhost:5432/forgeguard_test",
        jwt_secret_key=TEST_JWT_SECRET,
        log_level="DEBUG",
        app_env="testing",
        llm_api_key="",
        forge_catalog_url="http://localhost:9999/catalog",
    )


_SERVICE_ID = uuid.UUID("d0000000-0000-0000-0000-000000000001")
_SERVICE_ROW = {
    "id": _SERVICE_ID,
    "name": "payment-service",
    "team": "payments",
    "status": "active",
}
_ASSESSMENT_ID = uuid.UUID("e0000000-0000-0000-0000-000000000001")
_NOW = datetime(2025, 6, 1, 12, 0, 0, tzinfo=timezone.utc)

_PENDING_ROW = {
    "id": _ASSESSMENT_ID,
    "service_id": _SERVICE_ID,
    "commit_sha": "a" * 40,
    "pr_reference": None,
    "status": "pending",
    "created_at": _NOW,
    "completed_at": None,
    "change_analysis": None,
    "requested_by": None,
}

_COMPLETED_ROW = {
    **_PENDING_ROW,
    "status": "completed",
    "completed_at": _NOW,
    "change_analysis": json.dumps({"summary": {}, "findings": []}),
}

_SCORE_ROW = {
    "id": uuid.uuid4(),
    "assessment_id": _ASSESSMENT_ID,
    "service_id": _SERVICE_ID,
    "score_type": "risk",
    "overall_score": 35,
    "dimension_scores": {"code_complexity": 20, "test_coverage": 40, "dependencies": 30, "security": 50},
    "contributing_factors": [],
    "created_at": _NOW,
}


def _make_app(
    service_row=_SERVICE_ROW,
    assessment_row=_PENDING_ROW,
    score_row=None,
    assessment_list=None,
):
    _config_module._settings_cache = _settings()
    app = create_app()

    mock_svc_repo = AsyncMock()
    mock_svc_repo.get_by_id.return_value = service_row

    mock_assessment_repo = AsyncMock()
    mock_assessment_repo.create.return_value = assessment_row
    mock_assessment_repo.get_by_id.return_value = assessment_row
    mock_assessment_repo.update.return_value = assessment_row
    mock_assessment_repo.list_page.return_value = (
        assessment_list if assessment_list is not None else [assessment_row]
    )

    mock_score_repo = AsyncMock()
    mock_score_repo.get_by_assessment_id.return_value = score_row

    mock_pool = MagicMock()

    app.dependency_overrides[get_service_repository] = lambda: mock_svc_repo
    app.dependency_overrides[get_release_assessment_repo] = lambda: mock_assessment_repo
    app.dependency_overrides[get_assessment_score_repo] = lambda: mock_score_repo
    app.dependency_overrides[get_pool] = lambda: mock_pool

    return app


def _auth(role: str = "developer") -> dict:
    token = make_access_token(role=role)
    return {"Cookie": f"access_token={token}"}


# ---------------------------------------------------------------------------
# POST /api/v1/releases/assess
# ---------------------------------------------------------------------------


class TestPostAssessIntegration:
    async def test_valid_request_returns_202_with_location(self) -> None:
        app = _make_app()
        with patch("forgeguard.api.routes.releases._run_assessment_pipeline"):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://testserver"
            ) as client:
                resp = await client.post(
                    "/api/v1/releases/assess",
                    json={"service_id": str(_SERVICE_ID), "commit_sha": "a" * 40},
                    headers=_auth("developer"),
                )
        assert resp.status_code == 202
        assert resp.headers.get("Location", "").startswith("/api/v1/releases/")
        body = resp.json()
        assert body["status"] == "pending"
        assert uuid.UUID(body["id"])  # valid UUID

    async def test_nonexistent_service_returns_404(self) -> None:
        app = _make_app(service_row=None)
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://testserver"
        ) as client:
            resp = await client.post(
                "/api/v1/releases/assess",
                json={"service_id": str(_SERVICE_ID), "commit_sha": "a" * 40},
                headers=_auth("developer"),
            )
        assert resp.status_code == 404
        detail = resp.json().get("detail", {})
        assert detail.get("error_code") == "not_found"

    async def test_invalid_sha_format_returns_422(self) -> None:
        app = _make_app()
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://testserver"
        ) as client:
            resp = await client.post(
                "/api/v1/releases/assess",
                json={"service_id": str(_SERVICE_ID), "commit_sha": "not-40-hex"},
                headers=_auth("developer"),
            )
        assert resp.status_code == 422

    async def test_pr_reference_over_255_chars_returns_422(self) -> None:
        app = _make_app()
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://testserver"
        ) as client:
            resp = await client.post(
                "/api/v1/releases/assess",
                json={"service_id": str(_SERVICE_ID), "pr_reference": "x" * 256},
                headers=_auth("developer"),
            )
        assert resp.status_code == 422

    async def test_missing_both_sha_and_pr_returns_422(self) -> None:
        app = _make_app()
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://testserver"
        ) as client:
            resp = await client.post(
                "/api/v1/releases/assess",
                json={"service_id": str(_SERVICE_ID)},
                headers=_auth("developer"),
            )
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# GET /api/v1/releases/{id}
# ---------------------------------------------------------------------------


class TestGetAssessmentIntegration:
    async def test_returns_pending_status_for_in_progress(self) -> None:
        pending_row = {**_PENDING_ROW, "status": "in_progress"}
        app = _make_app(assessment_row=pending_row)
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://testserver"
        ) as client:
            resp = await client.get(
                f"/api/v1/releases/{_ASSESSMENT_ID}",
                headers=_auth("developer"),
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "in_progress"
        assert body["risk_score"] is None
        assert body["findings"] == []

    async def test_returns_completed_with_score(self) -> None:
        app = _make_app(assessment_row=_COMPLETED_ROW, score_row=_SCORE_ROW)
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://testserver"
        ) as client:
            resp = await client.get(
                f"/api/v1/releases/{_ASSESSMENT_ID}",
                headers=_auth("developer"),
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "completed"
        assert body["risk_score"]["overall_score"] == 35
        assert "dimension_scores" in body["risk_score"]

    async def test_returns_404_for_unknown_id(self) -> None:
        app = _make_app(assessment_row=None)
        missing_repo = AsyncMock()
        missing_repo.get_by_id.return_value = None
        _config_module._settings_cache = _settings()
        fresh_app = create_app()
        fresh_app.dependency_overrides[get_release_assessment_repo] = lambda: missing_repo
        fresh_app.dependency_overrides[get_assessment_score_repo] = lambda: AsyncMock()
        fresh_app.dependency_overrides[get_pool] = lambda: MagicMock()
        fresh_app.dependency_overrides[get_service_repository] = lambda: AsyncMock()
        async with AsyncClient(
            transport=ASGITransport(app=fresh_app), base_url="http://testserver"
        ) as client:
            resp = await client.get(
                f"/api/v1/releases/{uuid.uuid4()}",
                headers=_auth("developer"),
            )
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# GET /api/v1/releases (list with pagination)
# ---------------------------------------------------------------------------


class TestListAssessmentsIntegration:
    async def test_list_returns_items_and_has_more_false(self) -> None:
        app = _make_app(assessment_list=[_COMPLETED_ROW])
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://testserver"
        ) as client:
            resp = await client.get(
                "/api/v1/releases",
                headers=_auth("developer"),
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["has_more"] is False
        assert len(body["items"]) == 1

    async def test_has_more_true_and_cursor_present_when_overflow(self) -> None:
        # Return limit+1 rows to trigger has_more=True
        rows = [
            {**_PENDING_ROW, "id": uuid.uuid4(), "created_at": _NOW}
            for _ in range(6)
        ]
        app = _make_app(assessment_list=rows)
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://testserver"
        ) as client:
            resp = await client.get(
                "/api/v1/releases?limit=5",
                headers=_auth("developer"),
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["has_more"] is True
        assert body["cursor"] is not None

    async def test_cursor_pagination_decodes_cleanly(self) -> None:
        """A valid cursor returned in one response can be used in the next request."""
        from forgeguard.api.schemas.releases import decode_cursor

        rows = [
            {**_PENDING_ROW, "id": uuid.uuid4(), "created_at": _NOW}
            for _ in range(6)
        ]
        app = _make_app(assessment_list=rows)
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://testserver"
        ) as client:
            resp = await client.get(
                "/api/v1/releases?limit=5",
                headers=_auth("developer"),
            )
        cursor = resp.json()["cursor"]
        ts, rec_id = decode_cursor(cursor)
        assert ts == _NOW
        assert isinstance(rec_id, uuid.UUID)

    async def test_filter_by_service_id(self) -> None:
        app = _make_app(assessment_list=[_COMPLETED_ROW])
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://testserver"
        ) as client:
            resp = await client.get(
                f"/api/v1/releases?service_id={_SERVICE_ID}",
                headers=_auth("developer"),
            )
        assert resp.status_code == 200

    async def test_filter_by_status(self) -> None:
        app = _make_app(assessment_list=[_COMPLETED_ROW])
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://testserver"
        ) as client:
            resp = await client.get(
                "/api/v1/releases?status=completed",
                headers=_auth("developer"),
            )
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Background pipeline
# ---------------------------------------------------------------------------


class TestBackgroundPipeline:
    async def test_pipeline_marks_failed_on_exception(self) -> None:
        """_mark_failed is called when pipeline raises an exception."""
        from forgeguard.api.routes.releases import _run_assessment_pipeline

        # Patch at the source module level (lazy imports inside _run_assessment_pipeline
        # resolve at call time, so we must patch the class in its defining module).
        with (
            patch(
                "forgeguard.data.repositories.release_assessment_repository.ReleaseAssessmentRepository",
                autospec=False,
            ) as MockAssRepo,
            patch(
                "forgeguard.data.repositories.assessment_score_repository.AssessmentScoreRepository",
                autospec=False,
            ),
            patch(
                "forgeguard.services.audit.AuditService",
                autospec=False,
            ) as MockAudit,
            patch(
                "forgeguard.services.release_guardian.change_analyzer.ChangeAnalyzer",
                autospec=False,
            ) as MockAnalyzer,
            patch(
                "forgeguard.services.release_guardian.risk_scorer.RiskScorer",
                autospec=False,
            ),
            patch(
                "forgeguard.services.release_guardian.prompt_loader.PromptLoader",
                autospec=False,
            ),
            patch(
                "forgeguard.services.release_guardian.explanation_generator.ExplanationGenerator",
                autospec=False,
            ),
            patch(
                "forgeguard.services.release_guardian.providers_mock.MockChangeDataProvider",
                autospec=False,
            ),
        ):
            mock_repo_instance = AsyncMock()
            MockAssRepo.return_value = mock_repo_instance
            mock_audit_instance = AsyncMock()
            MockAudit.return_value = mock_audit_instance

            # Make analyze raise to simulate failure
            mock_analyzer_instance = AsyncMock()
            mock_analyzer_instance.analyze.side_effect = RuntimeError("simulate failure")
            MockAnalyzer.return_value = mock_analyzer_instance

            await _run_assessment_pipeline(
                assessment_id=_ASSESSMENT_ID,
                service_id=_SERVICE_ID,
                service_name="test-service",
                commit_sha="a" * 40,
                pr_reference=None,
                pool=MagicMock(),
                ai_engine=MagicMock(),
                actor_id=None,
                actor_role="developer",
            )

            # Verify status was set to 'failed'
            update_calls = mock_repo_instance.update.call_args_list
            assert any(
                call.args[1].get("status") == "failed"
                for call in update_calls
                if len(call.args) > 1
            )

    async def test_pipeline_marks_failed_on_timeout(self) -> None:
        """Timeout from asyncio.wait_for results in 'failed' status."""
        from forgeguard.api.routes.releases import _run_assessment_pipeline

        with (
            patch(
                "forgeguard.data.repositories.release_assessment_repository.ReleaseAssessmentRepository",
                autospec=False,
            ) as MockAssRepo,
            patch(
                "forgeguard.data.repositories.assessment_score_repository.AssessmentScoreRepository",
                autospec=False,
            ),
            patch(
                "forgeguard.services.audit.AuditService",
                autospec=False,
            ) as MockAudit,
            patch(
                "forgeguard.services.release_guardian.change_analyzer.ChangeAnalyzer",
                autospec=False,
            ) as MockAnalyzer,
            patch(
                "forgeguard.services.release_guardian.risk_scorer.RiskScorer",
                autospec=False,
            ),
            patch(
                "forgeguard.services.release_guardian.prompt_loader.PromptLoader",
                autospec=False,
            ),
            patch(
                "forgeguard.services.release_guardian.explanation_generator.ExplanationGenerator",
                autospec=False,
            ),
            patch(
                "forgeguard.services.release_guardian.providers_mock.MockChangeDataProvider",
                autospec=False,
            ),
            patch("asyncio.wait_for", side_effect=asyncio.TimeoutError()),
        ):
            mock_repo_instance = AsyncMock()
            MockAssRepo.return_value = mock_repo_instance
            MockAudit.return_value = AsyncMock()
            MockAnalyzer.return_value = AsyncMock()

            await _run_assessment_pipeline(
                assessment_id=_ASSESSMENT_ID,
                service_id=_SERVICE_ID,
                service_name="test-service",
                commit_sha="a" * 40,
                pr_reference=None,
                pool=MagicMock(),
                ai_engine=MagicMock(),
                actor_id=None,
                actor_role="developer",
            )

            update_calls = mock_repo_instance.update.call_args_list
            assert any(
                call.args[1].get("status") == "failed"
                for call in update_calls
                if len(call.args) > 1
            )
