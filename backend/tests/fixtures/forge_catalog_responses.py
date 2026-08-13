"""Forge Catalog API mock response fixtures (WO-089).

Covers all relevant status codes and scenarios:
  201 Created   — successful entity creation
  200 OK        — successful entity update / fetch
  400 Bad Request
  401 Unauthorized
  404 Not Found
  409 Conflict  — entity already exists
  500 Server Error
  Timeout       — connection timeout scenario
"""

from __future__ import annotations

import uuid

# ---------------------------------------------------------------------------
# Sample entity IDs
# ---------------------------------------------------------------------------

CATALOG_ENTITY_ID = uuid.UUID("aaaabbbb-cccc-dddd-eeee-ffff00001111")
SERVICE_ID = uuid.UUID("11112222-3333-4444-5555-666677778888")

# ---------------------------------------------------------------------------
# Success responses
# ---------------------------------------------------------------------------

CATALOG_CREATE_201 = {
    "id": str(CATALOG_ENTITY_ID),
    "name": "payment-service",
    "type": "service",
    "description": "Payment processing microservice",
    "owner": "payments",
    "metadata": {
        "language": "python",
        "framework": "fastapi",
        "team_size": 5,
    },
    "created_at": "2026-08-12T10:00:00Z",
    "updated_at": "2026-08-12T10:00:00Z",
}

CATALOG_UPDATE_200 = {
    "id": str(CATALOG_ENTITY_ID),
    "name": "payment-service",
    "type": "service",
    "description": "Payment processing microservice (updated)",
    "owner": "payments",
    "metadata": {
        "language": "python",
        "framework": "fastapi",
        "team_size": 6,
    },
    "created_at": "2026-08-12T10:00:00Z",
    "updated_at": "2026-08-12T11:00:00Z",
}

CATALOG_GET_200 = {
    "id": str(CATALOG_ENTITY_ID),
    "name": "payment-service",
    "type": "service",
    "description": "Payment processing microservice",
    "owner": "payments",
    "metadata": {},
    "created_at": "2026-08-12T10:00:00Z",
    "updated_at": "2026-08-12T10:00:00Z",
}

CATALOG_LIST_200 = {
    "items": [CATALOG_GET_200],
    "total": 1,
    "next_cursor": None,
}

CATALOG_LIST_EMPTY_200 = {
    "items": [],
    "total": 0,
    "next_cursor": None,
}

# ---------------------------------------------------------------------------
# Error responses
# ---------------------------------------------------------------------------

CATALOG_400_BAD_REQUEST = {
    "error": "bad_request",
    "message": "Missing required field: name",
    "status": 400,
}

CATALOG_401_UNAUTHORIZED = {
    "error": "unauthorized",
    "message": "Invalid or missing API key",
    "status": 401,
}

CATALOG_404_NOT_FOUND = {
    "error": "not_found",
    "message": "Entity not found",
    "status": 404,
}

CATALOG_409_CONFLICT = {
    "error": "conflict",
    "message": "Entity with this name already exists",
    "status": 409,
}

CATALOG_500_SERVER_ERROR = {
    "error": "internal_server_error",
    "message": "An unexpected error occurred",
    "status": 500,
}

# ---------------------------------------------------------------------------
# Service DB rows (simulated asyncpg fetchrow results)
# ---------------------------------------------------------------------------

SERVICE_ROW_PENDING = {
    "id": SERVICE_ID,
    "name": "payment-service",
    "description": "Payment processing microservice",
    "repository_url": "https://github.com/example/payment-service",
    "owner_team": "payments",
    "metadata": {},
    "forge_catalog_id": None,
    "forge_sync_status": "pending",
    "last_synced_at": None,
    "is_demo": False,
    "deleted_at": None,
    "created_at": "2026-08-12T10:00:00Z",
    "updated_at": "2026-08-12T10:00:00Z",
}

SERVICE_ROW_SYNCED = {
    **SERVICE_ROW_PENDING,
    "forge_catalog_id": CATALOG_ENTITY_ID,
    "forge_sync_status": "synced",
    "last_synced_at": "2026-08-12T10:30:00Z",
}

SERVICE_ROW_FAILED = {
    **SERVICE_ROW_PENDING,
    "forge_catalog_id": None,
    "forge_sync_status": "failed",
    "last_synced_at": None,
}
