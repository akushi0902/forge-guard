/**
 * Role-permission matrix for ForgeGuard RBAC (WO-080).
 *
 * Matches the architecture specification and the backend RBAC middleware.
 * For display purposes only — server-side RBAC is always authoritative.
 * Keep in sync with backend/src/forgeguard/middleware/rbac.py.
 */

import { Role } from '@/types';

/** All 10 permission slugs defined in the ForgeGuard architecture. */
export const ALL_PERMISSIONS = [
  'service.view',
  'assessment.request',
  'release.approve',
  'release.block',
  'exception.request',
  'exception.approve',
  'policy.manage',
  'rbac.manage',
  'health.monitor',
  'trends.view',
] as const;

export type Permission = (typeof ALL_PERMISSIONS)[number];

export const PERMISSION_LABELS: Record<Permission, string> = {
  'service.view': 'View Services',
  'assessment.request': 'Request Assessment',
  'release.approve': 'Approve Release',
  'release.block': 'Block Release',
  'exception.request': 'Request Exception',
  'exception.approve': 'Approve Exception',
  'policy.manage': 'Manage Policies',
  'rbac.manage': 'Manage Access Control',
  'health.monitor': 'Monitor Platform Health',
  'trends.view': 'View Trends',
};

/** The six ForgeGuard roles in display order. */
export const ALL_ROLES = [
  Role.Developer,
  Role.TechLead,
  Role.SecurityReviewer,
  Role.PlatformAdmin,
  Role.EngineeringManager,
  Role.Operator,
] as const;

export const ROLE_LABELS: Record<Role, string> = {
  [Role.Developer]: 'Developer',
  [Role.TechLead]: 'Tech Lead',
  [Role.SecurityReviewer]: 'Security Reviewer',
  [Role.PlatformAdmin]: 'Platform Admin',
  [Role.EngineeringManager]: 'Eng Manager',
  [Role.Operator]: 'Operator',
};

/**
 * Complete role-permission matrix.
 * True = the role has the permission.
 */
export const ROLE_PERMISSION_MATRIX: Record<Role, Record<Permission, boolean>> = {
  [Role.Developer]: {
    'service.view': true,
    'assessment.request': true,
    'release.approve': false,
    'release.block': false,
    'exception.request': true,
    'exception.approve': false,
    'policy.manage': false,
    'rbac.manage': false,
    'health.monitor': false,
    'trends.view': false,
  },
  [Role.TechLead]: {
    'service.view': true,
    'assessment.request': true,
    'release.approve': true,
    'release.block': true,
    'exception.request': true,
    'exception.approve': false,
    'policy.manage': false,
    'rbac.manage': false,
    'health.monitor': false,
    'trends.view': false,
  },
  [Role.SecurityReviewer]: {
    'service.view': false,
    'assessment.request': false,
    'release.approve': false,
    'release.block': true,
    'exception.request': false,
    'exception.approve': false,
    'policy.manage': false,
    'rbac.manage': false,
    'health.monitor': false,
    'trends.view': false,
  },
  [Role.PlatformAdmin]: {
    'service.view': true,
    'assessment.request': false,
    'release.approve': true,
    'release.block': true,
    'exception.request': false,
    'exception.approve': true,
    'policy.manage': true,
    'rbac.manage': true,
    'health.monitor': true,
    'trends.view': true,
  },
  [Role.EngineeringManager]: {
    'service.view': true,
    'assessment.request': false,
    'release.approve': false,
    'release.block': false,
    'exception.request': false,
    'exception.approve': true,
    'policy.manage': false,
    'rbac.manage': false,
    'health.monitor': false,
    'trends.view': true,
  },
  [Role.Operator]: {
    'service.view': true,
    'assessment.request': false,
    'release.approve': false,
    'release.block': false,
    'exception.request': false,
    'exception.approve': false,
    'policy.manage': false,
    'rbac.manage': false,
    'health.monitor': true,
    'trends.view': false,
  },
};
