/**
 * Frontend permission configuration for ForgeGuard RBAC.
 *
 * Maps permission slugs (as returned by the backend login response) to
 * human-readable labels and to the primary role that grants them. Used
 * by ForbiddenPage to render actionable access-denied messages.
 *
 * NOTE: These are client-side convenience only. Authoritative enforcement
 * is always server-side. Never rely solely on frontend guards for security.
 */

/** Human-readable label for each permission slug. */
export const PERMISSION_LABELS: Record<string, string> = {
  'service:read': 'View Services',
  'service:write': 'Manage Services',
  'service:delete': 'Delete Services',
  'finding:read': 'View Findings',
  'finding:write': 'Manage Findings',
  'finding:escalate': 'Escalate Findings',
  'score:read': 'View Scores',
  'assessment:read': 'View Assessments',
  'assessment:write': 'Request Assessments',
  'assessment:approve': 'Approve Assessments',
  'policy:read': 'View Policies',
  'policy:write': 'Manage Policies',
  'user:read': 'View Users',
  'user:write': 'Manage Users',
  'admin:access': 'Access Admin Panel',
  'security:review': 'Perform Security Reviews',
  'operations:read': 'View Operations',
  'operations:manage': 'Manage Operations',
  'report:read': 'View Reports',
};

/**
 * Maps a permission slug to the primary role that grants it.
 * Used to tell users which role they need to gain access.
 */
export const PERMISSION_TO_ROLE: Record<string, string> = {
  'service:read': 'Developer',
  'service:write': 'Tech Lead',
  'service:delete': 'Platform Admin',
  'finding:read': 'Developer',
  'finding:write': 'Tech Lead',
  'finding:escalate': 'Security Reviewer',
  'score:read': 'Developer',
  'assessment:read': 'Developer',
  'assessment:write': 'Tech Lead',
  'assessment:approve': 'Engineering Manager',
  'policy:read': 'Platform Admin',
  'policy:write': 'Platform Admin',
  'user:read': 'Platform Admin',
  'user:write': 'Platform Admin',
  'admin:access': 'Platform Admin',
  'security:review': 'Security Reviewer',
  'operations:read': 'Operator',
  'operations:manage': 'Operator',
  'report:read': 'Engineering Manager',
};

/**
 * Returns the primary role name that grants a given permission.
 * Falls back to 'Platform Admin' for unknown permissions.
 */
export function getRequiredRoleForPermission(permission: string): string {
  return PERMISSION_TO_ROLE[permission] ?? 'Platform Admin';
}

/**
 * Returns a human-readable label for a permission slug.
 * Falls back to the raw slug if not found.
 */
export function getPermissionLabel(permission: string): string {
  return PERMISSION_LABELS[permission] ?? permission;
}
