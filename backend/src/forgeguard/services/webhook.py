"""GitHub webhook processing service (WO-091).

Handles the full lifecycle of an inbound GitHub webhook delivery:
  1. Parse and validate the event type (only pull_request is processed).
  2. Extract PR payload: repository, PR number, head SHA, action.
  3. Check idempotency via the webhook_events table (delivery_id).
  4. Look up the ForgeGuard service by repository URL.
  5. Trigger a release assessment via the Release Guardian pipeline.
  6. Post a commit status check and PR comment back to GitHub.

Audit events emitted:
  - webhook_received
  - webhook_ignored    (non-PR event or unregistered repo)
  - webhook_duplicate  (same delivery_id received again)
  - assessment_triggered
  - github_status_posted
  - github_comment_posted
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Optional

import asyncpg
import structlog

from forgeguard.services.audit import AuditService

logger = structlog.get_logger(__name__)

# PR actions that trigger an assessment.
TRACKED_PR_ACTIONS: frozenset[str] = frozenset({"opened", "synchronize", "reopened"})


# ---------------------------------------------------------------------------
# Payload parsing
# ---------------------------------------------------------------------------

class WebhookParseError(Exception):
    """Raised when the webhook payload cannot be parsed."""


def parse_pr_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Extract fields from a GitHub pull_request event payload.

    Returns a dict with:
        repository  — full repo name (e.g. "acme/payments")
        owner       — repo owner
        repo        — repo name
        pr_number   — integer PR number
        head_sha    — head commit SHA
        action      — PR action string
        html_url    — pull request HTML URL
        repo_url    — repository clone/api URL (html_url of repo)

    Raises:
        WebhookParseError: If any required field is absent.
    """
    try:
        pull_request = payload["pull_request"]
        repo_data = payload["repository"]
        action = payload["action"]
        pr_number = int(pull_request["number"])
        head_sha = pull_request["head"]["sha"]
        repository = repo_data["full_name"]
        owner, _, repo = repository.partition("/")
        html_url = pull_request.get("html_url", "")
        repo_html_url = repo_data.get("html_url", "")
    except (KeyError, TypeError, ValueError) as exc:
        raise WebhookParseError(f"Malformed pull_request payload: {exc}") from exc

    return {
        "repository": repository,
        "owner": owner,
        "repo": repo,
        "pr_number": pr_number,
        "head_sha": head_sha,
        "action": action,
        "html_url": html_url,
        "repo_html_url": repo_html_url,
    }


# ---------------------------------------------------------------------------
# WebhookProcessor
# ---------------------------------------------------------------------------

