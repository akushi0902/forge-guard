"""GitHub Webhook Receiver endpoint (WO-091).

Route:
    POST /api/v1/webhooks/github

Authentication:
    HMAC-SHA256 via X-Hub-Signature-256 header (NOT JWT).
    This endpoint is listed in PUBLIC_PATHS so JWT auth and RBAC middleware
    are bypassed.

Flow:
    1. Read raw request body.
    2. Validate X-Hub-Signature-256 (401 if invalid).
    3. Parse JSON payload.
    4. Filter non-pull_request events (200 Ignored).
    5. Check per-repository rate limit (429 if exceeded).
    6. Check delivery idempotency (200 Ignored if duplicate).
    7. Look up ForgeGuard service by repository URL.
    8. Create assessment record.
    9. Return 202 Accepted immediately.
   10. BackgroundTask: run assessment pipeline, post GitHub callbacks.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from typing import Any, Optional

import asyncpg
import structlog
from fastapi import APIRouter, BackgroundTasks, Header, Request
from fastapi.responses import JSONResponse

from forgeguard.core.config import get_settings
from forgeguard.middleware.hmac_auth import (
    HMACValidationError,
    PayloadTooLargeError,
    get_webhook_rate_limiter,
    validate_github_signature,
)
from forgeguard.services.github_client import (
    GitHubApiClient,
    GitHubClientError,
    build_pr_comment,
    risk_score_to_github_state,
)
from forgeguard.services.webhook import (
    TRACKED_PR_ACTIONS,
    WebhookParseError,
    WebhookProcessor,
    parse_pr_payload,
)

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/api/v1/webhooks", tags=["webhooks"])

_PIPELINE_TIMEOUT_SECONDS = 300


# ---------------------------------------------------------------------------
# Background task: run assessment pipeline and post GitHub callbacks
# ---------------------------------------------------------------------------

async def _run_webhook_pipeline(
    *,
    assessment_id: uuid.UUID,
    service_id: uuid.UUID,
    commit_sha: str,
    pr_reference: str,
    owner: str,
    repo: str,
    pr_number: int,
    event_id: uuid.UUID,
    processor: WebhookProcessor,
    github_client: GitHubApiClient,
    app_base_url: str,
) -> None:
    """Run the Release Guardian pipeline and post results back to GitHub.

    Fire-and-forget from the route handler. All exceptions are caught and
    logged to prevent task silently disappearing.
    """
    from forgeguard.data.repositories.assessment_score_repository import (  # noqa: PLC0415
        AssessmentScoreRepository,
    )
    from forgeguard.data.repositories.release_assessment_repository import (  # noqa: PLC0415
        ReleaseAssessmentRepository,
    )
    from forgeguard.services.release_guardian.change_analyzer import ChangeAnalyzer  # noqa: PLC0415
    from forgeguard.services.release_guardian.providers_mock import (  # noqa: PLC0415
        MockChangeDataProvider,
    )
    from forgeguard.services.release_guardian.risk_scorer import RiskScorer  # noqa: PLC0415

    pool = processor._pool  # noqa: SLF001
    target_url = f"{app_base_url}/api/v1/releases/{assessment_id}"

    log = logger.bind(
        assessment_id=str(assessment_id),
        event_id=str(event_id),
        owner=owner,
        repo=repo,
    )

    try:
        # Post initial 'pending' status check immediately.
        try:
            await github_client.post_status_check(
                owner=owner,
                repo=repo,
                sha=commit_sha,
                state="pending",
                description="ForgeGuard assessment running…",
                target_url=target_url,
            )
            await processor.log_github_status_posted(
                assessment_id=assessment_id,
                state="pending",
                description="ForgeGuard assessment running…",
            )
        except (GitHubClientError, Exception) as exc:
            log.warning("webhook_pipeline.pending_status_failed", error=str(exc))

        # Run assessment pipeline.
        assessment_repo = ReleaseAssessmentRepository(pool)
        score_repo = AssessmentScoreRepository(pool)

        await assessment_repo.update(assessment_id, {"status": "in_progress"})

        provider = MockChangeDataProvider()
        change_analyzer = ChangeAnalyzer(provider)
        risk_scorer = RiskScorer()

        async def _pipeline():
            analysis = await change_analyzer.analyze(
                service_id,
                commit_sha=commit_sha,
                pr_reference=pr_reference,
            )
            score = risk_scorer.score(analysis)
            return analysis, score

        analysis, score = await asyncio.wait_for(
            _pipeline(), timeout=_PIPELINE_TIMEOUT_SECONDS
        )

        await score_repo.save_risk_score(assessment_id, service_id, score)
        await assessment_repo.update(assessment_id, {"status": "completed"})
        await processor.mark_processed(event_id, assessment_id=assessment_id)

        # Map risk score to GitHub state.
        github_state, description = risk_score_to_github_state(score.overall_score)

        # Post final status check.
        try:
            await github_client.post_status_check(
                owner=owner,
                repo=repo,
                sha=commit_sha,
                state=github_state,
                description=description,
                target_url=target_url,
            )
            await processor.log_github_status_posted(
                assessment_id=assessment_id,
                state=github_state,
                description=description,
            )
        except (GitHubClientError, Exception) as exc:
            log.warning("webhook_pipeline.final_status_failed", error=str(exc))

        # Post PR comment.
        try:
            comment_body = build_pr_comment(
                assessment_id=str(assessment_id),
                risk_score=score.overall_score,
                findings=[],
                target_url=target_url,
            )
            await github_client.post_pr_comment(
                owner=owner,
                repo=repo,
                pr_number=pr_number,
                body=comment_body,
            )
            await processor.log_github_comment_posted(
                assessment_id=assessment_id,
                pr_number=pr_number,
            )
        except (GitHubClientError, Exception) as exc:
            log.warning("webhook_pipeline.comment_failed", error=str(exc))

        log.info("webhook_pipeline.completed", risk_score=score.overall_score)

    except asyncio.TimeoutError:
        log.error("webhook_pipeline.timeout", timeout=_PIPELINE_TIMEOUT_SECONDS)
        await _fail_assessment_and_github(
            assessment_id=assessment_id,
            event_id=event_id,
            owner=owner,
            repo=repo,
            commit_sha=commit_sha,
            target_url=target_url,
            processor=processor,
            github_client=github_client,
            description="Assessment timed out — see ForgeGuard for details",
        )

    except Exception as exc:
        log.exception("webhook_pipeline.failed", error=str(exc))
        await _fail_assessment_and_github(
            assessment_id=assessment_id,
            event_id=event_id,
            owner=owner,
            repo=repo,
            commit_sha=commit_sha,
            target_url=target_url,
            processor=processor,
            github_client=github_client,
            description="Assessment failed — see ForgeGuard for details",
        )


async def _fail_assessment_and_github(
    *,
    assessment_id: uuid.UUID,
    event_id: uuid.UUID,
    owner: str,
    repo: str,
    commit_sha: str,
    target_url: str,
    processor: WebhookProcessor,
    github_client: GitHubApiClient,
    description: str,
) -> None:
    from forgeguard.data.repositories.release_assessment_repository import (  # noqa: PLC0415
        ReleaseAssessmentRepository,
    )

    pool = processor._pool  # noqa: SLF001
    try:
        assessment_repo = ReleaseAssessmentRepository(pool)
        await assessment_repo.update(assessment_id, {"status": "failed"})
        await processor.mark_processed(event_id, assessment_id=assessment_id, status="failed")
        await github_client.post_status_check(
            owner=owner,
            repo=repo,
            sha=commit_sha,
            state="error",
            description=description,
            target_url=target_url,
        )
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Route handler
# ---------------------------------------------------------------------------

@router.post(
    "/github",
    summary="GitHub Webhook Receiver",
    response_description="202 Accepted — assessment triggered asynchronously",
    status_code=202,
)
async def receive_github_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    x_hub_signature_256: Optional[str] = Header(default=None, alias="X-Hub-Signature-256"),
    x_github_delivery: Optional[str] = Header(default=None, alias="X-GitHub-Delivery"),
    x_github_event: Optional[str] = Header(default=None, alias="X-GitHub-Event"),
) -> JSONResponse:
    """Accept a GitHub webhook delivery.

    Validates HMAC-SHA256, deduplicates by delivery_id, and triggers a release
    assessment asynchronously for tracked pull_request events.
    """
    settings = get_settings()

    # Read raw body before any framework parsing.
    raw_body = await request.body()

    # HMAC-SHA256 validation.
    try:
        validate_github_signature(raw_body, x_hub_signature_256, settings.github_webhook_secret)
    except PayloadTooLargeError:
        logger.warning("webhook.payload_too_large", size=len(raw_body))
        return JSONResponse(
            status_code=413,
            content={"error": "payload_too_large", "message": "Webhook payload exceeds 1 MB limit"},
        )
    except HMACValidationError:
        logger.warning(
            "webhook.invalid_signature",
            delivery_id=x_github_delivery or "unknown",
        )
        return JSONResponse(
            status_code=401,
            content={"error": "invalid_signature", "message": "Webhook signature validation failed"},
        )

    # Parse JSON.
    try:
        payload: dict[str, Any] = json.loads(raw_body)
    except json.JSONDecodeError:
        logger.warning("webhook.invalid_json", delivery_id=x_github_delivery or "unknown")
        return JSONResponse(
            status_code=400,
            content={"error": "invalid_payload", "message": "Request body is not valid JSON"},
        )

    delivery_id = x_github_delivery or str(uuid.uuid4())
    event_type = x_github_event or "unknown"

    # Acquire pool and build dependencies.
    pool: asyncpg.Pool = request.app.state.pool  # type: ignore[attr-defined]
    from forgeguard.data.repositories.audit_logs import AuditLogRepository  # noqa: PLC0415
    from forgeguard.services.audit import AuditService  # noqa: PLC0415

    audit_service = AuditService(AuditLogRepository(pool))
    processor = WebhookProcessor(pool, audit_service)

    # Handle non-pull_request events silently.
    if event_type != "pull_request":
        event_id = await processor.record_received(
            delivery_id=delivery_id,
            event_type=event_type,
            repository=payload.get("repository", {}).get("full_name", "unknown")
            if isinstance(payload.get("repository"), dict) else "unknown",
            payload_summary={"event_type": event_type},
        )
        await processor.mark_ignored(event_id, f"non-pull_request event: {event_type}")
        return JSONResponse(
            status_code=200,
            content={"status": "ignored", "reason": f"event type '{event_type}' is not processed"},
        )

    # Parse PR-specific payload.
    try:
        pr_data = parse_pr_payload(payload)
    except WebhookParseError as exc:
        logger.warning("webhook.parse_error", error=str(exc), delivery_id=delivery_id)
        return JSONResponse(
            status_code=400,
            content={"error": "parse_error", "message": "Could not parse webhook payload"},
        )

    repository = pr_data["repository"]

    # Per-repository rate limit check.
    rate_limiter = get_webhook_rate_limiter()
    allowed, retry_after = await rate_limiter.check(repository)
    if not allowed:
        logger.info(
            "webhook.rate_limited",
            repository=repository,
            delivery_id=delivery_id,
            retry_after=retry_after,
        )
        return JSONResponse(
            status_code=429,
            headers={"Retry-After": str(retry_after)},
            content={
                "error": "rate_limit_exceeded",
                "message": f"Too many webhook deliveries for {repository}. Retry after {retry_after}s.",
                "retry_after": retry_after,
            },
        )

    # Idempotency check BEFORE inserting a new record (delivery_id is UNIQUE).
    is_duplicate = await processor.check_idempotency(delivery_id)
    if is_duplicate:
        return JSONResponse(
            status_code=200,
            content={"status": "ignored", "reason": "duplicate delivery"},
        )

    # Record receipt.
    event_id = await processor.record_received(
        delivery_id=delivery_id,
        event_type=event_type,
        repository=repository,
        payload_summary={
            "action": pr_data["action"],
            "pr_number": pr_data["pr_number"],
            "head_sha": pr_data["head_sha"][:8] if pr_data["head_sha"] else None,
        },
    )

    # Filter PR actions.
    action = pr_data["action"]
    if action not in TRACKED_PR_ACTIONS:
        await processor.mark_ignored(event_id, f"PR action '{action}' is not tracked")
        return JSONResponse(
            status_code=200,
            content={"status": "ignored", "reason": f"PR action '{action}' is not processed"},
        )

    # Look up service by repository URL.
    service = await processor.lookup_service(pr_data["repo_html_url"])
    if not service:
        await processor.mark_ignored(event_id, "repository not registered in ForgeGuard")
        return JSONResponse(
            status_code=200,
            content={"status": "ignored", "reason": "repository not registered"},
        )

    # Create assessment record.
    pr_reference = pr_data["html_url"] or f"#{pr_data['pr_number']}"
    assessment_id = await processor.create_assessment(
        service_id=uuid.UUID(str(service["id"])),
        commit_sha=pr_data["head_sha"],
        pr_reference=pr_reference,
    )

    # Set up GitHub API client.
    github_client = GitHubApiClient(
        token=settings.github_api_token,
        base_url=settings.github_api_base_url,
    )
    app_base_url = str(request.base_url).rstrip("/")

    # Schedule async pipeline.
    background_tasks.add_task(
        _run_webhook_pipeline,
        assessment_id=assessment_id,
        service_id=uuid.UUID(str(service["id"])),
        commit_sha=pr_data["head_sha"],
        pr_reference=pr_reference,
        owner=pr_data["owner"],
        repo=pr_data["repo"],
        pr_number=pr_data["pr_number"],
        event_id=event_id,
        processor=processor,
        github_client=github_client,
        app_base_url=app_base_url,
    )

    logger.info(
        "webhook.assessment_scheduled",
        delivery_id=delivery_id,
        repository=repository,
        assessment_id=str(assessment_id),
        action=action,
    )

    return JSONResponse(
        status_code=202,
        content={
            "status": "accepted",
            "assessment_id": str(assessment_id),
        },
    )
