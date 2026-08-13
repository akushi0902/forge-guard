"""Demo service fixtures."""

from __future__ import annotations

import json

SERVICE_PAYMENT_ID     = "d0000000-0000-0000-0000-000000000001"
SERVICE_API_GATEWAY_ID = "d0000000-0000-0000-0000-000000000002"
SERVICE_AUTH_ID        = "d0000000-0000-0000-0000-000000000003"

SERVICES = [
    {
        "id": SERVICE_PAYMENT_ID,
        "name": "ForgeGuard Payment Service",
        "description": "Handles payment processing, billing, and subscription management for ForgeGuard platform customers.",
        "repository_url": "https://git.forgeguard.demo/platform/payment-service",
        "owner_team": "Payments Platform Team",
        "metadata": json.dumps({
            "language": "Python",
            "framework": "FastAPI",
            "team_size": 6,
            "tier": "critical",
            "pci_scope": True,
        }),
        "is_demo": True,
    },
    {
        "id": SERVICE_API_GATEWAY_ID,
        "name": "ForgeGuard API Gateway",
        "description": "Central API gateway routing requests to internal services with authentication and rate limiting.",
        "repository_url": "https://git.forgeguard.demo/platform/api-gateway",
        "owner_team": "Platform Infrastructure Team",
        "metadata": json.dumps({
            "language": "Go",
            "framework": "Envoy",
            "team_size": 4,
            "tier": "critical",
        }),
        "is_demo": True,
    },
    {
        "id": SERVICE_AUTH_ID,
        "name": "ForgeGuard Auth Service",
        "description": "Identity and access management service providing JWT authentication and RBAC enforcement.",
        "repository_url": "https://git.forgeguard.demo/platform/auth-service",
        "owner_team": "Security Platform Team",
        "metadata": json.dumps({
            "language": "Python",
            "framework": "FastAPI",
            "team_size": 3,
            "tier": "critical",
        }),
        "is_demo": True,
    },
]
