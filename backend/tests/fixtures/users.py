"""Test fixtures — static user data for each of the six ForgeGuard roles.

These factory functions produce plain-dict payloads that can be posted to
the registration endpoint or used in unit tests without any database.

All passwords satisfy the ForgeGuard password policy:
  - ≥12 characters
  - uppercase letter
  - lowercase letter
  - digit
  - special character
"""

from __future__ import annotations

from forgeguard.core.permissions import UserRole


def make_register_payload(
    *,
    email: str = "user@example.com",
    name: str = "Test User",
    password: str = "TestP@ssw0rd1!",
    role: str = "developer",
) -> dict:
    """Return a valid registration request body as a dict."""
    return {
        "email": email,
        "name": name,
        "password": password,
        "role": role,
    }


# ---------------------------------------------------------------------------
# One canonical payload per role
# ---------------------------------------------------------------------------

def developer_payload() -> dict:
    return make_register_payload(
        email="dev@example.com",
        name="Dev User",
        password="DevP@ssw0rd12!",
        role=UserRole.developer.value,
    )


def tech_lead_payload() -> dict:
    return make_register_payload(
        email="tl@example.com",
        name="Tech Lead",
        password="TechL3@d!Passw0rd",
        role=UserRole.tech_lead.value,
    )


def security_reviewer_payload() -> dict:
    return make_register_payload(
        email="sr@example.com",
        name="Security Reviewer",
        password="SecR3viewer!Pass1",
        role=UserRole.security_reviewer.value,
    )


def platform_admin_payload() -> dict:
    return make_register_payload(
        email="admin@example.com",
        name="Platform Admin",
        password="PlatformAdm1n!Pass",
        role=UserRole.platform_admin.value,
    )


def engineering_manager_payload() -> dict:
    return make_register_payload(
        email="em@example.com",
        name="Engineering Manager",
        password="EngM@nager1!Passw",
        role=UserRole.engineering_manager.value,
    )


def operator_payload() -> dict:
    return make_register_payload(
        email="operator@example.com",
        name="Operator User",
        password="Oper@t0r!Passw0rd",
        role=UserRole.operator.value,
    )


ALL_ROLE_PAYLOADS: list[dict] = [
    developer_payload(),
    tech_lead_payload(),
    security_reviewer_payload(),
    platform_admin_payload(),
    engineering_manager_payload(),
    operator_payload(),
]
