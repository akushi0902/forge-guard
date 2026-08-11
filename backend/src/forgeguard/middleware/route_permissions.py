"""Route-permission mapping configuration for RBAC middleware (WO-027).

This module defines the authoritative mapping of every ForgeGuard API endpoint
to its required permission(s).  The RBACMiddleware reads this configuration at
startup and enforces it on every request.

Deny-by-default:
    Any endpoint that is NOT listed here (and is not a public path) will be
    automatically denied with HTTP 403.  This means every new endpoint MUST be
    added to ROUTE_PERMISSION_MAP before it becomes accessible.

Adding a new endpoint:
    1. Choose the applicable :class:`~forgeguard.core.permissions.Permissions` slug.
    2. Add a :class:`RoutePermission` entry to :data:`ROUTE_PERMISSION_MAP`.
    3. Use ``*`` as the method to match any HTTP method, or specify the exact
       method (``GET``, ``POST``, etc.).
    4. Use ``*`` in path patterns to match a single path segment (e.g. a UUID).
       Use ``**`` to match multiple segments.

Pattern examples:
    ``/api/v1/services``         — exact match
    ``/api/v1/services/*``       — one dynamic segment (service ID)
    ``/api/v1/admin/rbac/**``    — any sub-path under /api/v1/admin/rbac/
    ``/api/v1/releases/*/approve`` — specific sub-action on a resource
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from forgeguard.core.permissions import Permissions


# ---------------------------------------------------------------------------
# RoutePermission dataclass
# ---------------------------------------------------------------------------

def _compile_pattern(pattern: str) -> re.Pattern[str]:
    """Compile a wildcard path pattern to a compiled regex.

    Wildcards:
        ``*``  — matches exactly one path segment (no slashes): ``[^/]+``
        ``**`` — matches one or more characters including slashes: ``.+``

    The pattern is anchored at both ends (``^...$``).
    """
    # Split on ** first so single * inside each chunk is handled separately.
    double_star_parts = pattern.split("**")
    processed: list[str] = []
    for part in double_star_parts:
        # re.escape converts * → \* as well as escaping other special chars.
        escaped = re.escape(part)
        # Replace the escaped single wildcard with a non-slash segment matcher.
        replaced = escaped.replace(r"\*", "[^/]+")
        processed.append(replaced)
    regex_str = ".+".join(processed)
    return re.compile(f"^{regex_str}$")


@dataclass
class RoutePermission:
    """Maps a (method, path_pattern) pair to the permission(s) required.

    Args:
        method:       HTTP method string or ``"*"`` to match any method.
                      Comparison is always case-insensitive.
        path_pattern: URL path with optional ``*`` / ``**`` wildcards.
        permissions:  List of permission slugs from
                      :class:`~forgeguard.core.permissions.Permissions`.
                      Must contain at least one entry.
        match_mode:   ``"any"`` — pass if the user holds ANY permission in the list
                      (default / most permissive).  ``"all"`` — pass only if the
                      user holds ALL permissions (use for multi-gated actions).
    """

    method: str
    path_pattern: str
    permissions: list[str]
    match_mode: str = "any"
    # Compiled regex is derived from path_pattern — not an init arg.
    _regex: re.Pattern[str] = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        # Regular (non-frozen) dataclass — direct attribute assignment is fine.
        self._regex = _compile_pattern(self.path_pattern)

    def matches(self, method: str, path: str) -> bool:
        """Return True if this entry matches *method* and *path*."""
        method_match = self.method == "*" or self.method.upper() == method.upper()
        return method_match and bool(self._regex.match(path))

    def has_permission(self, user_role: str) -> bool:
        """Return True if *user_role* satisfies the permission requirement."""
        from forgeguard.core.permissions import has_permission  # noqa: PLC0415

        if self.match_mode == "all":
            return all(has_permission(user_role, p) for p in self.permissions)
        return any(has_permission(user_role, p) for p in self.permissions)


# ---------------------------------------------------------------------------
# ROUTE_PERMISSION_MAP
#
# Order matters: the middleware uses the FIRST matching entry.  Place more
# specific patterns before broader wildcards.
# ---------------------------------------------------------------------------

ROUTE_PERMISSION_MAP: list[RoutePermission] = [
    # ------------------------------------------------------------------
    # Services — broad read access, admin-only writes
    # ------------------------------------------------------------------
    RoutePermission("GET",    "/api/v1/services",     [Permissions.SERVICE_VIEW]),
    RoutePermission("GET",    "/api/v1/services/*",   [Permissions.SERVICE_VIEW]),
    RoutePermission("POST",   "/api/v1/services",     [Permissions.POLICY_MANAGE]),
    RoutePermission("PATCH",  "/api/v1/services/*",   [Permissions.POLICY_MANAGE]),
    RoutePermission("DELETE", "/api/v1/services/*",   [Permissions.POLICY_MANAGE]),

    # ------------------------------------------------------------------
    # Assessments
    # ------------------------------------------------------------------
    RoutePermission("GET",  "/api/v1/assessments",          [Permissions.SERVICE_VIEW]),
    RoutePermission("GET",  "/api/v1/assessments/*",        [Permissions.SERVICE_VIEW]),
    RoutePermission("POST", "/api/v1/assessments/*/request", [Permissions.ASSESSMENT_REQUEST]),

    # ------------------------------------------------------------------
    # Releases
    # ------------------------------------------------------------------
    RoutePermission("GET",  "/api/v1/releases",              [Permissions.SERVICE_VIEW]),
    RoutePermission("GET",  "/api/v1/releases/*",            [Permissions.SERVICE_VIEW]),
    # Exact path /assess must appear before wildcard patterns (first-match wins).
    RoutePermission("POST", "/api/v1/releases/assess",       [Permissions.ASSESSMENT_REQUEST]),
    RoutePermission("POST", "/api/v1/releases/*/approve",    [Permissions.RELEASE_APPROVE]),
    RoutePermission("POST", "/api/v1/releases/*/block",      [Permissions.RELEASE_BLOCK]),

    # ------------------------------------------------------------------
    # Exception requests and approvals
    # ------------------------------------------------------------------
    RoutePermission("GET",  "/api/v1/exceptions",          [Permissions.SERVICE_VIEW]),
    RoutePermission("GET",  "/api/v1/exceptions/*",        [Permissions.SERVICE_VIEW]),
    RoutePermission("POST", "/api/v1/exceptions",          [Permissions.EXCEPTION_REQUEST]),
    RoutePermission("POST", "/api/v1/exceptions/*/approve", [Permissions.EXCEPTION_APPROVE]),

    # ------------------------------------------------------------------
    # Admin — RBAC management
    # ------------------------------------------------------------------
    RoutePermission("*", "/api/v1/admin/rbac",   [Permissions.RBAC_MANAGE]),
    RoutePermission("*", "/api/v1/admin/rbac/*", [Permissions.RBAC_MANAGE]),

    # ------------------------------------------------------------------
    # Admin — Policy / prompt template management
    # ------------------------------------------------------------------
    RoutePermission("*", "/api/v1/admin/policies",              [Permissions.POLICY_MANAGE]),
    RoutePermission("*", "/api/v1/admin/policies/*",            [Permissions.POLICY_MANAGE]),
    RoutePermission("*", "/api/v1/admin/prompt-templates",      [Permissions.POLICY_MANAGE]),
    RoutePermission("*", "/api/v1/admin/prompt-templates/*",    [Permissions.POLICY_MANAGE]),

    # ------------------------------------------------------------------
    # Platform health monitoring
    # ------------------------------------------------------------------
    RoutePermission("GET", "/api/v1/platform/health",  [Permissions.HEALTH_MONITOR]),
    RoutePermission("GET", "/api/v1/health/platform",  [Permissions.HEALTH_MONITOR]),

    # ------------------------------------------------------------------
    # Trends / analytics
    # ------------------------------------------------------------------
    RoutePermission("GET", "/api/v1/trends",   [Permissions.TRENDS_VIEW]),
    RoutePermission("GET", "/api/v1/trends/*", [Permissions.TRENDS_VIEW]),

    # ------------------------------------------------------------------
    # User profile — self-serve (all authenticated roles)
    # ------------------------------------------------------------------
    RoutePermission("GET",   "/api/v1/users/me",   [Permissions.SERVICE_VIEW]),
    RoutePermission("PATCH", "/api/v1/users/me",   [Permissions.SERVICE_VIEW]),

    # ------------------------------------------------------------------
    # GDPR data subject rights (policy manage = admin only)
    # ------------------------------------------------------------------
    RoutePermission("*", "/api/v1/data-subject",    [Permissions.POLICY_MANAGE]),
    RoutePermission("*", "/api/v1/data-subject/**", [Permissions.POLICY_MANAGE]),

    # ------------------------------------------------------------------
    # Demo / mock endpoints (any authenticated user)
    # ------------------------------------------------------------------
    RoutePermission("*", "/api/v1/demo/**", [Permissions.SERVICE_VIEW]),
]
