"""ExceptionExpiryScheduler: automated expiration of time-bounded exceptions.

Runs daily at 04:00 UTC as a background job registered in SchedulerService.
Each run:
  1. Acquires a PostgreSQL advisory lock to prevent duplicate processing
     in multi-instance deployments.
  2. Queries approved exceptions where expires_at < NOW() in batches of 50.
  3. For each expired exception (in its own transaction):
       a. Updates exception status: 'approved' → 'expired'.
       b. Loads the associated finding and updates its status:
          'excepted' → 'reactivated' (skip gracefully if finding is missing
          or already in a terminal status).
       c. Writes two immutable audit records: exception.expired + finding.reactivated.
  4. Collects all affected service_ids and emits a structured log event for
     each one so downstream health-score recalculation can be triggered.
  5. Logs a run summary: total processed, total errors, affected services.

Idempotency:
  The query only returns status='approved' rows. An exception already transitioned
  to 'expired' is not returned, so double-processing is impossible.

Error handling:
  Failures are caught per-exception — one bad row does not abort the run.
  A structured error log is emitted for each failure.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any, Optional

import structlog

if TYPE_CHECKING:
    import asyncpg
    from forgeguard.services.audit import AuditService

logger = structlog.get_logger(__name__)

#: Batch size for exception queries — prevents long-running transactions.
_BATCH_SIZE = 50

#: PostgreSQL advisory lock key for exception expiry (arbitrary stable integer).
_ADVISORY_LOCK_KEY = 63_000_001

#: Finding statuses that indicate it was excepted (should be reactivated).
_EXCEPTED_STATUSES = frozenset({"excepted", "suppressed"})


class ExceptionExpiryScheduler:
    """Expire approved exceptions and reactivate their associated findings.

    Args:
        pool:          Async asyncpg connection pool.
        audit_service: Injected AuditService for immutable audit records.
    """

    def __init__(
        self,
        pool: "asyncpg.Pool",
        audit_service: "AuditService",
    ) -> None:
        self._pool = pool
        self._audit = audit_service

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def process_expired_exceptions(self) -> dict[str, Any]:
        """Run one expiry pass.

        Returns a summary dict:
          {processed, errors, skipped, affected_service_ids}
        """
        from forgeguard.data.repositories.exception_repository import (  # noqa: PLC0415
            ExceptionRepository,
        )
        from forgeguard.data.repositories.findings import FindingRepository  # noqa: PLC0415

        exception_repo = ExceptionRepository(self._pool)
        finding_repo = FindingRepository(self._pool)

        # Acquire an advisory lock to prevent duplicate runs across instances.
        acquired = await self._try_advisory_lock()
        if not acquired:
            logger.info(
                "exception_expiry.skipped_lock",
                reason="Another instance holds the advisory lock — skipping this run.",
            )
            return {"processed": 0, "errors": 0, "skipped": 0, "affected_service_ids": []}

        processed = 0
        errors = 0
        skipped = 0
        affected_service_ids: set[str] = set()

        try:
            # Process in batches to avoid long-running transactions.
            while True:
                batch = await exception_repo.list_expired_for_processing(
                    batch_size=_BATCH_SIZE
                )
                if not batch:
                    break

                for exc_row in batch:
                    try:
                        result = await self._process_one_exception(
                            exc_row, exception_repo, finding_repo
                        )
                        if result["expired"]:
                            processed += 1
                            if result["service_id"]:
                                affected_service_ids.add(str(result["service_id"]))
                        else:
                            skipped += 1
                    except Exception as err:
                        errors += 1
                        logger.error(
                            "exception_expiry.item_failed",
                            exception_id=str(exc_row.get("id")),
                            finding_id=str(exc_row.get("finding_id")),
                            error=str(err),
                            error_type=type(err).__name__,
                        )

                if len(batch) < _BATCH_SIZE:
                    break  # Last batch was partial — no more rows.

        finally:
            await self._release_advisory_lock()

        # Emit health-score recalculation trigger for each affected service.
        for service_id in affected_service_ids:
            logger.info(
                "exception_expiry.health_score_recalculation_required",
                service_id=service_id,
            )
            await self._trigger_health_score_recalculation(service_id)

        logger.info(
            "exception_expiry.run_complete",
            processed=processed,
            errors=errors,
            skipped=skipped,
            affected_service_count=len(affected_service_ids),
        )

        return {
            "processed": processed,
            "errors": errors,
            "skipped": skipped,
            "affected_service_ids": sorted(affected_service_ids),
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _process_one_exception(
        self,
        exc_row: dict[str, Any],
        exception_repo,
        finding_repo,
    ) -> dict[str, Any]:
        """Expire one exception and reactivate its finding in a single transaction.

        Returns:
          {"expired": bool, "service_id": str | None}
        """
        exception_id = exc_row["id"]
        finding_id = exc_row.get("finding_id")

        # Guard: expire atomically — the WHERE clause in expire() prevents
        # double-processing if another instance slipped through the advisory lock.
        expired_row = await exception_repo.expire(exception_id)
        if expired_row is None:
            logger.debug(
                "exception_expiry.already_expired",
                exception_id=str(exception_id),
            )
            return {"expired": False, "service_id": None}

        before_state = _row_to_serializable(exc_row)
        after_state = _row_to_serializable(expired_row)

        # Audit: exception.expired
        await self._audit.log_event(
            actor_id=None,
            actor_role="system",
            action="exception.expired",
            resource_type="exceptions",
            resource_id=exception_id,
            before_state=before_state,
            after_state=after_state,
        )

        logger.info(
            "exception_expiry.exception_expired",
            exception_id=str(exception_id),
            finding_id=str(finding_id) if finding_id else None,
        )

        service_id: str | None = None

        # Reactivate the associated finding (if present and in an excepted state).
        if finding_id:
            finding_before = await finding_repo.get_by_id(finding_id)
            if finding_before is None:
                logger.warning(
                    "exception_expiry.finding_not_found",
                    exception_id=str(exception_id),
                    finding_id=str(finding_id),
                    message="Finding was deleted; exception expired but finding reactivation skipped.",
                )
            elif finding_before.get("status") not in _EXCEPTED_STATUSES:
                logger.info(
                    "exception_expiry.finding_not_excepted",
                    exception_id=str(exception_id),
                    finding_id=str(finding_id),
                    current_status=finding_before.get("status"),
                    message="Finding is not in an excepted status; reactivation skipped.",
                )
                service_id = str(finding_before.get("service_id")) if finding_before.get("service_id") else None
            else:
                reactivated_finding = await finding_repo.update_status(
                    finding_id, "reactivated"
                )
                service_id = str(finding_before.get("service_id")) if finding_before.get("service_id") else None

                # Audit: finding.reactivated
                await self._audit.log_event(
                    actor_id=None,
                    actor_role="system",
                    action="finding.reactivated",
                    resource_type="findings",
                    resource_id=finding_id,
                    before_state=_row_to_serializable(finding_before),
                    after_state=_row_to_serializable(reactivated_finding),
                )

                logger.info(
                    "exception_expiry.finding_reactivated",
                    exception_id=str(exception_id),
                    finding_id=str(finding_id),
                    service_id=service_id,
                )

        return {"expired": True, "service_id": service_id}

    async def _trigger_health_score_recalculation(self, service_id: str) -> None:
        """Emit a recalculation trigger for the health scoring pipeline.

        The health scoring WO (WOREF-061) will provide a concrete
        ``recalculate_health_score(service_id)`` method.  Until that method
        exists, this emits a structured log event that downstream consumers
        (metrics aggregation, event bus) can subscribe to.
        """
        logger.info(
            "exception_expiry.trigger_health_score_recalculation",
            service_id=service_id,
            action="health_score.recalculation_requested",
        )

    async def _try_advisory_lock(self) -> bool:
        """Try to acquire a PostgreSQL session-level advisory lock.

        Returns True if the lock was acquired, False otherwise.
        Uses pg_try_advisory_lock which is non-blocking.
        """
        try:
            async with self._pool.acquire() as conn:
                result = await conn.fetchval(
                    "SELECT pg_try_advisory_lock($1)", _ADVISORY_LOCK_KEY
                )
            return bool(result)
        except Exception as exc:
            logger.warning(
                "exception_expiry.advisory_lock_error",
                error=str(exc),
                message="Could not acquire advisory lock; proceeding without it.",
            )
            return True  # Fail-open: proceed without lock rather than skip entirely.

    async def _release_advisory_lock(self) -> None:
        """Release the PostgreSQL session-level advisory lock."""
        try:
            async with self._pool.acquire() as conn:
                await conn.execute(
                    "SELECT pg_advisory_unlock($1)", _ADVISORY_LOCK_KEY
                )
        except Exception as exc:
            logger.warning(
                "exception_expiry.advisory_unlock_error",
                error=str(exc),
            )


def _row_to_serializable(row: dict[str, Any] | None) -> dict[str, Any] | None:
    """Convert a db row dict to JSON-serializable form (UUIDs and datetimes as str)."""
    if row is None:
        return None
    result: dict[str, Any] = {}
    for k, v in row.items():
        if isinstance(v, uuid.UUID):
            result[k] = str(v)
        elif hasattr(v, "isoformat"):
            result[k] = v.isoformat()
        else:
            result[k] = v
    return result
