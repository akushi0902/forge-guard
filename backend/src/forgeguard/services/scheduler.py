"""SchedulerService: APScheduler-backed retention job runner.

Registers daily cron jobs for all six data retention categories and the
partition lifecycle management job.  Integrates with the FastAPI lifespan
event so the scheduler starts when the application starts and stops cleanly
on shutdown.

Job schedule (all times UTC):
  01:00 — partition management (create next month's partition)
  02:00 — audit log partition drops + release decisions purge
  03:00 — assessment scores purge + findings purge
  04:00 — AI conversations purge + expired exceptions purge

The scheduler uses an in-memory job store (acceptable for a single-instance
modular monolith — no external scheduler service required).
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Optional

import structlog

if TYPE_CHECKING:
    import asyncpg
    from forgeguard.core.config import Settings

logger = structlog.get_logger(__name__)


class SchedulerService:
    """Manages the APScheduler instance for all retention jobs.

    Args:
        settings: Application settings (retention periods, scheduler toggle).
    """

    def __init__(self, settings: "Settings") -> None:
        self._settings = settings
        self._scheduler: Optional[object] = None

    def start(self) -> None:
        """Start the APScheduler AsyncIOScheduler and register all retention jobs."""
        try:
            from apscheduler.schedulers.asyncio import AsyncIOScheduler  # noqa: PLC0415
            from apscheduler.triggers.cron import CronTrigger  # noqa: PLC0415
        except ImportError:
            logger.warning(
                "scheduler.apscheduler_missing",
                message="APScheduler not installed; retention scheduler disabled.",
            )
            return

        scheduler = AsyncIOScheduler()
        settings = self._settings

        # 01:00 UTC — partition management
        scheduler.add_job(
            _run_partition_management,
            CronTrigger(hour=1, minute=0, timezone="UTC"),
            id="partition_management",
            name="Audit Log Partition Management",
            kwargs={"settings": settings},
            replace_existing=True,
            misfire_grace_time=3600,
        )

        # 02:00 UTC — audit log purge + release decisions purge
        scheduler.add_job(
            _run_audit_log_purge,
            CronTrigger(hour=2, minute=0, timezone="UTC"),
            id="purge_audit_logs",
            name="Audit Log Partition Purge",
            kwargs={"settings": settings},
            replace_existing=True,
            misfire_grace_time=3600,
        )
        scheduler.add_job(
            _run_release_decisions_purge,
            CronTrigger(hour=2, minute=30, timezone="UTC"),
            id="purge_release_decisions",
            name="Release Decisions Purge",
            kwargs={"settings": settings},
            replace_existing=True,
            misfire_grace_time=3600,
        )

        # 03:00 UTC — assessment scores + findings purge
        scheduler.add_job(
            _run_assessments_purge,
            CronTrigger(hour=3, minute=0, timezone="UTC"),
            id="purge_assessments",
            name="Assessment Scores Purge",
            kwargs={"settings": settings},
            replace_existing=True,
            misfire_grace_time=3600,
        )
        scheduler.add_job(
            _run_findings_purge,
            CronTrigger(hour=3, minute=30, timezone="UTC"),
            id="purge_findings",
            name="Findings Purge",
            kwargs={"settings": settings},
            replace_existing=True,
            misfire_grace_time=3600,
        )

        # 04:00 UTC — AI conversations + expired exceptions purge
        scheduler.add_job(
            _run_ai_conversations_purge,
            CronTrigger(hour=4, minute=0, timezone="UTC"),
            id="purge_ai_conversations",
            name="AI Conversations Purge",
            kwargs={"settings": settings},
            replace_existing=True,
            misfire_grace_time=3600,
        )
        scheduler.add_job(
            _run_exceptions_purge,
            CronTrigger(hour=4, minute=30, timezone="UTC"),
            id="purge_exceptions",
            name="Expired Exceptions Purge",
            kwargs={"settings": settings},
            replace_existing=True,
            misfire_grace_time=3600,
        )

        scheduler.start()
        self._scheduler = scheduler
        logger.info("scheduler.started", job_count=len(scheduler.get_jobs()))

    def shutdown(self, wait: bool = True) -> None:
        """Stop the scheduler gracefully."""
        if self._scheduler is None:
            return
        try:
            self._scheduler.shutdown(wait=wait)  # type: ignore[union-attr]
            logger.info("scheduler.stopped")
        except Exception as exc:
            logger.warning("scheduler.shutdown_error", error=str(exc))
        finally:
            self._scheduler = None

    @property
    def is_running(self) -> bool:
        """Return True if the scheduler is active."""
        if self._scheduler is None:
            return False
        return getattr(self._scheduler, "running", False)


# ---------------------------------------------------------------------------
# Async job functions — each creates a RetentionService and calls one method.
# These are top-level functions (not methods) so APScheduler can serialize them.
# ---------------------------------------------------------------------------

async def _make_retention_service(settings: "Settings"):
    """Build a RetentionService using the live connection pool."""
    from forgeguard.data.database import get_pool  # noqa: PLC0415
    from forgeguard.data.repositories.audit_logs import AuditLogRepository  # noqa: PLC0415
    from forgeguard.services.audit import AuditService  # noqa: PLC0415
    from forgeguard.services.retention import RetentionService  # noqa: PLC0415

    pool = await get_pool()
    audit_service = AuditService(AuditLogRepository(pool))
    return RetentionService(
        pool=pool,
        audit_service=audit_service,
        retention_audit_days=settings.retention_audit_days,
        retention_assessment_days=settings.retention_assessment_days,
        retention_findings_days=settings.retention_findings_days,
        retention_release_decisions_days=settings.retention_release_decisions_days,
        retention_ai_conversations_days=settings.retention_ai_conversations_days,
        retention_exceptions_days=settings.retention_exceptions_days,
    )


async def _run_partition_management(settings: "Settings") -> None:
    try:
        svc = await _make_retention_service(settings)
        await svc.create_next_partition()
        await svc.drop_expired_partitions()
    except Exception as exc:
        logger.error("scheduler.job.failed", job="partition_management", error=str(exc))


async def _run_audit_log_purge(settings: "Settings") -> None:
    try:
        svc = await _make_retention_service(settings)
        await svc.purge_audit_logs()
    except Exception as exc:
        logger.error("scheduler.job.failed", job="purge_audit_logs", error=str(exc))


async def _run_release_decisions_purge(settings: "Settings") -> None:
    try:
        svc = await _make_retention_service(settings)
        await svc.purge_release_decisions()
    except Exception as exc:
        logger.error("scheduler.job.failed", job="purge_release_decisions", error=str(exc))


async def _run_assessments_purge(settings: "Settings") -> None:
    try:
        svc = await _make_retention_service(settings)
        await svc.purge_assessments()
    except Exception as exc:
        logger.error("scheduler.job.failed", job="purge_assessments", error=str(exc))


async def _run_findings_purge(settings: "Settings") -> None:
    try:
        svc = await _make_retention_service(settings)
        await svc.purge_findings()
    except Exception as exc:
        logger.error("scheduler.job.failed", job="purge_findings", error=str(exc))


async def _run_ai_conversations_purge(settings: "Settings") -> None:
    try:
        svc = await _make_retention_service(settings)
        await svc.purge_ai_conversations()
    except Exception as exc:
        logger.error("scheduler.job.failed", job="purge_ai_conversations", error=str(exc))


async def _run_exceptions_purge(settings: "Settings") -> None:
    try:
        svc = await _make_retention_service(settings)
        await svc.purge_expired_exceptions()
    except Exception as exc:
        logger.error("scheduler.job.failed", job="purge_exceptions", error=str(exc))
