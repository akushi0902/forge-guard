"""GitHub webhook payload fixtures for WO-091 tests.

Provides realistic payload dicts for:
  - PR opened
  - PR synchronize
  - PR reopened
  - PR closed (should be ignored)
  - PR labeled (should be ignored)
  - push event (non-pull_request, should be ignored)
"""

from __future__ import annotations

from typing import Any

_REPO = {
    "id": 123456789,
    "full_name": "acme/payments",
    "name": "payments",
    "html_url": "https://github.com/acme/payments",
    "clone_url": "https://github.com/acme/payments.git",
    "owner": {
        "login": "acme",
        "id": 1,
        "type": "Organization",
    },
}

_PR_BASE = {
    "number": 42,
    "title": "feat: add payment retry logic",
    "state": "open",
    "html_url": "https://github.com/acme/payments/pull/42",
    "head": {
        "sha": "abc1234567890abcdef1234567890abcdef12345",
        "ref": "feat/retry-logic",
        "repo": _REPO,
    },
    "base": {
        "sha": "def0987654321fedcba0987654321fedcba09876",
        "ref": "main",
        "repo": _REPO,
    },
    "user": {
        "login": "developer1",
        "id": 99,
    },
    "draft": False,
    "body": "Adds exponential backoff for payment retries.",
    "changed_files": 5,
    "additions": 120,
    "deletions": 30,
}


def pr_opened_payload(
    *,
    delivery_id: str = "11111111-1111-1111-1111-111111111111",
    head_sha: str = "abc1234567890abcdef1234567890abcdef12345",
    repo_html_url: str = "https://github.com/acme/payments",
    pr_number: int = 42,
) -> dict[str, Any]:
    """Payload for a PR 'opened' event."""
    pr = dict(_PR_BASE)
    pr["number"] = pr_number
    pr["html_url"] = f"{repo_html_url}/pull/{pr_number}"
    pr["head"] = dict(_PR_BASE["head"])
    pr["head"]["sha"] = head_sha
    repo = dict(_REPO)
    repo["html_url"] = repo_html_url
    return {
        "action": "opened",
        "number": pr_number,
        "pull_request": pr,
        "repository": repo,
        "sender": {"login": "developer1", "id": 99},
        "installation": {"id": 12345},
    }


def pr_synchronize_payload(
    *,
    delivery_id: str = "22222222-2222-2222-2222-222222222222",
    head_sha: str = "bcd2345678901bcdef2345678901bcdef23456",
    repo_html_url: str = "https://github.com/acme/payments",
    pr_number: int = 42,
) -> dict[str, Any]:
    """Payload for a PR 'synchronize' event (new commits pushed)."""
    payload = pr_opened_payload(
        delivery_id=delivery_id,
        head_sha=head_sha,
        repo_html_url=repo_html_url,
        pr_number=pr_number,
    )
    payload["action"] = "synchronize"
    payload["before"] = "abc1234567890abcdef1234567890abcdef12345"
    payload["after"] = head_sha
    return payload


def pr_reopened_payload(
    *,
    delivery_id: str = "33333333-3333-3333-3333-333333333333",
    head_sha: str = "abc1234567890abcdef1234567890abcdef12345",
    repo_html_url: str = "https://github.com/acme/payments",
    pr_number: int = 42,
) -> dict[str, Any]:
    """Payload for a PR 'reopened' event."""
    payload = pr_opened_payload(
        delivery_id=delivery_id,
        head_sha=head_sha,
        repo_html_url=repo_html_url,
        pr_number=pr_number,
    )
    payload["action"] = "reopened"
    return payload


def pr_closed_payload(
    *,
    delivery_id: str = "44444444-4444-4444-4444-444444444444",
    merged: bool = False,
) -> dict[str, Any]:
    """Payload for a PR 'closed' event — should be ignored."""
    payload = pr_opened_payload(delivery_id=delivery_id)
    payload["action"] = "closed"
    payload["pull_request"]["state"] = "closed"
    payload["pull_request"]["merged"] = merged
    return payload


def pr_labeled_payload(
    *,
    delivery_id: str = "55555555-5555-5555-5555-555555555555",
    label: str = "needs-review",
) -> dict[str, Any]:
    """Payload for a PR 'labeled' event — should be ignored."""
    payload = pr_opened_payload(delivery_id=delivery_id)
    payload["action"] = "labeled"
    payload["label"] = {"name": label, "color": "ededed"}
    return payload


def push_event_payload(
    *,
    delivery_id: str = "66666666-6666-6666-6666-666666666666",
    ref: str = "refs/heads/main",
) -> dict[str, Any]:
    """Payload for a 'push' event — non-pull_request, should be ignored."""
    return {
        "ref": ref,
        "before": "abc1234567890abcdef1234567890abcdef12345",
        "after": "def0987654321fedcba0987654321fedcba09876",
        "repository": _REPO,
        "pusher": {"name": "developer1", "email": "dev@acme.com"},
        "commits": [
            {
                "id": "def0987654321fedcba0987654321fedcba09876",
                "message": "chore: update deps",
                "author": {"name": "developer1"},
            }
        ],
    }


def malformed_payload() -> dict[str, Any]:
    """A pull_request payload missing required fields."""
    return {
        "action": "opened",
        # Missing 'pull_request' and 'repository' keys
    }
