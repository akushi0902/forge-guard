"""Mock fixtures for Forge Workflow Engine API responses (WO-092).

Used by unit tests (test_forge_workflow.py) and integration tests
(test_workflow_routing.py).
"""
from __future__ import annotations

import uuid

# ---------------------------------------------------------------------------
# Trigger response fixtures
# ---------------------------------------------------------------------------

WORKFLOW_ID = "wf-1234-5678-abcd"

TRIGGER_SUCCESS_RESPONSE = {
    "workflow_id": WORKFLOW_ID,
    "status": "pending",
    "created_at": "2026-08-13T00:00:00Z",
}

TRIGGER_4XX_RESPONSE = {
    "error": "Bad Request",
    "message": "Invalid workflow_type",
}

# 500-level error bodies — status code matters more than body.
TRIGGER_5XX_RESPONSE = {
    "error": "Internal Server Error",
}

# ---------------------------------------------------------------------------
# Status poll response fixtures
# ---------------------------------------------------------------------------

STATUS_PENDING = {
    "id": WORKFLOW_ID,
    "status": "pending",
    "decided_by": None,
    "decided_at": None,
    "comment": None,
}

STATUS_IN_REVIEW = {
    "id": WORKFLOW_ID,
    "status": "in_review",
    "decided_by": None,
    "decided_at": None,
    "comment": None,
}

STATUS_APPROVED = {
    "id": WORKFLOW_ID,
    "status": "approved",
    "decided_by": {
        "id": str(uuid.uuid4()),
        "role": "reviewer",
        "name": "Alice Tech Lead",
    },
    "decided_at": "2026-08-13T01:00:00Z",
    "comment": "Looks good to release.",
}

STATUS_REJECTED = {
    "id": WORKFLOW_ID,
    "status": "rejected",
    "decided_by": {
        "id": str(uuid.uuid4()),
        "role": "reviewer",
        "name": "Bob Tech Lead",
    },
    "decided_at": "2026-08-13T01:30:00Z",
    "comment": "Critical issues must be resolved first.",
}

STATUS_TIMED_OUT = {
    "id": WORKFLOW_ID,
    "status": "timed_out",
    "decided_by": None,
    "decided_at": None,
    "comment": None,
}

STATUS_NOT_FOUND_BODY = {
    "error": "Not Found",
    "message": f"Workflow {WORKFLOW_ID} not found",
}

# ---------------------------------------------------------------------------
# Error scenario fixtures
# ---------------------------------------------------------------------------

# Trigger that times out (httpx.TimeoutException is raised, no body).
TRIGGER_TIMEOUT_DESCRIPTION = "httpx.TimeoutException raised during POST /workflows/trigger"

# Circuit open — CircuitOpenError raised, no HTTP call made.
CIRCUIT_OPEN_DESCRIPTION = "CircuitOpenError raised; decision must route via dashboard_fallback"
