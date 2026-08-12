"""Unit tests for ExceptionExpiryScheduler (WO-063).

Tests cover:
  - Zero expired exceptions — clean no-op run
  - One expired exception — full expiry + finding reactivation
  - Multiple expired exceptions in one batch — all processed
  - Idempotency — running twice produces no duplicate state changes
  - Partial failure — one exception fails, others still process
  - Finding already resolved (not in excepted status) — expiry still proceeds
  - Finding deleted/missing — expiry still proceeds, finding step skipped
  - Advisory lock not acquired — scheduler exits immediately
  - Health score recalculation trigger emitted for each affected service

Run:
    pytest tests/unit/services/remediation/test_exception_expiry_scheduler.py -v
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest

from forgeguard.services.remediation.exception_expiry_scheduler import (
    ExceptionExpiryScheduler,
    _row_to_serializable,
)


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

def _exc_row(
    status: str = "approved",
    finding_id: str | None = None,
    service_id: str | None = None,
) -> dict[str, Any]:
    return {
        "id": str(uuid.uuid4()),
        "finding_id": finding_id or str(uuid.uuid4()),
        "status": status,
        "expires_at": datetime(2026, 7, 1, 0, 0, 0, tzinfo=timezone.utc),
        "justification": "Approved for demo",
        "requested_by": str(uuid.uuid4()),
    }


def _finding_row(
    status: str = "excepted",
    service_id: str | None = None,
) -> dict[str, Any]:
    sid = service_id or str(uuid.uuid4())
    return {
        "id": str(uuid.uuid4()),
        "service_id": sid,
        "status": status,
        "severity": "high",
        "title": "Finding A",
    }


def _make_scheduler(
    expired_batches: list[list[dict]],
    expire_side_effect: list | None = None,
    finding_side_effect: list | None = None,
    update_status_side_effect: list | None = None,
    advisory_lock_result: bool = True,
) -> tuple[ExceptionExpiryScheduler, MagicMock, MagicMock, MagicMock]:
    """Build a scheduler with fully mocked repositories and pool.

    Returns: (scheduler, mock_exception_repo, mock_finding_repo, mock_audit)
    """
    mock_pool = MagicMock()
    mock_audit = MagicMock()
    mock_audit.log_event = AsyncMock()

    mock_exception_repo = MagicMock()
    mock_finding_repo = MagicMock()

    # list_expired_for_processing cycles through batches
    mock_exception_repo.list_expired_for_processing = AsyncMock(
        side_effect=expired_batches + [[]]  # final empty batch terminates loop
    )

    if expire_side_effect is not None:
        mock_exception_repo.expire = AsyncMock(side_effect=expire_side_effect)
    else:
        # Default: return the row with status='expired'
        async def _expire_default(id):
            return {**_exc_row(status="expired"), "id": str(id)}
        mock_exception_repo.expire = AsyncMock(side_effect=_expire_default)

    if finding_side_effect is not None:
        mock_finding_repo.get_by_id = AsyncMock(side_effect=finding_side_effect)
    else:
        async def _get_finding_default(id):
            return _finding_row()
        mock_finding_repo.get_by_id = AsyncMock(side_effect=_get_finding_default)

    if update_status_side_effect is not None:
        mock_finding_repo.update_status = AsyncMock(side_effect=update_status_side_effect)
    else:
        async def _update_status_default(id, status):
            return _finding_row(status=status)
        mock_finding_repo.update_status = AsyncMock(side_effect=_update_status_default)

    scheduler = ExceptionExpiryScheduler(pool=mock_pool, audit_service=mock_audit)

    # Patch repository constructors and advisory lock
    with (
        patch(
            "forgeguard.services.remediation.exception_expiry_scheduler.ExceptionExpiryScheduler._try_advisory_lock",
            new_callable=AsyncMock,
            return_value=advisory_lock_result,
        ),
        patch(
            "forgeguard.services.remediation.exception_expiry_scheduler.ExceptionExpiryScheduler._release_advisory_lock",
            new_callable=AsyncMock,
        ),
    ):
        # Patch at the import level inside process_expired_exceptions
        with (
            patch(
                "forgeguard.services.remediation.exception_expiry_scheduler.ExceptionRepository",
                return_value=mock_exception_repo,
            ),
            patch(
                "forgeguard.services.remediation.exception_expiry_scheduler.FindingRepository",
                return_value=mock_finding_repo,
            ),
        ):
            return scheduler, mock_exception_repo, mock_finding_repo, mock_audit


# ---------------------------------------------------------------------------
# Tests: zero exceptions
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_no_expired_exceptions_clean_run():
    """When no exceptions are expired, scheduler runs cleanly and returns zeros."""
    mock_pool = MagicMock()
    mock_audit = MagicMock()
    mock_audit.log_event = AsyncMock()
    mock_exception_repo = MagicMock()
    mock_finding_repo = MagicMock()
    mock_exception_repo.list_expired_for_processing = AsyncMock(return_value=[])

    scheduler = ExceptionExpiryScheduler(pool=mock_pool, audit_service=mock_audit)

    with (
        patch.object(scheduler, "_try_advisory_lock", new_callable=AsyncMock, return_value=True),
        patch.object(scheduler, "_release_advisory_lock", new_callable=AsyncMock),
        patch("forgeguard.services.remediation.exception_expiry_scheduler.ExceptionRepository", return_value=mock_exception_repo),
        patch("forgeguard.services.remediation.exception_expiry_scheduler.FindingRepository", return_value=mock_finding_repo),
    ):
        result = await scheduler.process_expired_exceptions()

    assert result["processed"] == 0
    assert result["errors"] == 0
    assert result["skipped"] == 0
    assert result["affected_service_ids"] == []
    mock_audit.log_event.assert_not_called()


# ---------------------------------------------------------------------------
# Tests: single exception
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_single_exception_full_flow():
    """One expired exception: status transitions, finding reactivated, audit records written."""
    exc_id = str(uuid.uuid4())
    finding_id = str(uuid.uuid4())
    service_id = str(uuid.uuid4())
    exc = {**_exc_row(status="approved", finding_id=finding_id), "id": exc_id}
    finding = _finding_row(status="excepted", service_id=service_id)
    expired_exc = {**exc, "status": "expired"}

    mock_pool = MagicMock()
    mock_audit = MagicMock()
    mock_audit.log_event = AsyncMock()
    mock_exception_repo = MagicMock()
    mock_finding_repo = MagicMock()

    mock_exception_repo.list_expired_for_processing = AsyncMock(side_effect=[[exc], []])
    mock_exception_repo.expire = AsyncMock(return_value=expired_exc)
    mock_finding_repo.get_by_id = AsyncMock(return_value=finding)
    mock_finding_repo.update_status = AsyncMock(return_value={**finding, "status": "reactivated"})

    scheduler = ExceptionExpiryScheduler(pool=mock_pool, audit_service=mock_audit)

    with (
        patch.object(scheduler, "_try_advisory_lock", new_callable=AsyncMock, return_value=True),
        patch.object(scheduler, "_release_advisory_lock", new_callable=AsyncMock),
        patch("forgeguard.services.remediation.exception_expiry_scheduler.ExceptionRepository", return_value=mock_exception_repo),
        patch("forgeguard.services.remediation.exception_expiry_scheduler.FindingRepository", return_value=mock_finding_repo),
    ):
        result = await scheduler.process_expired_exceptions()

    assert result["processed"] == 1
    assert result["errors"] == 0
    assert service_id in result["affected_service_ids"]

    # Two audit events: exception.expired + finding.reactivated
    assert mock_audit.log_event.call_count == 2
    actions = [c.kwargs["action"] for c in mock_audit.log_event.call_args_list]
    assert "exception.expired" in actions
    assert "finding.reactivated" in actions

    # Finding update_status called with 'reactivated'
    mock_finding_repo.update_status.assert_awaited_once_with(finding_id, "reactivated")


# ---------------------------------------------------------------------------
# Tests: multiple exceptions
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_multiple_exceptions_all_processed():
    """Three expired exceptions all processed; three audit pairs written."""
    service_id = str(uuid.uuid4())
    exceptions = [_exc_row(finding_id=str(uuid.uuid4())) for _ in range(3)]
    findings = [_finding_row(status="excepted", service_id=service_id) for _ in range(3)]
    expired_excs = [{**e, "status": "expired"} for e in exceptions]

    mock_pool = MagicMock()
    mock_audit = MagicMock()
    mock_audit.log_event = AsyncMock()
    mock_exception_repo = MagicMock()
    mock_finding_repo = MagicMock()

    mock_exception_repo.list_expired_for_processing = AsyncMock(side_effect=[exceptions, []])
    mock_exception_repo.expire = AsyncMock(side_effect=expired_excs)
    mock_finding_repo.get_by_id = AsyncMock(side_effect=findings)
    mock_finding_repo.update_status = AsyncMock(side_effect=[{**f, "status": "reactivated"} for f in findings])

    scheduler = ExceptionExpiryScheduler(pool=mock_pool, audit_service=mock_audit)

    with (
        patch.object(scheduler, "_try_advisory_lock", new_callable=AsyncMock, return_value=True),
        patch.object(scheduler, "_release_advisory_lock", new_callable=AsyncMock),
        patch("forgeguard.services.remediation.exception_expiry_scheduler.ExceptionRepository", return_value=mock_exception_repo),
        patch("forgeguard.services.remediation.exception_expiry_scheduler.FindingRepository", return_value=mock_finding_repo),
    ):
        result = await scheduler.process_expired_exceptions()

    assert result["processed"] == 3
    assert result["errors"] == 0
    # 6 audit records: 3 × (exception.expired + finding.reactivated)
    assert mock_audit.log_event.call_count == 6


# ---------------------------------------------------------------------------
# Tests: idempotency
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_idempotency_second_run_no_duplicates():
    """Running the scheduler twice: first run processes; second run finds nothing."""
    exc = _exc_row()
    expired_exc = {**exc, "status": "expired"}
    finding = _finding_row()

    mock_pool = MagicMock()
    mock_audit = MagicMock()
    mock_audit.log_event = AsyncMock()
    mock_exception_repo = MagicMock()
    mock_finding_repo = MagicMock()

    # First run: one expired exception. Second run: nothing.
    mock_exception_repo.list_expired_for_processing = AsyncMock(
        side_effect=[[exc], [], [], []]
    )
    mock_exception_repo.expire = AsyncMock(return_value=expired_exc)
    mock_finding_repo.get_by_id = AsyncMock(return_value=finding)
    mock_finding_repo.update_status = AsyncMock(return_value={**finding, "status": "reactivated"})

    scheduler = ExceptionExpiryScheduler(pool=mock_pool, audit_service=mock_audit)

    with (
        patch.object(scheduler, "_try_advisory_lock", new_callable=AsyncMock, return_value=True),
        patch.object(scheduler, "_release_advisory_lock", new_callable=AsyncMock),
        patch("forgeguard.services.remediation.exception_expiry_scheduler.ExceptionRepository", return_value=mock_exception_repo),
        patch("forgeguard.services.remediation.exception_expiry_scheduler.FindingRepository", return_value=mock_finding_repo),
    ):
        result1 = await scheduler.process_expired_exceptions()
        result2 = await scheduler.process_expired_exceptions()

    assert result1["processed"] == 1
    assert result2["processed"] == 0
    # Audit events only from first run
    assert mock_audit.log_event.call_count == 2


@pytest.mark.asyncio
async def test_expire_returns_none_means_already_expired():
    """If expire() returns None (already transitioned), the exception is counted as skipped."""
    exc = _exc_row()
    mock_pool = MagicMock()
    mock_audit = MagicMock()
    mock_audit.log_event = AsyncMock()
    mock_exception_repo = MagicMock()
    mock_finding_repo = MagicMock()

    mock_exception_repo.list_expired_for_processing = AsyncMock(side_effect=[[exc], []])
    mock_exception_repo.expire = AsyncMock(return_value=None)  # already expired

    scheduler = ExceptionExpiryScheduler(pool=mock_pool, audit_service=mock_audit)

    with (
        patch.object(scheduler, "_try_advisory_lock", new_callable=AsyncMock, return_value=True),
        patch.object(scheduler, "_release_advisory_lock", new_callable=AsyncMock),
        patch("forgeguard.services.remediation.exception_expiry_scheduler.ExceptionRepository", return_value=mock_exception_repo),
        patch("forgeguard.services.remediation.exception_expiry_scheduler.FindingRepository", return_value=mock_finding_repo),
    ):
        result = await scheduler.process_expired_exceptions()

    assert result["processed"] == 0
    assert result["skipped"] == 1
    mock_audit.log_event.assert_not_called()
    mock_finding_repo.update_status.assert_not_called()


# ---------------------------------------------------------------------------
# Tests: partial failure
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_partial_failure_one_fails_others_continue():
    """If one exception's expiry raises, others in the batch still process."""
    exc1 = _exc_row(finding_id=str(uuid.uuid4()))
    exc2 = _exc_row(finding_id=str(uuid.uuid4()))
    exc3 = _exc_row(finding_id=str(uuid.uuid4()))
    finding = _finding_row()

    mock_pool = MagicMock()
    mock_audit = MagicMock()
    mock_audit.log_event = AsyncMock()
    mock_exception_repo = MagicMock()
    mock_finding_repo = MagicMock()

    mock_exception_repo.list_expired_for_processing = AsyncMock(
        side_effect=[[exc1, exc2, exc3], []]
    )
    # exc2 fails; exc1 and exc3 succeed
    mock_exception_repo.expire = AsyncMock(
        side_effect=[
            {**exc1, "status": "expired"},
            RuntimeError("DB connection lost"),
            {**exc3, "status": "expired"},
        ]
    )
    mock_finding_repo.get_by_id = AsyncMock(return_value=finding)
    mock_finding_repo.update_status = AsyncMock(return_value={**finding, "status": "reactivated"})

    scheduler = ExceptionExpiryScheduler(pool=mock_pool, audit_service=mock_audit)

    with (
        patch.object(scheduler, "_try_advisory_lock", new_callable=AsyncMock, return_value=True),
        patch.object(scheduler, "_release_advisory_lock", new_callable=AsyncMock),
        patch("forgeguard.services.remediation.exception_expiry_scheduler.ExceptionRepository", return_value=mock_exception_repo),
        patch("forgeguard.services.remediation.exception_expiry_scheduler.FindingRepository", return_value=mock_finding_repo),
    ):
        result = await scheduler.process_expired_exceptions()

    assert result["processed"] == 2
    assert result["errors"] == 1
    # 2 exceptions processed × 2 audit events each = 4
    assert mock_audit.log_event.call_count == 4


