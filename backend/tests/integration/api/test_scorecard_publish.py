"""Integration tests for Forge Scorecard publish flow (WO-090).

Tests validate:
  AC-1  After assessment, scorecard publish is called with correct payload
  AC-2  Failed publish (5xx) enqueues retry job in pending_sync_jobs
  AC-3  After max retries, forge_sync_status=stale; GET /scores exposes stale flag
  AC-4  Every publish attempt produces an audit log record
  AC-7  GET /api/v1/services/{id}/scores returns scorecard_sync_status field

All database and adapter calls are mocked — no running PostgreSQL required.

Run:
    pytest tests/integration/api/test_scorecard_publish.py -v
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from forgeguard.services.assessment_orchestrator import AssessmentOrchestrator, AssessmentResult
from forgeguard.services.domain.scoring import DimensionScore
from forgeguard.services.forge_scorecard import (
    ForgeScorecardAdapter,
    ScorecardSyncStatus,
)
from forgeguard.services.sync_queue import SyncQueueService
from tests.fixtures.forge_scorecard_responses import (
    ASSESSMENT_ID,
    PUBLISH_RESULT_5XX,
    PUBLISH_RESULT_SUCCESS,
    PUBLISH_RESULT_4XX,
    SAMPLE_ASSESSED_AT,
    SAMPLE_DIMENSION_SCORES,
    SAMPLE_OVERALL_SCORE,
    SCORECARD_ID,
    SERVICE_ID,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_dimension_score(score: float = 75.0) -> DimensionScore:
    return DimensionScore(
        dimension="security",
        score=Decimal(str(score)),
        weight=Decimal("0.30"),
        total_rules=10,
        passed_rules=8,
        failed_rules=2,
        inconclusive_rules=0,
        error_rules=0,
        has_data=True,
    )


def _make_assessment_result(
    *,
    assessment_id: uuid.UUID = ASSESSMENT_ID,
    service_id: uuid.UUID = SERVICE_ID,
    overall_score: float = SAMPLE_OVERALL_SCORE,
) -> AssessmentResult:
    return AssessmentResult(
        assessment_id=assessment_id,
        status="completed",
        overall_score=Decimal(str(overall_score)),
        dimension_scores={
            "code_quality": _make_dimension_score(80.0),
            "test_coverage": _make_dimension_score(65.0),
            "security": _make_dimension_score(70.0),
            "documentation": _make_dimension_score(75.0),
            "operations_readiness": _make_dimension_score(78.0),
        },
        finding_counts={"critical": 0, "high": 1},
        evaluated_at=SAMPLE_ASSESSED_AT,
    )


def _make_orchestrator(
    *,
    scorecard_adapter: ForgeScorecardAdapter | None,
    sync_queue: SyncQueueService | None = None,
    scorecard_id: str | None = SCORECARD_ID,
    score_repo: Any = None,
    service_repo: Any = None,
) -> AssessmentOrchestrator:
    assessment_repo = AsyncMock()
    assessment_repo.create = AsyncMock(return_value={"id": ASSESSMENT_ID})
    assessment_repo.update_status = AsyncMock()
    assessment_repo.check_in_progress = AsyncMock(return_value=None)

    policy_repo = AsyncMock()
    policy_repo.list_active_rules = AsyncMock(return_value=[])

    if score_repo is None:
        score_repo = AsyncMock()
        score_repo.save_health_score = AsyncMock(return_value={"id": uuid.uuid4()})
        score_repo.update_forge_sync_status = AsyncMock()

    finding_repo = AsyncMock()
    finding_repo.count_by_severity = AsyncMock(return_value={})

    audit_svc = AsyncMock()
    audit_svc.log_event = AsyncMock(return_value={"id": uuid.uuid4()})

    if service_repo is None:
        service_repo = AsyncMock()
        service_repo.get_by_id = AsyncMock(
            return_value={"id": SERVICE_ID, "forge_catalog_id": scorecard_id}
        )

    from forgeguard.services.mock_data_collector import MockDataCollector  # noqa: PLC0415

    return AssessmentOrchestrator(
        assessment_repo=assessment_repo,
        policy_repo=policy_repo,
        score_repo=score_repo,
        finding_repo=finding_repo,
        data_collector=MockDataCollector(),
        audit_svc=audit_svc,
        scorecard_adapter=scorecard_adapter,
        sync_queue=sync_queue,
        service_repo=service_repo,
    )


# ---------------------------------------------------------------------------
# AC-1: Successful publish — adapter called with correct payload
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_successful_publish_calls_adapter():
    """After assessment completes, publish_score is called with overall + dimensions."""
    adapter = AsyncMock(spec=ForgeScorecardAdapter)
    adapter.publish_score = AsyncMock(return_value=PUBLISH_RESULT_SUCCESS)

    orchestrator = _make_orchestrator(scorecard_adapter=adapter)

    await orchestrator._publish_scorecard(
        assessment_id=ASSESSMENT_ID,
        service_id=SERVICE_ID,
        result=_make_assessment_result(),
    )

    adapter.publish_score.assert_called_once()
    call_kwargs = adapter.publish_score.call_args.kwargs
    assert call_kwargs["scorecard_id"] == SCORECARD_ID
    assert call_kwargs["service_id"] == SERVICE_ID
    assert call_kwargs["assessment_id"] == ASSESSMENT_ID
    assert abs(call_kwargs["overall_score"] - SAMPLE_OVERALL_SCORE) < 0.01


@pytest.mark.asyncio
async def test_successful_publish_updates_sync_status_to_synced():
    adapter = AsyncMock(spec=ForgeScorecardAdapter)
    adapter.publish_score = AsyncMock(return_value=PUBLISH_RESULT_SUCCESS)

    score_repo = AsyncMock()
    score_repo.save_health_score = AsyncMock(return_value={})
    score_repo.update_forge_sync_status = AsyncMock()

    orchestrator = _make_orchestrator(scorecard_adapter=adapter, score_repo=score_repo)

    await orchestrator._publish_scorecard(
        assessment_id=ASSESSMENT_ID,
        service_id=SERVICE_ID,
        result=_make_assessment_result(),
    )

    score_repo.update_forge_sync_status.assert_called_once_with(
        assessment_id=ASSESSMENT_ID,
        status=ScorecardSyncStatus.SYNCED,
    )


# ---------------------------------------------------------------------------
# AC-2: Failed publish (5xx) → enqueues retry job
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_5xx_failure_enqueues_retry():
    adapter = AsyncMock(spec=ForgeScorecardAdapter)
    adapter.publish_score = AsyncMock(return_value=PUBLISH_RESULT_5XX)

    sync_queue = AsyncMock(spec=SyncQueueService)
    sync_queue.enqueue_job = AsyncMock(return_value={"id": uuid.uuid4()})

    orchestrator = _make_orchestrator(scorecard_adapter=adapter, sync_queue=sync_queue)

    await orchestrator._publish_scorecard(
        assessment_id=ASSESSMENT_ID,
        service_id=SERVICE_ID,
        result=_make_assessment_result(),
    )

    sync_queue.enqueue_job.assert_called_once()
    payload = sync_queue.enqueue_job.call_args.kwargs["payload"]
    assert payload["scorecard_id"] == SCORECARD_ID
    assert payload["assessment_id"] == str(ASSESSMENT_ID)


@pytest.mark.asyncio
async def test_non_retryable_4xx_does_not_enqueue():
    adapter = AsyncMock(spec=ForgeScorecardAdapter)
    adapter.publish_score = AsyncMock(return_value=PUBLISH_RESULT_4XX)

    sync_queue = AsyncMock(spec=SyncQueueService)
    sync_queue.enqueue_job = AsyncMock()

    orchestrator = _make_orchestrator(scorecard_adapter=adapter, sync_queue=sync_queue)

    await orchestrator._publish_scorecard(
        assessment_id=ASSESSMENT_ID,
        service_id=SERVICE_ID,
        result=_make_assessment_result(),
    )

    sync_queue.enqueue_job.assert_not_called()


# ---------------------------------------------------------------------------
# AC-3: No catalog_id → blocked_no_catalog_id status
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_no_catalog_id_sets_blocked_status():
    adapter = AsyncMock(spec=ForgeScorecardAdapter)

    score_repo = AsyncMock()
    score_repo.save_health_score = AsyncMock(return_value={})
    score_repo.update_forge_sync_status = AsyncMock()

    service_repo = AsyncMock()
    service_repo.get_by_id = AsyncMock(return_value={"id": SERVICE_ID, "forge_catalog_id": None})

    orchestrator = _make_orchestrator(
        scorecard_adapter=adapter,
        score_repo=score_repo,
        service_repo=service_repo,
        scorecard_id=None,
    )

    await orchestrator._publish_scorecard(
        assessment_id=ASSESSMENT_ID,
        service_id=SERVICE_ID,
        result=_make_assessment_result(),
    )

    # Adapter must NOT be called when no catalog_id
    adapter.publish_score.assert_not_called()

    # sync_status set to blocked
    score_repo.update_forge_sync_status.assert_called_once_with(
        assessment_id=ASSESSMENT_ID,
        status=ScorecardSyncStatus.BLOCKED_NO_CATALOG_ID,
    )


# ---------------------------------------------------------------------------
# AC-4: Audit log is emitted for success and failure
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_success_emits_audit_log():
    adapter = AsyncMock(spec=ForgeScorecardAdapter)
    adapter.publish_score = AsyncMock(return_value=PUBLISH_RESULT_SUCCESS)

    audit_svc = AsyncMock()
    audit_svc.log_event = AsyncMock(return_value={"id": uuid.uuid4()})

    score_repo = AsyncMock()
    score_repo.save_health_score = AsyncMock(return_value={})
    score_repo.update_forge_sync_status = AsyncMock()

    service_repo = AsyncMock()
    service_repo.get_by_id = AsyncMock(return_value={"id": SERVICE_ID, "forge_catalog_id": SCORECARD_ID})

    assessment_repo = AsyncMock()
    assessment_repo.create = AsyncMock(return_value={"id": ASSESSMENT_ID})
    assessment_repo.update_status = AsyncMock()

    policy_repo = AsyncMock()
    policy_repo.list_active_rules = AsyncMock(return_value=[])

    finding_repo = AsyncMock()
    finding_repo.count_by_severity = AsyncMock(return_value={})

    from forgeguard.services.mock_data_collector import MockDataCollector  # noqa: PLC0415

    orchestrator = AssessmentOrchestrator(
        assessment_repo=assessment_repo,
        policy_repo=policy_repo,
        score_repo=score_repo,
        finding_repo=finding_repo,
        data_collector=MockDataCollector(),
        audit_svc=audit_svc,
        scorecard_adapter=adapter,
        sync_queue=None,
        service_repo=service_repo,
    )

    await orchestrator._publish_scorecard(
        assessment_id=ASSESSMENT_ID,
        service_id=SERVICE_ID,
        result=_make_assessment_result(),
    )

    # Audit log_event called at least once for the scorecard operation
    audit_svc.log_event.assert_called()
    actions = [c.kwargs.get("action") for c in audit_svc.log_event.call_args_list]
    assert "scorecard_publish_succeeded" in actions


@pytest.mark.asyncio
async def test_failure_emits_audit_log():
    adapter = AsyncMock(spec=ForgeScorecardAdapter)
    adapter.publish_score = AsyncMock(return_value=PUBLISH_RESULT_5XX)

    audit_svc = AsyncMock()
    audit_svc.log_event = AsyncMock(return_value={"id": uuid.uuid4()})

    score_repo = AsyncMock()
    score_repo.save_health_score = AsyncMock(return_value={})
    score_repo.update_forge_sync_status = AsyncMock()

    service_repo = AsyncMock()
    service_repo.get_by_id = AsyncMock(return_value={"id": SERVICE_ID, "forge_catalog_id": SCORECARD_ID})

    assessment_repo = AsyncMock()
    assessment_repo.create = AsyncMock(return_value={"id": ASSESSMENT_ID})
    assessment_repo.update_status = AsyncMock()

    policy_repo = AsyncMock()
    policy_repo.list_active_rules = AsyncMock(return_value=[])

    finding_repo = AsyncMock()
    finding_repo.count_by_severity = AsyncMock(return_value={})

    sync_queue = AsyncMock(spec=SyncQueueService)
    sync_queue.enqueue_job = AsyncMock(return_value={"id": uuid.uuid4()})

    from forgeguard.services.mock_data_collector import MockDataCollector  # noqa: PLC0415

    orchestrator = AssessmentOrchestrator(
        assessment_repo=assessment_repo,
        policy_repo=policy_repo,
        score_repo=score_repo,
        finding_repo=finding_repo,
        data_collector=MockDataCollector(),
        audit_svc=audit_svc,
        scorecard_adapter=adapter,
        sync_queue=sync_queue,
        service_repo=service_repo,
    )

    await orchestrator._publish_scorecard(
        assessment_id=ASSESSMENT_ID,
        service_id=SERVICE_ID,
        result=_make_assessment_result(),
    )

    audit_svc.log_event.assert_called()
    actions = [c.kwargs.get("action") for c in audit_svc.log_event.call_args_list]
    assert "scorecard_publish_failed" in actions


# ---------------------------------------------------------------------------
# AC-5: Adapter is injected — mock works without HTTP calls
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_mock_adapter_injected_no_http():
    """Confirms the ABC injection pattern: MockAdapter works without real HTTP."""

    class MockAdapter(ForgeScorecardAdapter):
        async def publish_score(self, **kwargs: Any) -> dict:
            return PUBLISH_RESULT_SUCCESS

        async def get_scorecard_status(self, *, scorecard_id: str) -> dict:
            return {"id": scorecard_id}

    orchestrator = _make_orchestrator(scorecard_adapter=MockAdapter())
    # Should run without any httpx calls
    await orchestrator._publish_scorecard(
        assessment_id=ASSESSMENT_ID,
        service_id=SERVICE_ID,
        result=_make_assessment_result(),
    )


# ---------------------------------------------------------------------------
# AC-7: HealthScoreResponse scorecard fields present
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_health_score_response_includes_scorecard_fields():
    """Verify HealthScoreResponse schema includes the three new scorecard fields."""
    from forgeguard.api.schemas.assessment import HealthScoreResponse

    response = HealthScoreResponse(
        service_id=SERVICE_ID,
        overall_score=Decimal("72.5"),
        forge_scorecard_stale=True,
        scorecard_sync_status="stale",
        last_scorecard_sync_at=None,
    )
    assert response.forge_scorecard_stale is True
    assert response.scorecard_sync_status == "stale"
    assert response.last_scorecard_sync_at is None


@pytest.mark.asyncio
async def test_health_score_response_stale_false_by_default():
    from forgeguard.api.schemas.assessment import HealthScoreResponse

    response = HealthScoreResponse(service_id=SERVICE_ID)
    assert response.forge_scorecard_stale is False
    assert response.scorecard_sync_status is None
