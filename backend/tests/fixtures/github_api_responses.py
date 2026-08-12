"""GitHub API response fixtures for WO-091 tests.

Provides mock response dicts for:
  - Status check created (201)
  - PR comment created (201)
  - Rate limit exceeded (403)
  - Unauthorized (401)
  - Not found (404)
"""

from __future__ import annotations

from typing import Any


def status_check_created(
    *,
    state: str = "success",
    sha: str = "abc1234567890abcdef1234567890abcdef12345",
    context: str = "forgeguard/release-risk",
    description: str = "Low risk — score: 25/100",
    target_url: str = "https://forgeguard.example.com/api/v1/releases/some-uuid",
) -> dict[str, Any]:
    """Successful GitHub commit status POST response (201 Created)."""
    return {
        "url": f"https://api.github.com/repos/acme/payments/statuses/{sha}",
        "id": 987654321,
        "state": state,
        "description": description,
        "target_url": target_url,
        "context": context,
        "created_at": "2026-08-12T10:00:00Z",
        "updated_at": "2026-08-12T10:00:00Z",
        "creator": {
            "login": "forgeguard-bot",
            "id": 1,
        },
    }


def pr_comment_created(
    *,
    pr_number: int = 42,
    body: str = "## ForgeGuard Release Assessment\n\n**Risk Score:** 25/100 — 🟢 Low Risk",
) -> dict[str, Any]:
    """Successful GitHub PR comment POST response (201 Created)."""
    return {
        "id": 123456789,
        "url": f"https://api.github.com/repos/acme/payments/issues/comments/123456789",
        "html_url": f"https://github.com/acme/payments/pull/{pr_number}#issuecomment-123456789",
        "body": body,
        "user": {
            "login": "forgeguard-bot",
            "id": 1,
        },
        "created_at": "2026-08-12T10:00:00Z",
        "updated_at": "2026-08-12T10:00:00Z",
    }


def rate_limit_exceeded() -> dict[str, Any]:
    """GitHub API rate limit exceeded response body (403)."""
    return {
        "message": "API rate limit exceeded for user ID 1.",
        "documentation_url": "https://docs.github.com/rest/overview/rate-limits",
    }


def rate_limit_exceeded_headers() -> dict[str, str]:
    """Response headers for a rate-limited GitHub API response."""
    return {
        "X-RateLimit-Limit": "5000",
        "X-RateLimit-Remaining": "0",
        "X-RateLimit-Reset": "1723456789",
        "Retry-After": "60",
    }


def unauthorized_response() -> dict[str, Any]:
    """GitHub API unauthorized response body (401)."""
    return {
        "message": "Bad credentials",
        "documentation_url": "https://docs.github.com/rest",
    }


def not_found_response() -> dict[str, Any]:
    """GitHub API not found response body (404)."""
    return {
        "message": "Not Found",
        "documentation_url": "https://docs.github.com/rest",
    }