# ---------------------------------------------------------------------------
# Tests: edge cases
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_finding_not_in_excepted_status_skips_reactivation():
    """If finding is already in 'open' status, reactivation is skipped but exception still expires."""
    exc = _exc_row()
    finding_already_open = _finding_row(status="open")
    expired_exc = {**exc, "status": "expired"}

    mock_pool = MagicMock()
    mock_audit = MagicMock()
    mock_audit.log_event = AsyncMock()
    mock_exception_repo = MagicMock()
    mock_finding_repo = MagicMock()

    mock_exception_repo.list_expired_for_processing = AsyncMock(side_effect=[[exc], []])
    mock_exception_repo.expire = AsyncMock(return_value=expired_exc)
    mock_finding_repo.get_by_id = AsyncMock(return_value=finding_already_open)

    scheduler = ExceptionExpiryScheduler(pool=mock_pool, audit_service=mock_audit)

    with (
        patch.object(scheduler, "_try_advisory_lock", new_callable=AsyncMock, return_value=True),
        patch.object(scheduler, "_release_advisory_lock", new_callable=AsyncMock),
        patch("forgeguard.services.remediation.exception_expiry_scheduler.ExceptionRepository", return_value=mock_exception_repo),
        patch("forgeguard.services.remediation.exception_expiry_scheduler.FindingRepository", return_value=mock_finding_repo),
    ):
        result = await scheduler.process_expired_exceptions()

    assert result["processed"] == 1
    assert result["errors"] == 0
    # Only exception.expired audit event — no finding.reactivated
    assert mock_audit.log_event.call_count == 1
    mock_finding_repo.update_status.assert_not_called()


