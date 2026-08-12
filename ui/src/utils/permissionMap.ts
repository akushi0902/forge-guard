/**
 * Client-side RBAC permission map for ForgeGuard.
 *
 * Maps each of the 10 RBAC permission slugs (as returned by the backend) to
 * a human-readable label, a description, and the list of roles that hold it.
 *
 * NOTE: This map is for display purposes only. Authoritative access control
 * is always server-side. Never rely solely on this map for security decisions.
 *
 * Keep in sync with the backend RBAC permission matrix (WO-086 contract).
 */

import type { PermissionDeniedResponse } from '@/types/api-errors';

export interface PermissionInfo {
  /** Short display label, e.g. "Approve Release". */
  humanLabel: string;
  /** One-sentence description of what the permission grants. */
  description: string;
  /** Role names that hold this permission. */
  roles: string[];
}

/**
 * All 10 RBAC permissions defined in the ForgeGuard architecture spec.
 */
export const PERMISSION_MAP: Record<string, PermissionInfo> = {
  'service.view': {
    humanLabel: 'View Services',
    description: 'View registered services and their engineering health scores.',
    roles: ['Developer', 'Tech Lead', 'Engineering Manager', 'Platform Admin', 'Operator'],
  },
  'assessment.request': {
    humanLabel: 'Request Assessment',
    description: 'Submit a release readiness assessment request for a service.',
    roles: ['Developer', 'Tech Lead'],
  },
  'release.approve': {
    humanLabel: 'Approve Release',
    description: 'Approve a release for deployment based on assessment results.',
    roles: ['Tech Lead', 'Platform Admin'],
  },
  'release.block': {
    humanLabel: 'Block Release',
    description: 'Block a release from proceeding due to policy violations.',
    roles: ['Tech Lead', 'Platform Admin', 'Security Reviewer'],
  },
  'exception.request': {
    humanLabel: 'Request Exception',
    description: 'Request a policy exception to bypass a failing rule temporarily.',
    roles: ['Developer', 'Tech Lead'],
  },
  'exception.approve': {
    humanLabel: 'Approve Exception',
    description: 'Approve or reject a submitted policy exception request.',
    roles: ['Engineering Manager', 'Platform Admin'],
  },
  'policy.manage': {
    humanLabel: 'Manage Policies',
    description: 'Create, update, and delete governance policy rules.',
    roles: ['Platform Admin'],
  },
  'rbac.manage': {
    humanLabel: 'Manage Access Control',
    description: 'Assign and revoke user roles and permissions across the platform.',
    roles: ['Platform Admin'],
  },
  'health.monitor': {
    humanLabel: 'Monitor Platform Health',
    description: 'View platform health metrics, service status, and operational logs.',
    roles: ['Operator', 'Platform Admin'],
  },
  'trends.view': {
    humanLabel: 'View Trends',
    description: 'Access engineering analytics dashboards and historical trend data.',
    roles: ['Engineering Manager', 'Platform Admin'],
  },
};

/** Fallback message when permission details are unavailable. */
export const FALLBACK_PERMISSION_MESSAGE =
  'You do not have permission to perform this action. Contact your Platform Admin for access.';

// ---------------------------------------------------------------------------
// Pure formatting helper (usable outside React — e.g. in interceptors)
// ---------------------------------------------------------------------------

export interface FormattedPermissionError {
  permissionLabel: string;
  permissionDescription: string;
  /** Comma-separated role list, e.g. "Tech Lead, Platform Admin". */
  roleList: string;
  actionGuidance: string;
}

/**
 * Convert a PermissionDeniedResponse into display-ready strings.
 *
 * Falls back gracefully when the permission is not in PERMISSION_MAP.
 */
export function formatPermissionError(
  error: PermissionDeniedResponse,
): FormattedPermissionError {
  const info = PERMISSION_MAP[error.permission];

  const permissionLabel = info?.humanLabel ?? error.permission;
  const permissionDescription =
    info?.description ??
    `This action requires the '${error.permission}' permission.`;

  const requiredRoles: string[] = Array.isArray(error.required_role)
    ? error.required_role
    : [error.required_role];

  // Prefer the canonical roles list from the map; fall back to what the server sent.
  const roleList = info?.roles?.join(', ') ?? requiredRoles.join(', ');

  const actionGuidance = error.action?.trim() || FALLBACK_PERMISSION_MESSAGE;

  return { permissionLabel, permissionDescription, roleList, actionGuidance };
}
