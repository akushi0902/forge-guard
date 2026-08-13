import { Role } from '@/types';
import { type RbacUser, type UsersResponse } from '@/hooks/api/useUsers';

export const RBAC_USERS_FIXTURE: RbacUser[] = [
  {
    id: 'usr-001',
    name: 'Alice Chen',
    email: 'alice@forgeguard.io',
    role: Role.Developer,
    last_role_change: '2026-06-01T09:00:00Z',
    created_at: '2026-01-15T08:00:00Z',
  },
  {
    id: 'usr-002',
    name: 'Bob Martinez',
    email: 'bob.martinez@forgeguard.io',
    role: Role.Developer,
    last_role_change: null,
    created_at: '2026-02-01T10:00:00Z',
  },
  {
    id: 'usr-003',
    name: 'Carol Okafor',
    email: 'carol@forgeguard.io',
    role: Role.TechLead,
    last_role_change: '2026-05-15T14:30:00Z',
    created_at: '2026-01-20T09:00:00Z',
  },
  {
    id: 'usr-004',
    name: 'David Park',
    email: 'david.park@forgeguard.io',
    role: Role.TechLead,
    last_role_change: null,
    created_at: '2026-03-10T11:00:00Z',
  },
  {
    id: 'usr-005',
    name: 'Eve Johnson',
    email: 'eve@forgeguard.io',
    role: Role.SecurityReviewer,
    last_role_change: '2026-04-20T16:00:00Z',
    created_at: '2026-01-25T08:30:00Z',
  },
  {
    id: 'usr-006',
    name: 'Frank Williams',
    email: 'frank.w@forgeguard.io',
    role: Role.EngineeringManager,
    last_role_change: '2026-03-01T10:00:00Z',
    created_at: '2026-01-10T09:00:00Z',
  },
  {
    id: 'usr-007',
    name: 'Grace Liu',
    email: 'grace@forgeguard.io',
    role: Role.Operator,
    last_role_change: null,
    created_at: '2026-02-15T13:00:00Z',
  },
  {
    id: 'usr-008',
    name: 'Henry Schmidt',
    email: 'henry.schmidt@forgeguard.io',
    role: Role.Operator,
    last_role_change: '2026-07-01T09:00:00Z',
    created_at: '2026-03-05T10:00:00Z',
  },
  {
    id: 'usr-009',
    name: 'Isabel Torres',
    email: 'isabel@forgeguard.io',
    role: Role.PlatformAdmin,
    last_role_change: null,
    created_at: '2026-01-05T08:00:00Z',
  },
  {
    id: 'usr-010',
    name: 'James Kim',
    email: 'james.kim@forgeguard.io',
    role: Role.Developer,
    last_role_change: '2026-07-10T11:00:00Z',
    created_at: '2026-04-01T09:00:00Z',
  },
  {
    id: 'usr-011',
    name: 'Karen Patel',
    email: 'karen.p@forgeguard.io',
    role: Role.EngineeringManager,
    last_role_change: null,
    created_at: '2026-02-20T14:00:00Z',
  },
];

// The current Platform Admin (self) — used to test self-change prevention
export const CURRENT_ADMIN_USER = RBAC_USERS_FIXTURE[8]; // Isabel Torres

export const USERS_RESPONSE_FIXTURE: UsersResponse = {
  users: RBAC_USERS_FIXTURE,
  roles: [
    { name: Role.Developer, description: 'Engineers building services', permissions: ['service.view', 'assessment.request', 'exception.request'] },
    { name: Role.TechLead, description: 'Senior engineers and team leads', permissions: ['service.view', 'assessment.request', 'release.approve', 'release.block', 'exception.request'] },
    { name: Role.SecurityReviewer, description: 'Security specialists', permissions: ['release.block'] },
    { name: Role.PlatformAdmin, description: 'Full platform control', permissions: ['service.view', 'release.approve', 'release.block', 'exception.approve', 'policy.manage', 'rbac.manage', 'health.monitor', 'trends.view'] },
    { name: Role.EngineeringManager, description: 'Engineering department managers', permissions: ['service.view', 'exception.approve', 'trends.view'] },
    { name: Role.Operator, description: 'Operations and SRE team', permissions: ['service.view', 'health.monitor'] },
  ],
};