@pytest.mark.asyncio
async def test_finding_deleted_skips_gracefully():
    """If the associated finding is deleted (returns None), expiry still succeeds."""
    exc = _exc_row()
    expired_exc = {**exc, "status": "expired"}

    mock_pool = MagicMock()
    mock_audit = MagicMock()
    mock_audit.log_event = AsyncMock()
    mock_exception_repo = MagicMock()
    mock_finding_repo = MagicMock()

    mock_exception_repo.list_expired_for_processing = AsyncMock(side_effect=[[exc], []])
    mock_exception_repo.expire = AsyncMock(return_value=expired_exc)
    mock_finding_repo.get_by_id = AsyncMock(return_value=None)

    scheduler = ExceptionExpiryScheduler(pool=mock_pool, audit_service=mock_audit)

    with (
        patch.object(scheduler, "_try_advisory_lock", new_callable=AsyncMock, return_value=True),
        patch.object(scheduler, "_release_advisory_lock", new_callable=AsyncMock),
        patch("forgeguard.services.remediation.exception_expiry_scheduler.ExceptionRepository", return_value=mock_exception_repo),
        patch("forgeguard.services.remediation.exception_expiry_scheduler.FindingRepository", return_value=mock_finding_repo),
    ):
        result = await scheduler.process_expired_exceptions()

    assert result["processed"] == 1
    assert result["errors"] == 0
    # Only exception.expired audit (no finding.reactivated)
    assert mock_audit.log_event.call_count == 1
    mock_finding_repo.update_status.assert_not_called()


