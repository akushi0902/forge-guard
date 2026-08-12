/**
 * ForgeGuard React Router configuration (WO-070).
 *
 * Structure:
 *   /login                        — public, no auth required
 *   / (layout route)              — ProtectedRoute > AppLayout
 *     /dashboard                  — all authenticated users
 *     /health                     — service:read
 *     /releases                   — assessment:read
 *     /findings                   — finding:read
 *     /remediation                — finding:read
 *     /approvals                  — assessment:write | assessment:approve
 *     /security                   — security:review
 *     /escalations                — finding:escalate
 *     /ai-agent                   — service:read
 *     /audit                      — service:read
 *     /portfolio                  — report:read
 *     /trends                     — report:read
 *     /services                   — service:read
 *     /platform/health            — operations:read
 *     /monitoring                 — operations:manage
 *     /alerts                     — operations:read
 *     /admin/policies             — admin:access
 *     /admin/rbac                 — admin:access
 *     /admin/users                — admin:access
 *     /admin/integrations         — admin:access
 *   * (404)                       — unmatched routes
 *
 * Page components are lazily loaded for code splitting.
 * The AppLayout shell is rendered by the layout route and provides
 * Sidebar (permission-filtered) + TopBar (auto-breadcrumb) + Outlet.
 */

import { Box } from '@mantine/core';
import {
  type JSX,
  lazy,
  Suspense,
  type ReactNode,
} from 'react';
import {
  createBrowserRouter,
  Outlet,
  useRouteError,
} from 'react-router-dom';

import { Sidebar, type NavItem } from '@/components/layout/Sidebar';
import { TopBar } from '@/components/layout/TopBar';
import { MainContent } from '@/components/layout/MainContent';
import { ProtectedRoute } from '@/components/guards/ProtectedRoute';
import { RoleGuard } from '@/components/guards/RoleGuard';
import { NotFoundPage } from '@/pages/NotFoundPage';
import { ForbiddenPage } from '@/pages/ForbiddenPage';
import { LoginPage } from '@/pages/LoginPage';
import { useAuthStore } from '@/stores/auth-store';
import {
  developerNav,
  techLeadNav,
  securityReviewerNav,
  platformAdminNav,
  engineeringManagerNav,
  operatorNav,
  type NavConfigItem,
} from '@/config/navigation';
import { Role } from '@/types';

// ---------------------------------------------------------------------------
// Icon resolver — maps icon names to ReactNode (no icon library required)
// ---------------------------------------------------------------------------

const ICON_MAP: Record<string, string> = {
  dashboard:    '📊',
  health:       '💚',
  releases:     '🚀',
  findings:     '🔍',
  remediate:    '🔧',
  agent:        '🤖',
  audit:        '📋',
  approvals:    '✅',
  security:     '🛡',
  escalate:     '⚠',
  services:     '⚙',
  policies:     '📜',
  rbac:         '🔐',
  users:        '👥',
  integrations: '🔗',
  portfolio:    '📈',
  trends:       '📉',
  platform:     '🖥',
  monitor:      '📡',
  alerts:       '🔔',
};

function resolveNavItems(config: NavConfigItem[]): NavItem[] {
  return config.map((item) => ({
    label: item.label,
    path: item.path,
    icon: (
      <span aria-hidden="true" style={{ fontSize: 16 }}>
        {ICON_MAP[item.iconName] ?? '●'}
      </span>
    ),
    requiredPermission: item.requiredPermission,
    badgeCount: item.badgeCount,
  }));
}

const NAV_BY_ROLE: Record<Role, NavItem[]> = {
  [Role.Developer]:          resolveNavItems(developerNav),
  [Role.TechLead]:           resolveNavItems(techLeadNav),
  [Role.SecurityReviewer]:   resolveNavItems(securityReviewerNav),
  [Role.PlatformAdmin]:      resolveNavItems(platformAdminNav),
  [Role.EngineeringManager]: resolveNavItems(engineeringManagerNav),
  [Role.Operator]:           resolveNavItems(operatorNav),
};

// ---------------------------------------------------------------------------
// Application shell layout
// ---------------------------------------------------------------------------

function AppLayout(): JSX.Element {
  const user = useAuthStore((s) => s.user);
  const logout = useAuthStore((s) => s.logout);

  const role = user?.role ?? Role.Developer;
  const navItems = NAV_BY_ROLE[role] ?? NAV_BY_ROLE[Role.Developer];

  return (
    <Box style={{ display: 'flex', minHeight: '100vh' }}>
      <Sidebar navItems={navItems} userPermissions={user?.permissions} />
      <Box style={{ flex: 1, display: 'flex', flexDirection: 'column' }}>
        <TopBar
          userName={user?.name}
          userMenuItems={[
            { key: 'logout', label: 'Log out', onClick: () => void logout() },
          ]}
        />
        <MainContent>
          <Outlet />
        </MainContent>
      </Box>
    </Box>
  );
}

// ---------------------------------------------------------------------------
// Page loading fallback
// ---------------------------------------------------------------------------

function PageLoader(): JSX.Element {
  return (
    <Box style={{ padding: '2rem', textAlign: 'center' }}>
      Loading…
    </Box>
  );
}

// ---------------------------------------------------------------------------
// Lazy page components
// ---------------------------------------------------------------------------

