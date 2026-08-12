/**
 * Role-based navigation configuration for ForgeGuard.
 *
 * Each NavConfigItem defines a navigation entry with its icon name, label,
 * path, required permission, and optional badge count.
 *
 * Permission filtering: the Sidebar filters items by checking whether the
 * authenticated user's permissions array includes item.requiredPermission.
 * Items without requiredPermission are always shown to authenticated users.
 */

export interface NavConfigItem {
  /** Tabler icon component name (resolved to ReactNode in the route shell). */
  iconName: string;
  label: string;
  path: string;
  /** If set, the item is only shown to users whose permissions include this slug. */
  requiredPermission?: string;
  /** Optional badge count (wired to API data in later stories). */
  badgeCount?: number;
}

// ---------------------------------------------------------------------------
// Developer (7 items)
// ---------------------------------------------------------------------------

export const developerNav: NavConfigItem[] = [
  { iconName: 'dashboard', label: 'Dashboard',    path: '/dashboard',    requiredPermission: 'service:read' },
  { iconName: 'health',    label: 'Health',        path: '/health',       requiredPermission: 'service:read' },
  { iconName: 'releases',  label: 'Releases',      path: '/releases',     requiredPermission: 'assessment:read' },
  { iconName: 'findings',  label: 'Findings',      path: '/findings',     requiredPermission: 'finding:read' },
  { iconName: 'remediate', label: 'Remediation',   path: '/remediation',  requiredPermission: 'finding:read' },
  { iconName: 'agent',     label: 'AI Agent',      path: '/ai-agent',     requiredPermission: 'service:read' },
  { iconName: 'audit',     label: 'Audit',         path: '/audit',        requiredPermission: 'service:read' },
];

// ---------------------------------------------------------------------------
// Tech Lead (developer items + approvals)
// ---------------------------------------------------------------------------

export const techLeadNav: NavConfigItem[] = [
  { iconName: 'dashboard', label: 'Dashboard',    path: '/dashboard',    requiredPermission: 'service:read' },
  { iconName: 'health',    label: 'Health',        path: '/health',       requiredPermission: 'service:read' },
  { iconName: 'releases',  label: 'Releases',      path: '/releases',     requiredPermission: 'assessment:read' },
  { iconName: 'findings',  label: 'Findings',      path: '/findings',     requiredPermission: 'finding:read' },
  { iconName: 'remediate', label: 'Remediation',   path: '/remediation',  requiredPermission: 'finding:read' },
  { iconName: 'approvals', label: 'Approvals',     path: '/approvals',    requiredPermission: 'assessment:write' },
  { iconName: 'agent',     label: 'AI Agent',      path: '/ai-agent',     requiredPermission: 'service:read' },
  { iconName: 'audit',     label: 'Audit',         path: '/audit',        requiredPermission: 'service:read' },
];

// ---------------------------------------------------------------------------
// Security Reviewer (security-focused, with badge)
// ---------------------------------------------------------------------------

export const securityReviewerNav: NavConfigItem[] = [
  { iconName: 'dashboard', label: 'Dashboard',       path: '/dashboard',   requiredPermission: 'service:read' },
  { iconName: 'security',  label: 'Security Review', path: '/security',    requiredPermission: 'security:review' },
  { iconName: 'findings',  label: 'Findings',        path: '/findings',    requiredPermission: 'finding:read' },
  { iconName: 'escalate',  label: 'Escalations',     path: '/escalations', requiredPermission: 'finding:escalate' },
  { iconName: 'releases',  label: 'Assessments',     path: '/releases',    requiredPermission: 'assessment:read' },
];

// ---------------------------------------------------------------------------
// Platform Admin (admin-focused)
// ---------------------------------------------------------------------------

export const platformAdminNav: NavConfigItem[] = [
  { iconName: 'dashboard',     label: 'Dashboard',    path: '/dashboard',        requiredPermission: 'service:read' },
  { iconName: 'services',      label: 'Services',     path: '/services',         requiredPermission: 'service:read' },
  { iconName: 'policies',      label: 'Policies',     path: '/admin/policies',   requiredPermission: 'admin:access' },
  { iconName: 'rbac',          label: 'RBAC',         path: '/admin/rbac',       requiredPermission: 'admin:access' },
  { iconName: 'users',         label: 'Users',        path: '/admin/users',      requiredPermission: 'admin:access' },
  { iconName: 'integrations',  label: 'Integrations', path: '/admin/integrations', requiredPermission: 'admin:access' },
];

// ---------------------------------------------------------------------------
// Engineering Manager (portfolio + trends)
// ---------------------------------------------------------------------------

export const engineeringManagerNav: NavConfigItem[] = [
  { iconName: 'portfolio',  label: 'Manager Dashboard', path: '/manager-dashboard', requiredPermission: 'report:read' },
  { iconName: 'dashboard',  label: 'Dev Dashboard',     path: '/dashboard',         requiredPermission: 'service:read' },
  { iconName: 'trends',     label: 'Trends',            path: '/trends',            requiredPermission: 'report:read' },
  { iconName: 'findings',   label: 'Findings',          path: '/findings',          requiredPermission: 'finding:read' },
  { iconName: 'approvals',  label: 'Approvals',         path: '/approvals',         requiredPermission: 'assessment:approve' },
];

// ---------------------------------------------------------------------------
// Operator (platform health + operations)
// ---------------------------------------------------------------------------

export const operatorNav: NavConfigItem[] = [
  { iconName: 'platform',  label: 'Platform Health', path: '/platform/health', requiredPermission: 'operations:read' },
  { iconName: 'monitor',   label: 'Monitoring',      path: '/monitoring',      requiredPermission: 'operations:manage' },
  { iconName: 'services',  label: 'Services',        path: '/services',        requiredPermission: 'service:read' },
  { iconName: 'alerts',    label: 'Alerts',          path: '/alerts',          requiredPermission: 'operations:read' },
];