@pytest.mark.asyncio
async def test_exception_without_finding_id_still_expires():
    """Exception row with no finding_id should still expire cleanly."""
    exc = _exc_row()
    exc["finding_id"] = None
    expired_exc = {**exc, "status": "expired"}

    mock_pool = MagicMock()
    mock_audit = MagicMock()
    mock_audit.log_event = AsyncMock()
    mock_exception_repo = MagicMock()
    mock_finding_repo = MagicMock()

    mock_exception_repo.list_expired_for_processing = AsyncMock(side_effect=[[exc], []])
    mock_exception_repo.expire = AsyncMock(return_value=expired_exc)

    scheduler = ExceptionExpiryScheduler(pool=mock_pool, audit_service=mock_audit)

    with (
        patch.object(scheduler, "_try_advisory_lock", new_callable=AsyncMock, return_value=True),
        patch.object(scheduler, "_release_advisory_lock", new_callable=AsyncMock),
        patch("forgeguard.services.remediation.exception_expiry_scheduler.ExceptionRepository", return_value=mock_exception_repo),
        patch("forgeguard.services.remediation.exception_expiry_scheduler.FindingRepository", return_value=mock_finding_repo),
    ):
        result = await scheduler.process_expired_exceptions()

    assert result["processed"] == 1
    assert result["errors"] == 0
    mock_finding_repo.get_by_id.assert_not_called()


