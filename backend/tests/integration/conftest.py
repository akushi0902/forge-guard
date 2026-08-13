"""Integration-specific pytest fixtures (WO-097).

Shared fixtures for integration tests that exercise the full HTTP → middleware →
service → database pipeline.  All database and LLM calls are mocked — no
Docker or external service required unless a test is marked @pytest.mark.integration
(which uses the testcontainers fixtures from tests/conftest.py).

Fixture groups:
  _settings_no_db   — Settings with placeholder DB URL for in-process tests
  health_app        — FastAPI app with health-route dependency overrides
  release_app       — FastAPI app with release-route dependency overrides
  mock_orchestrator — Deterministic AssessmentOrchestrator
  _auth             — Cookie-based JWT auth helper for all integration tests

Run (no Docker):
    pytest tests/integration/test_assessment_pipeline.py \
           tests/integration/test_middleware_chain.py -v
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

import forgeguard.core.config as _config_module
from forgeguard.core.config import Settings
from forgeguard.main import create_app
from forgeguard.services.assessment_orchestrator import AssessmentResult
from forgeguard.services.domain.scoring import DimensionScore
from tests.fixtures.tokens import TEST_JWT_SECRET, make_access_token

# ---------------------------------------------------------------------------
# Shared constants
# ---------------------------------------------------------------------------

INTEGRATION_SERVICE_ID = uuid.UUID("aaaabbbb-0000-0000-0000-000000000001")
INTEGRATION_ASSESSMENT_ID = uuid.UUID("ccccdddd-0000-0000-0000-000000000001")
INTEGRATION_ACTOR_ID = uuid.UUID("eeeeeeee-0000-0000-0000-000000000001")
INTEGRATION_NOW = datetime(2026, 8, 13, 12, 0, 0, tzinfo=timezone.utc)

INTEGRATION_SERVICE_ROW = {
    "id": INTEGRATION_SERVICE_ID,
    "name": "payments-service",
    "team": "Platform",
    "repository_url": "https://github.com/acme/payments",
    "status": "active",
    "forge_catalog_id": "sc-test-001",
    "created_at": INTEGRATION_NOW,
    "updated_at": INTEGRATION_NOW,
}

INTEGRATION_SCORE_ROW = {
    "id": uuid.uuid4(),
    "assessment_id": INTEGRATION_ASSESSMENT_ID,
    "service_id": INTEGRATION_SERVICE_ID,
    "overall_score": Decimal("72.5"),
    "dimension_scores": {
        "code_quality": {
            "score": 80.0,
            "weight": 0.25,
            "total_rules": 10,
            "passed_rules": 8,
            "failed_rules": 2,
            "inconclusive_rules": 0,
            "error_rules": 0,
            "has_data": True,
        },
        "security": {
            "score": 70.0,
            "weight": 0.30,
            "total_rules": 5,
            "passed_rules": 4,
            "failed_rules": 1,
            "inconclusive_rules": 0,
            "error_rules": 0,
            "has_data": True,
        },
    },
    "finding_counts": {"critical": 0, "high": 1},
    "created_at": INTEGRATION_NOW,
    "forge_sync_status": "synced",
    "last_scorecard_sync_at": INTEGRATION_NOW,
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _test_settings() -> Settings:
    """Settings with placeholder DB URL — never makes real DB connections."""
    return Settings(
        database_url="postgresql+asyncpg://postgres:postgres@localhost:5432/forgeguard_test",
        jwt_secret_key=TEST_JWT_SECRET,
        log_level="DEBUG",
        app_env="testing",
        llm_api_key="",
        forge_catalog_url="http://localhost:9999/catalog",
    )


def _auth(role: str = "developer") -> dict[str, str]:
    """Return cookie auth headers for the given role."""
    token = make_access_token(role=role)
    return {"Cookie": f"access_token={token}"}


def _make_dim_score(dimension: str = "security", score: float = 72.5) -> DimensionScore:
    return DimensionScore(
        dimension=dimension,
        score=Decimal(str(score)),
        weight=Decimal("0.30"),
        total_rules=10,
        passed_rules=7,
        failed_rules=3,
        inconclusive_rules=0,
        error_rules=0,
        has_data=True,
    )


def _make_assessment_result(
    *,
    assessment_id: uuid.UUID = INTEGRATION_ASSESSMENT_ID,
    service_id: uuid.UUID = INTEGRATION_SERVICE_ID,
    overall_score: float = 72.5,
    status: str = "completed",
) -> AssessmentResult:
    """Build a deterministic AssessmentResult for use in mock orchestrators."""
    return AssessmentResult(
        assessment_id=assessment_id,
        status=status,
        overall_score=Decimal(str(overall_score)),
        dimension_scores={
            "code_quality": _make_dim_score("code_quality", 80.0),
            "test_coverage": _make_dim_score("test_coverage", 65.0),
            "security": _make_dim_score("security", 70.0),
            "documentation": _make_dim_score("documentation", 75.0),
            "operations_readiness": _make_dim_score("operations_readiness", 78.0),
        },
        finding_counts={"critical": 0, "high": 1, "medium": 3},
        evaluated_at=INTEGRATION_NOW,
    )


# ---------------------------------------------------------------------------
# Health-route app factory
# ---------------------------------------------------------------------------


def make_health_app(
    *,
    service_row: dict | None = INTEGRATION_SERVICE_ROW,
    score_row: dict | None = INTEGRATION_SCORE_ROW,
    orchestrator_result: AssessmentResult | None = None,
    in_progress_id: uuid.UUID | None = None,
    orchestrator_raises: Exception | None = None,
) -> Any:
    """Create a FastAPI test app with health-route dependencies overridden.

    Parameters:
        service_row:         Row returned by service_repo.get_by_id (None → 404).
        score_row:           Row returned by score_repo.get_latest (None → no prior score).
        orchestrator_result: AssessmentResult the mock orchestrator returns.
        in_progress_id:      If set, assessment_repo.check_in_progress returns this UUID.
        orchestrator_raises: If set, orchestrator.run() raises this exception.
    """
    from forgeguard.api.dependencies.audit import get_audit_service  # noqa: PLC0415
    from forgeguard.api.routes.health import (  # noqa: PLC0415
        get_assessment_repo,
        get_finding_repo,
        get_orchestrator,
        get_policy_repo,
        get_score_repo,
        get_service_repo,
    )
    from forgeguard.core.dependencies import get_pool  # noqa: PLC0415

    _config_module._settings_cache = _test_settings()
    app = create_app()

    # ── mock service repo ──────────────────────────────────────────────────
    mock_svc = AsyncMock()
    mock_svc.get_by_id = AsyncMock(return_value=service_row)

    # ── mock assessment repo ───────────────────────────────────────────────
    mock_assessment = AsyncMock()
    mock_assessment.check_in_progress = AsyncMock(
        return_value={"id": in_progress_id} if in_progress_id else None
    )
    mock_assessment.create = AsyncMock(return_value={"id": INTEGRATION_ASSESSMENT_ID})
    mock_assessment.update_status = AsyncMock()

    # ── mock score repo ────────────────────────────────────────────────────
    mock_scores = AsyncMock()
    mock_scores.get_latest_health_score = AsyncMock(return_value=score_row)
    mock_scores.save_health_score = AsyncMock(return_value={"id": uuid.uuid4()})
    mock_scores.update_forge_sync_status = AsyncMock()

    # ── mock finding repo ──────────────────────────────────────────────────
    mock_findings = AsyncMock()
    mock_findings.list_page = AsyncMock(return_value=([], None))
    mock_findings.count_by_severity = AsyncMock(return_value={})

    # ── mock policy repo ───────────────────────────────────────────────────
    mock_policy = AsyncMock()
    mock_policy.list_active_rules = AsyncMock(return_value=[])

    # ── mock audit service ─────────────────────────────────────────────────
    mock_audit = AsyncMock()
    mock_audit.log_event = AsyncMock(return_value={"id": uuid.uuid4()})

    # ── mock orchestrator ──────────────────────────────────────────────────
    result = orchestrator_result or _make_assessment_result()
    mock_orch = AsyncMock()
    if orchestrator_raises:
        mock_orch.run = AsyncMock(side_effect=orchestrator_raises)
    else:
        mock_orch.run = AsyncMock(return_value=result)

    # ── dependency overrides ───────────────────────────────────────────────
    app.dependency_overrides[get_pool] = lambda: MagicMock()
    app.dependency_overrides[get_service_repo] = lambda: mock_svc
    app.dependency_overrides[get_assessment_repo] = lambda: mock_assessment
    app.dependency_overrides[get_score_repo] = lambda: mock_scores
    app.dependency_overrides[get_finding_repo] = lambda: mock_findings
    app.dependency_overrides[get_policy_repo] = lambda: mock_policy
    app.dependency_overrides[get_audit_service] = lambda: mock_audit
    app.dependency_overrides[get_orchestrator] = lambda: mock_orch

    return app


# ---------------------------------------------------------------------------
# Pytest fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def integration_settings() -> Settings:
    """Test Settings suitable for integration tests (no real DB)."""
    return _test_settings()


@pytest.fixture()
def auth():
    """Return the _auth() helper so tests can call auth('role')."""
    return _auth


@pytest.fixture()
def make_result():
    """Return the _make_assessment_result factory for tests that need custom results."""
    return _make_assessment_result
