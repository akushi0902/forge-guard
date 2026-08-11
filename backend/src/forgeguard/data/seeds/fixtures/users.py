"""Demo user, role, permission, and RBAC matrix fixtures.

All passwords are "ForgeGuard2025!" hashed with bcrypt cost-12.
The hash is computed once at import time so repeated module loads
do not recompute (the runtime cost of bcrypt rounds=12 is ~250 ms).
"""

from __future__ import annotations

import bcrypt

# ---------------------------------------------------------------------------
# Password hash — computed ONCE at import time
# ---------------------------------------------------------------------------
_DEMO_PASSWORD = b"ForgeGuard2025!"
DEMO_PASSWORD_HASH: str = bcrypt.hashpw(_DEMO_PASSWORD, bcrypt.gensalt(rounds=12)).decode()

# ---------------------------------------------------------------------------
# Fixed UUIDs — stable across runs for idempotent ON CONFLICT DO NOTHING
# ---------------------------------------------------------------------------

# Users
USER_DEVELOPER_ID          = "a0000000-0000-0000-0000-000000000001"
USER_TECHLEAD_ID           = "a0000000-0000-0000-0000-000000000002"
USER_SECURITY_ID           = "a0000000-0000-0000-0000-000000000003"
USER_ADMIN_ID              = "a0000000-0000-0000-0000-000000000004"
USER_MANAGER_ID            = "a0000000-0000-0000-0000-000000000005"
USER_OPERATOR_ID           = "a0000000-0000-0000-0000-000000000006"

# Roles
ROLE_DEVELOPER_ID          = "b0000000-0000-0000-0000-000000000001"
ROLE_TECHLEAD_ID           = "b0000000-0000-0000-0000-000000000002"
ROLE_SECURITY_ID           = "b0000000-0000-0000-0000-000000000003"
ROLE_ADMIN_ID              = "b0000000-0000-0000-0000-000000000004"
ROLE_MANAGER_ID            = "b0000000-0000-0000-0000-000000000005"
ROLE_OPERATOR_ID           = "b0000000-0000-0000-0000-000000000006"

# Permissions
PERM_ASSESSMENT_VIEW_ID    = "c0000000-0000-0000-0000-000000000001"
PERM_ASSESSMENT_CREATE_ID  = "c0000000-0000-0000-0000-000000000002"
PERM_POLICY_VIEW_ID        = "c0000000-0000-0000-0000-000000000003"
PERM_POLICY_MANAGE_ID      = "c0000000-0000-0000-0000-000000000004"
PERM_RELEASE_VIEW_ID       = "c0000000-0000-0000-0000-000000000005"
PERM_RELEASE_APPROVE_ID    = "c0000000-0000-0000-0000-000000000006"
PERM_FINDING_VIEW_ID       = "c0000000-0000-0000-0000-000000000007"
PERM_EXCEPTION_REQUEST_ID  = "c0000000-0000-0000-0000-000000000008"
PERM_EXCEPTION_APPROVE_ID  = "c0000000-0000-0000-0000-000000000009"
PERM_ADMIN_MANAGE_ID       = "c0000000-0000-0000-0000-000000000010"

# ---------------------------------------------------------------------------
# Fixture data
# ---------------------------------------------------------------------------

ROLES = [
    {"id": ROLE_DEVELOPER_ID,   "name": "developer",           "description": "Engineering team member with read access to governance results"},
    {"id": ROLE_TECHLEAD_ID,    "name": "tech_lead",           "description": "Technical lead who can trigger assessments and approve releases"},
    {"id": ROLE_SECURITY_ID,    "name": "security_reviewer",   "description": "Security specialist who approves security exceptions and blocks releases"},
    {"id": ROLE_ADMIN_ID,       "name": "platform_admin",      "description": "Platform administrator with full system access"},
    {"id": ROLE_MANAGER_ID,     "name": "engineering_manager", "description": "Engineering manager with cross-team visibility and reporting access"},
    {"id": ROLE_OPERATOR_ID,    "name": "operator",            "description": "Platform operator responsible for infrastructure and deployment health"},
]

PERMISSIONS = [
    {"id": PERM_ASSESSMENT_VIEW_ID,   "name": "assessment.view",    "description": "View assessment results and scores"},
    {"id": PERM_ASSESSMENT_CREATE_ID, "name": "assessment.create",  "description": "Trigger new assessments"},
    {"id": PERM_POLICY_VIEW_ID,       "name": "policy.view",        "description": "View policies and rules"},
    {"id": PERM_POLICY_MANAGE_ID,     "name": "policy.manage",      "description": "Create, update, and deactivate policies"},
    {"id": PERM_RELEASE_VIEW_ID,      "name": "release.view",       "description": "View release assessments and decisions"},
    {"id": PERM_RELEASE_APPROVE_ID,   "name": "release.approve",    "description": "Approve or block releases"},
    {"id": PERM_FINDING_VIEW_ID,      "name": "finding.view",       "description": "View governance findings"},
    {"id": PERM_EXCEPTION_REQUEST_ID, "name": "exception.request",  "description": "Request a finding exception"},
    {"id": PERM_EXCEPTION_APPROVE_ID, "name": "exception.approve",  "description": "Approve or deny finding exceptions"},
    {"id": PERM_ADMIN_MANAGE_ID,      "name": "admin.manage",       "description": "Full platform administration"},
]