@pytest.mark.asyncio
async def test_advisory_lock_not_acquired_skips_run():
    """If advisory lock cannot be acquired, scheduler exits without processing."""
    mock_pool = MagicMock()
    mock_audit = MagicMock()
    mock_audit.log_event = AsyncMock()
    mock_exception_repo = MagicMock()
    mock_exception_repo.list_expired_for_processing = AsyncMock(return_value=[_exc_row()])

    scheduler = ExceptionExpiryScheduler(pool=mock_pool, audit_service=mock_audit)

    with (
        patch.object(scheduler, "_try_advisory_lock", new_callable=AsyncMock, return_value=False),
        patch.object(scheduler, "_release_advisory_lock", new_callable=AsyncMock),
        patch("forgeguard.services.remediation.exception_expiry_scheduler.ExceptionRepository", return_value=mock_exception_repo),
        patch("forgeguard.services.remediation.exception_expiry_scheduler.FindingRepository", return_value=MagicMock()),
    ):
        result = await scheduler.process_expired_exceptions()

    assert result["processed"] == 0
    assert result["affected_service_ids"] == []
    mock_exception_repo.list_expired_for_processing.assert_not_called()


@pytest.mark.asyncio
async def test_health_score_trigger_called_for_each_affected_service():
    """Health score recalculation trigger is emitted for each unique service_id."""
    service1 = str(uuid.uuid4())
    service2 = str(uuid.uuid4())

    finding1 = _finding_row(service_id=service1)
    finding2 = _finding_row(service_id=service2)
    finding3 = _finding_row(service_id=service1)  # duplicate service

    excs = [_exc_row() for _ in range(3)]
    expired = [{**e, "status": "expired"} for e in excs]

    mock_pool = MagicMock()
    mock_audit = MagicMock()
    mock_audit.log_event = AsyncMock()
    mock_exception_repo = MagicMock()
    mock_finding_repo = MagicMock()

    mock_exception_repo.list_expired_for_processing = AsyncMock(side_effect=[excs, []])
    mock_exception_repo.expire = AsyncMock(side_effect=expired)
    mock_finding_repo.get_by_id = AsyncMock(side_effect=[finding1, finding2, finding3])
    mock_finding_repo.update_status = AsyncMock(side_effect=[
        {**finding1, "status": "reactivated"},
        {**finding2, "status": "reactivated"},
        {**finding3, "status": "reactivated"},
    ])

    scheduler = ExceptionExpiryScheduler(pool=mock_pool, audit_service=mock_audit)

    with (
        patch.object(scheduler, "_try_advisory_lock", new_callable=AsyncMock, return_value=True),
        patch.object(scheduler, "_release_advisory_lock", new_callable=AsyncMock),
        patch("forgeguard.services.remediation.exception_expiry_scheduler.ExceptionRepository", return_value=mock_exception_repo),
        patch("forgeguard.services.remediation.exception_expiry_scheduler.FindingRepository", return_value=mock_finding_repo),
    ):
        with patch.object(scheduler, "_trigger_health_score_recalculation", new_callable=AsyncMock) as mock_trigger:
            result = await scheduler.process_expired_exceptions()

    # Only 2 unique services despite 3 findings
    assert sorted(result["affected_service_ids"]) == sorted([service1, service2])
    assert mock_trigger.call_count == 2


# ---------------------------------------------------------------------------
# Tests: _row_to_serializable helper
# ---------------------------------------------------------------------------

def test_row_to_serializable_converts_uuids():
    uid = uuid.uuid4()
    row = {"id": uid, "name": "test"}
    result = _row_to_serializable(row)
    assert result["id"] == str(uid)
    assert result["name"] == "test"


def test_row_to_serializable_converts_datetimes():
    dt = datetime(2026, 8, 12, 4, 0, 0, tzinfo=timezone.utc)
    row = {"expires_at": dt, "status": "expired"}
    result = _row_to_serializable(row)
    assert result["expires_at"] == dt.isoformat()


def test_row_to_serializable_none_input():
    assert _row_to_serializable(None) is None


def test_row_to_serializable_empty_dict():
    assert _row_to_serializable({}) == {}
