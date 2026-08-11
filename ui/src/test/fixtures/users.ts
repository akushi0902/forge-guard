/**
 * Canonical user fixtures for all 6 ForgeGuard roles.
 *
 * Used in component tests, MSW handler overrides, and story files.
 * Shapes match the User interface from @/stores/auth-store (login response).
 */

import type { User } from '@/stores/auth-store';
import { Role } from '@/types';

export const developerUser: User = {
  id: 'user-dev-001',
  email: 'alice@forgeguard.io',
  name: 'Alice Developer',
  role: Role.Developer,
  permissions: ['service:read', 'finding:read', 'score:read', 'assessment:read'],
};

export const techLeadUser: User = {
  id: 'user-tl-002',
  email: 'bob@forgeguard.io',
  name: 'Bob TechLead',
  role: Role.TechLead,
  permissions: [
    'service:read',
    'service:write',
    'finding:read',
    'finding:write',
    'score:read',
    'assessment:read',
    'assessment:write',
  ],
};

export const securityReviewerUser: User = {
  id: 'user-sr-003',
  email: 'carol@forgeguard.io',
  name: 'Carol Security',
  role: Role.SecurityReviewer,
  permissions: [
    'service:read',
    'finding:read',
    'finding:write',
    'finding:escalate',
    'score:read',
    'assessment:read',
    'security:review',
  ],
};

export const platformAdminUser: User = {
  id: 'user-pa-004',
  email: 'dave@forgeguard.io',
  name: 'Dave Admin',
  role: Role.PlatformAdmin,
  permissions: [
    'service:read',
    'service:write',
    'service:delete',
    'finding:read',
    'finding:write',
    'score:read',
    'assessment:read',
    'assessment:write',
    'policy:read',
    'policy:write',
    'user:read',
    'user:write',
    'admin:access',
  ],
};

export const engineeringManagerUser: User = {
  id: 'user-em-005',
  email: 'eve@forgeguard.io',
  name: 'Eve Manager',
  role: Role.EngineeringManager,
  permissions: [
    'service:read',
    'finding:read',
    'finding:write',
    'score:read',
    'assessment:read',
    'assessment:approve',
    'report:read',
  ],
};

export const operatorUser: User = {
  id: 'user-op-006',
  email: 'frank@forgeguard.io',
  name: 'Frank Operator',
  role: Role.Operator,
  permissions: [
    'service:read',
    'finding:read',
    'score:read',
    'assessment:read',
    'operations:read',
    'operations:manage',
  ],
};

export const allUsers: User[] = [
  developerUser,
  techLeadUser,
  securityReviewerUser,
  platformAdminUser,
  engineeringManagerUser,
  operatorUser,
];