# (role_id, permission_id) pairs
ROLE_PERMISSIONS = [
    # developer: view only
    (ROLE_DEVELOPER_ID, PERM_ASSESSMENT_VIEW_ID),
    (ROLE_DEVELOPER_ID, PERM_POLICY_VIEW_ID),
    (ROLE_DEVELOPER_ID, PERM_RELEASE_VIEW_ID),
    (ROLE_DEVELOPER_ID, PERM_FINDING_VIEW_ID),
    (ROLE_DEVELOPER_ID, PERM_EXCEPTION_REQUEST_ID),
    # tech_lead: views + can trigger assessments + approve releases + request exceptions
    (ROLE_TECHLEAD_ID, PERM_ASSESSMENT_VIEW_ID),
    (ROLE_TECHLEAD_ID, PERM_ASSESSMENT_CREATE_ID),
    (ROLE_TECHLEAD_ID, PERM_POLICY_VIEW_ID),
    (ROLE_TECHLEAD_ID, PERM_RELEASE_VIEW_ID),
    (ROLE_TECHLEAD_ID, PERM_RELEASE_APPROVE_ID),
    (ROLE_TECHLEAD_ID, PERM_FINDING_VIEW_ID),
    (ROLE_TECHLEAD_ID, PERM_EXCEPTION_REQUEST_ID),
    # security_reviewer: all views + exception.approve + release.approve
    (ROLE_SECURITY_ID, PERM_ASSESSMENT_VIEW_ID),
    (ROLE_SECURITY_ID, PERM_POLICY_VIEW_ID),
    (ROLE_SECURITY_ID, PERM_RELEASE_VIEW_ID),
    (ROLE_SECURITY_ID, PERM_RELEASE_APPROVE_ID),
    (ROLE_SECURITY_ID, PERM_FINDING_VIEW_ID),
    (ROLE_SECURITY_ID, PERM_EXCEPTION_REQUEST_ID),
    (ROLE_SECURITY_ID, PERM_EXCEPTION_APPROVE_ID),
    # platform_admin: all
    (ROLE_ADMIN_ID, PERM_ASSESSMENT_VIEW_ID),
    (ROLE_ADMIN_ID, PERM_ASSESSMENT_CREATE_ID),
    (ROLE_ADMIN_ID, PERM_POLICY_VIEW_ID),
    (ROLE_ADMIN_ID, PERM_POLICY_MANAGE_ID),
    (ROLE_ADMIN_ID, PERM_RELEASE_VIEW_ID),
    (ROLE_ADMIN_ID, PERM_RELEASE_APPROVE_ID),
    (ROLE_ADMIN_ID, PERM_FINDING_VIEW_ID),
    (ROLE_ADMIN_ID, PERM_EXCEPTION_REQUEST_ID),
    (ROLE_ADMIN_ID, PERM_EXCEPTION_APPROVE_ID),
    (ROLE_ADMIN_ID, PERM_ADMIN_MANAGE_ID),
    # engineering_manager: all views + assessment.create
    (ROLE_MANAGER_ID, PERM_ASSESSMENT_VIEW_ID),
    (ROLE_MANAGER_ID, PERM_ASSESSMENT_CREATE_ID),
    (ROLE_MANAGER_ID, PERM_POLICY_VIEW_ID),
    (ROLE_MANAGER_ID, PERM_RELEASE_VIEW_ID),
    (ROLE_MANAGER_ID, PERM_FINDING_VIEW_ID),
    (ROLE_MANAGER_ID, PERM_EXCEPTION_REQUEST_ID),
    # operator: all views + assessment.create
    (ROLE_OPERATOR_ID, PERM_ASSESSMENT_VIEW_ID),
    (ROLE_OPERATOR_ID, PERM_ASSESSMENT_CREATE_ID),
    (ROLE_OPERATOR_ID, PERM_POLICY_VIEW_ID),
    (ROLE_OPERATOR_ID, PERM_RELEASE_VIEW_ID),
    (ROLE_OPERATOR_ID, PERM_FINDING_VIEW_ID),
]


def get_users() -> list[dict]:
    """Return user fixtures with the runtime-computed bcrypt hash."""
    return [
        {
            "id": USER_DEVELOPER_ID,
            "email": "developer@forgeguard.demo",
            "password_hash": DEMO_PASSWORD_HASH,
            "role": "developer",
            "is_active": True,
            "failed_login_attempts": 0,
        },
        {
            "id": USER_TECHLEAD_ID,
            "email": "techlead@forgeguard.demo",
            "password_hash": DEMO_PASSWORD_HASH,
            "role": "tech_lead",
            "is_active": True,
            "failed_login_attempts": 0,
        },
        {
            "id": USER_SECURITY_ID,
            "email": "security@forgeguard.demo",
            "password_hash": DEMO_PASSWORD_HASH,
            "role": "security_reviewer",
            "is_active": True,
            "failed_login_attempts": 0,
        },
        {
            "id": USER_ADMIN_ID,
            "email": "admin@forgeguard.demo",
            "password_hash": DEMO_PASSWORD_HASH,
            "role": "platform_admin",
            "is_active": True,
            "failed_login_attempts": 0,
        },
        {
            "id": USER_MANAGER_ID,
            "email": "manager@forgeguard.demo",
            "password_hash": DEMO_PASSWORD_HASH,
            "role": "engineering_manager",
            "is_active": True,
            "failed_login_attempts": 0,
        },
        {
            "id": USER_OPERATOR_ID,
            "email": "operator@forgeguard.demo",
            "password_hash": DEMO_PASSWORD_HASH,
            "role": "operator",
            "is_active": True,
            "failed_login_attempts": 0,
        },
    ]