const DashboardPage        = lazy(() => import('@/pages/DashboardPage').then((m) => ({ default: m.DashboardPage })));
const DeveloperDashboard   = lazy(() => import('@/pages/DeveloperDashboard').then((m) => ({ default: m.DeveloperDashboard })));
const HealthPage      = lazy(() => import('@/pages/HealthPage').then((m) => ({ default: m.HealthPage })));
const ReleasesPage    = lazy(() => import('@/pages/ReleasesPage').then((m) => ({ default: m.ReleasesPage })));
const FindingsPage    = lazy(() => import('@/pages/FindingsPage').then((m) => ({ default: m.FindingsPage })));
const RemediationPage = lazy(() => import('@/pages/RemediationPage').then((m) => ({ default: m.RemediationPage })));
const ApprovalsPage   = lazy(() => import('@/pages/ApprovalsPage').then((m) => ({ default: m.ApprovalsPage })));
const SecurityPage    = lazy(() => import('@/pages/SecurityPage').then((m) => ({ default: m.SecurityPage })));
const EscalationsPage = lazy(() => import('@/pages/EscalationsPage').then((m) => ({ default: m.EscalationsPage })));
const AiAgentPage     = lazy(() => import('@/pages/AiAgentPage').then((m) => ({ default: m.AiAgentPage })));
const AuditPage       = lazy(() => import('@/pages/AuditPage').then((m) => ({ default: m.AuditPage })));
const PortfolioPage   = lazy(() => import('@/pages/PortfolioPage').then((m) => ({ default: m.PortfolioPage })));
const TrendsPage      = lazy(() => import('@/pages/TrendsPage').then((m) => ({ default: m.TrendsPage })));
const ServicesPage    = lazy(() => import('@/pages/ServicesPage').then((m) => ({ default: m.ServicesPage })));
const PlatformHealthPage = lazy(() => import('@/pages/PlatformHealthPage').then((m) => ({ default: m.PlatformHealthPage })));
const MonitoringPage  = lazy(() => import('@/pages/MonitoringPage').then((m) => ({ default: m.MonitoringPage })));
const AlertsPage      = lazy(() => import('@/pages/AlertsPage').then((m) => ({ default: m.AlertsPage })));
const PoliciesPage    = lazy(() => import('@/pages/PoliciesPage').then((m) => ({ default: m.PoliciesPage })));
const RbacPage        = lazy(() => import('@/pages/RbacPage').then((m) => ({ default: m.RbacPage })));
const UsersPage       = lazy(() => import('@/pages/UsersPage').then((m) => ({ default: m.UsersPage })));
const IntegrationsPage = lazy(() => import('@/pages/IntegrationsPage').then((m) => ({ default: m.IntegrationsPage })));
const ReleaseAssessmentRequestPage = lazy(() => import('@/pages/ReleaseAssessmentRequestPage').then((m) => ({ default: m.ReleaseAssessmentRequestPage })));

// ---------------------------------------------------------------------------
// Guarded route helper
// ---------------------------------------------------------------------------

function guarded(permission: string, element: ReactNode): JSX.Element {
  return (
    <Suspense fallback={<PageLoader />}>
      <RoleGuard requiredPermission={permission}>{element}</RoleGuard>
    </Suspense>
  );
}

// ---------------------------------------------------------------------------
// Route-level error element
// ---------------------------------------------------------------------------

function RouteErrorElement(): JSX.Element {
  const error = useRouteError();
  const message = error instanceof Error ? error.message : String(error);
  return (
    <ForbiddenPage missingPermission={undefined} />
  );
}

// ---------------------------------------------------------------------------
// Router
// ---------------------------------------------------------------------------

export const router = createBrowserRouter([
  {
    path: '/login',
    element: <LoginPage />,
  },
  {
    path: '/',
    element: <ProtectedRoute />,
    errorElement: <RouteErrorElement />,
    children: [
      {
        element: <AppLayout />,
        children: [
          {
            index: true,
            element: <Suspense fallback={<PageLoader />}><DashboardPage /></Suspense>,
          },
          {
            path: 'dashboard',
            element: guarded('service:read', <DeveloperDashboard />),
          },
          {
            path: 'health',
            element: guarded('service:read', <HealthPage />),
          },
          {
            path: 'releases',
            element: guarded('assessment:read', <ReleasesPage />),
          },
          {
            path: 'releases/new',
            element: guarded('assessment:write', <ReleaseAssessmentRequestPage />),
          },
          {
            path: 'findings',
            element: guarded('finding:read', <FindingsPage />),
          },
          {
            path: 'remediation',
            element: guarded('finding:read', <RemediationPage />),
          },
          {
            path: 'approvals',
            element: guarded('assessment:write', <ApprovalsPage />),
          },
          {
            path: 'security',
            element: guarded('security:review', <SecurityPage />),
          },
          {
            path: 'escalations',
            element: guarded('finding:escalate', <EscalationsPage />),
          },
          {
            path: 'ai-agent',
            element: guarded('service:read', <AiAgentPage />),
          },
          {
            path: 'audit',
            element: guarded('service:read', <AuditPage />),
          },
          {
            path: 'portfolio',
            element: guarded('report:read', <PortfolioPage />),
          },
          {
            path: 'trends',
            element: guarded('report:read', <TrendsPage />),
          },
          {
            path: 'services',
            element: guarded('service:read', <ServicesPage />),
          },
          {
            path: 'platform/health',
            element: guarded('operations:read', <PlatformHealthPage />),
          },
          {
            path: 'monitoring',
            element: guarded('operations:manage', <MonitoringPage />),
          },
          {
            path: 'alerts',
            element: guarded('operations:read', <AlertsPage />),
          },
          {
            path: 'admin/policies',
            element: guarded('admin:access', <PoliciesPage />),
          },
          {
            path: 'admin/rbac',
            element: guarded('admin:access', <RbacPage />),
          },
          {
            path: 'admin/users',
            element: guarded('admin:access', <UsersPage />),
          },
          {
            path: 'admin/integrations',
            element: guarded('admin:access', <IntegrationsPage />),
          },
        ],
      },
    ],
  },
  {
    path: '*',
    element: <NotFoundPage />,
  },
]);
