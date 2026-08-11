"""Test fixtures for RBAC unit and integration tests (WO-026).

Provides helpers to create mock FastAPI Request objects with a pre-populated
``request.state.user_role``, enabling rapid test setup without HTTP overhead.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from forgeguard.core.permissions import UserRole


def make_request_state(role: str) -> MagicMock:
    """Return a mock ``request.state`` object with ``user_role`` set.

    Args:
        role: A role string from :class:`~forgeguard.core.permissions.UserRole`.

    Returns:
        A ``MagicMock`` with ``.user_role`` attribute set.

    Usage::

        state = make_request_state("developer")
        assert state.user_role == "developer"
    """
    state = MagicMock()
    state.user_role = role
    return state


def make_mock_request(role: str) -> MagicMock:
    """Return a mock FastAPI ``Request`` with ``state.user_role`` set.

    Args:
        role: A role string from :class:`~forgeguard.core.permissions.UserRole`.

    Returns:
        A ``MagicMock`` whose ``.state.user_role`` attribute returns *role*.
    """
    request = MagicMock()
    request.state = make_request_state(role)
    return request


# ---------------------------------------------------------------------------
# One pre-built mock request per role
# ---------------------------------------------------------------------------

def developer_request() -> MagicMock:
    return make_mock_request(UserRole.developer.value)


def tech_lead_request() -> MagicMock:
    return make_mock_request(UserRole.tech_lead.value)


def security_reviewer_request() -> MagicMock:
    return make_mock_request(UserRole.security_reviewer.value)


def platform_admin_request() -> MagicMock:
    return make_mock_request(UserRole.platform_admin.value)


def engineering_manager_request() -> MagicMock:
    return make_mock_request(UserRole.engineering_manager.value)


def operator_request() -> MagicMock:
    return make_mock_request(UserRole.operator.value)


ALL_ROLE_REQUESTS: dict[str, MagicMock] = {
    role.value: make_mock_request(role.value)
    for role in UserRole
}
