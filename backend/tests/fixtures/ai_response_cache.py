"""Test fixtures for AI response cache (WO-060).

Provides:
    - Sample cache entry dicts in fresh, about-to-expire, and expired states
    - Sample finding dicts for cache key computation tests
    - Factory function for arbitrary cache row construction
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

from forgeguard.services.ai_engine.response_cache import DBResponseCache

# ---------------------------------------------------------------------------
# Stable IDs
# ---------------------------------------------------------------------------

CACHE_ENTRY_FRESH_ID = uuid.UUID("c0000000-0000-0000-0000-000000000001")
CACHE_ENTRY_EXPIRING_ID = uuid.UUID("c0000000-0000-0000-0000-000000000002")
CACHE_ENTRY_EXPIRED_ID = uuid.UUID("c0000000-0000-0000-0000-000000000003")

POLICY_RULE_ID_A = uuid.UUID("a0000000-0000-0000-0000-000000000001")
POLICY_RULE_ID_B = uuid.UUID("a0000000-0000-0000-0000-000000000002")

# ---------------------------------------------------------------------------
# Sample findings (used for cache key computation)
# ---------------------------------------------------------------------------

FINDING_CRITICAL_SECURITY: dict[str, Any] = {
    "id": uuid.UUID("f0000000-0000-0000-0000-000000000001"),
    "dimension": "security",
    "severity": "critical",
    "policy_rule_id": POLICY_RULE_ID_A,
    "title": "Missing SAST scan",
    "description": "No SAST scan configured for this service.",
}

FINDING_HIGH_QUALITY: dict[str, Any] = {
    "id": uuid.UUID("f0000000-0000-0000-0000-000000000002"),
    "dimension": "code_quality",
    "severity": "high",
    "policy_rule_id": POLICY_RULE_ID_B,
    "title": "Low test coverage",
    "description": "Test coverage below 80%.",
}

FINDING_NO_RULE: dict[str, Any] = {
    "id": uuid.UUID("f0000000-0000-0000-0000-000000000003"),
    "dimension": "reliability",
    "severity": "medium",
    "policy_rule_id": None,
    "title": "No SLO defined",
    "description": "Service lacks an SLO definition.",
}

# ---------------------------------------------------------------------------
# Pre-computed cache keys for the findings above
# ---------------------------------------------------------------------------

CACHE_KEY_CRITICAL_SECURITY = DBResponseCache.compute_cache_key(
    dimension="security",
    severity="critical",
    policy_rule_id=str(POLICY_RULE_ID_A),
)
CACHE_KEY_HIGH_QUALITY = DBResponseCache.compute_cache_key(
    dimension="code_quality",
    severity="high",
    policy_rule_id=str(POLICY_RULE_ID_B),
)
CACHE_KEY_NO_RULE = DBResponseCache.compute_cache_key(
    dimension="reliability",
    severity="medium",
    policy_rule_id=None,
)

# ---------------------------------------------------------------------------
# Cache entry dicts (match DB row shape returned by CacheRepository)
# ---------------------------------------------------------------------------

_NOW = datetime.now(tz=timezone.utc)

CACHE_ENTRY_FRESH: dict[str, Any] = {
    "id": CACHE_ENTRY_FRESH_ID,
    "cache_key": CACHE_KEY_CRITICAL_SECURITY,
    "response_text": "Configure SAST scanning for the CI pipeline.",
    "implementation_guide": "1. Add SAST tool.\n2. Configure pipeline.\n3. Review results.",
    "confidence_score": Decimal("0.85"),
    "source": "ai_generated",
    "policy_rule_id": POLICY_RULE_ID_A,
    "prompt_template_version": 1,
    "created_at": _NOW - timedelta(minutes=30),
    "expires_at": _NOW + timedelta(hours=1),
}

CACHE_ENTRY_ABOUT_TO_EXPIRE: dict[str, Any] = {
    "id": CACHE_ENTRY_EXPIRING_ID,
    "cache_key": CACHE_KEY_HIGH_QUALITY,
    "response_text": "Increase test coverage to at least 80%.",
    "implementation_guide": "1. Add unit tests.\n2. Run coverage report.\n3. Fill gaps.",
    "confidence_score": Decimal("0.75"),
    "source": "ai_generated",
    "policy_rule_id": POLICY_RULE_ID_B,
    "prompt_template_version": 1,
    "created_at": _NOW - timedelta(hours=1),
    "expires_at": _NOW + timedelta(seconds=5),
}

CACHE_ENTRY_EXPIRED: dict[str, Any] = {
    "id": CACHE_ENTRY_EXPIRED_ID,
    "cache_key": CACHE_KEY_NO_RULE,
    "response_text": "Define an SLO for this service.",
    "implementation_guide": "1. Identify key metrics.\n2. Set SLO targets.\n3. Monitor.",
    "confidence_score": Decimal("0.50"),
    "source": "template_fallback",
    "policy_rule_id": None,
    "prompt_template_version": 1,
    "created_at": _NOW - timedelta(hours=2),
    "expires_at": _NOW - timedelta(hours=1),
}


# ---------------------------------------------------------------------------
# Factory helper
# ---------------------------------------------------------------------------

def make_cache_entry(
    *,
    id: uuid.UUID = CACHE_ENTRY_FRESH_ID,
    cache_key: str = CACHE_KEY_CRITICAL_SECURITY,
    response_text: str = "Remediation guidance text.",
    implementation_guide: str = "Step-by-step implementation guide.",
    confidence_score: Decimal = Decimal("0.80"),
    source: str = "ai_generated",
    policy_rule_id: uuid.UUID | None = POLICY_RULE_ID_A,
    prompt_template_version: int = 1,
    ttl_seconds: int = 3600,
) -> dict[str, Any]:
    now = datetime.now(tz=timezone.utc)
    return {
        "id": id,
        "cache_key": cache_key,
        "response_text": response_text,
        "implementation_guide": implementation_guide,
        "confidence_score": confidence_score,
        "source": source,
        "policy_rule_id": policy_rule_id,
        "prompt_template_version": prompt_template_version,
        "created_at": now,
        "expires_at": now + timedelta(seconds=ttl_seconds),
    }