class WebhookProcessor:
    """Orchestrates the GitHub webhook → release assessment pipeline.

    Args:
        pool:          asyncpg connection pool.
        audit_service: AuditService for immutable event logging.
    """

    def __init__(self, pool: asyncpg.Pool, audit_service: AuditService) -> None:
        self._pool = pool
        self._audit = audit_service

    # ------------------------------------------------------------------
    # Idempotency
    # ------------------------------------------------------------------

    async def check_idempotency(self, delivery_id: str) -> bool:
        """Return True if this delivery_id was already processed.

        Checks the webhook_events table for an existing record with the same
        delivery_id.  If found, logs a duplicate event and returns True.
        """
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT id, processing_status FROM webhook_events WHERE delivery_id = $1",
                delivery_id,
            )
        if row:
            logger.info(
                "webhook_duplicate",
                delivery_id=delivery_id,
                existing_status=row["processing_status"],
            )
            return True
        return False

    async def record_received(
        self,
        *,
        delivery_id: str,
        event_type: str,
        repository: str,
        payload_summary: dict[str, Any],
    ) -> uuid.UUID:
        """Insert a 'received' record into webhook_events.

        Returns the new webhook_event UUID.
        """
        event_id = uuid.uuid4()
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO webhook_events
                    (id, delivery_id, event_type, repository, payload_summary,
                     processing_status, received_at)
                VALUES ($1, $2, $3, $4, $5, 'received', now())
                """,
                event_id,
                delivery_id,
                event_type,
                repository,
                payload_summary,
            )
        await self._audit.log_event(
            actor_id=None,
            actor_role="system",
            action="webhook_received",
            resource_type="webhook_event",
            resource_id=str(event_id),
            details={
                "delivery_id": delivery_id,
                "event_type": event_type,
                "repository": repository,
            },
        )
        return event_id

    async def mark_processed(
        self,
        event_id: uuid.UUID,
        *,
        assessment_id: Optional[uuid.UUID] = None,
        status: str = "processed",
    ) -> None:
        """Update webhook_events.processing_status and optional assessment_id."""
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE webhook_events
                SET processing_status = $1,
                    assessment_id = $2,
                    processed_at = now()
                WHERE id = $3
                """,
                status,
                assessment_id,
                event_id,
            )

    async def mark_ignored(self, event_id: uuid.UUID, reason: str) -> None:
        """Mark a webhook event as ignored with a reason in payload_summary."""
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE webhook_events
                SET processing_status = 'ignored',
                    payload_summary = jsonb_set(
                        COALESCE(payload_summary, '{}'),
                        '{ignore_reason}',
                        $1::jsonb
                    ),
                    processed_at = now()
                WHERE id = $2
                """,
                f'"{reason}"',
                event_id,
            )
        await self._audit.log_event(
            actor_id=None,
            actor_role="system",
            action="webhook_ignored",
            resource_type="webhook_event",
            resource_id=str(event_id),
            details={"reason": reason},
        )

    # ------------------------------------------------------------------
    # Service lookup
    # ------------------------------------------------------------------

    async def lookup_service(self, repo_html_url: str) -> Optional[dict[str, Any]]:
        """Find a ForgeGuard service by exact repository URL match.

        Args:
            repo_html_url: GitHub HTML URL of the repository
                           (e.g. "https://github.com/acme/payments").

        Returns:
            Row dict with service id, name, etc. or None if not found.
            Uses exact match only (no partial match) to prevent false positives.
        """
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT id, name FROM services WHERE repository_url = $1",
                repo_html_url,
            )
        return dict(row) if row else None

    # ------------------------------------------------------------------
    # Assessment triggering
    # ------------------------------------------------------------------

    async def create_assessment(
        self,
        *,
        service_id: uuid.UUID,
        commit_sha: str,
        pr_reference: str,
    ) -> uuid.UUID:
        """Create a release assessment record with trigger_type='github_webhook'.

        Returns the new assessment UUID.
        """
        assessment_id = uuid.uuid4()
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO release_assessments
                    (id, service_id, commit_sha, pr_reference, trigger_type,
                     status, created_at, updated_at)
                VALUES ($1, $2, $3, $4, 'github_webhook', 'pending', now(), now())
                """,
                assessment_id,
                service_id,
                commit_sha,
                pr_reference,
            )
        await self._audit.log_event(
            actor_id=None,
            actor_role="system",
            action="assessment_triggered",
            resource_type="release_assessment",
            resource_id=str(assessment_id),
            details={
                "service_id": str(service_id),
                "commit_sha": commit_sha,
                "pr_reference": pr_reference,
                "trigger_type": "github_webhook",
            },
        )
        return assessment_id

    # ------------------------------------------------------------------
    # GitHub callback helpers
    # ------------------------------------------------------------------

    async def log_github_status_posted(
        self,
        *,
        assessment_id: uuid.UUID,
        state: str,
        description: str,
    ) -> None:
        """Emit an audit record for a posted GitHub status check."""
        await self._audit.log_event(
            actor_id=None,
            actor_role="system",
            action="github_status_posted",
            resource_type="release_assessment",
            resource_id=str(assessment_id),
            details={"state": state, "description": description},
        )

    async def log_github_comment_posted(
        self,
        *,
        assessment_id: uuid.UUID,
        pr_number: int,
    ) -> None:
        """Emit an audit record for a posted GitHub PR comment."""
        await self._audit.log_event(
            actor_id=None,
            actor_role="system",
            action="github_comment_posted",
            resource_type="release_assessment",
            resource_id=str(assessment_id),
            details={"pr_number": pr_number},
        )
