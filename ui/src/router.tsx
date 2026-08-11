import { type JSX } from 'react';
import { createBrowserRouter, type RouteObject } from 'react-router-dom';

import { LoginPage } from '@/pages/LoginPage';

// --------------------------------------------------------------------------
// Placeholder page components
//
// Each page component is a thin stub. Feature WOs will replace these with
// fully implemented views. They are inline here to keep the scaffold minimal
// and avoid empty files that TypeScript would flag as unused-import errors.
// --------------------------------------------------------------------------

function DashboardPage(): JSX.Element {
  return (
    <main style={{ padding: '2rem' }}>
      <h1>Dashboard</h1>
      <p>Engineering Health overview — coming soon.</p>
    </main>
  );
}

function ServiceHealthPage(): JSX.Element {
  return (
    <main style={{ padding: '2rem' }}>
      <h1>Service Health</h1>
      <p>Per-service policy evaluation detail — coming soon.</p>
    </main>
  );
}

function ReleaseAssessmentPage(): JSX.Element {
  return (
    <main style={{ padding: '2rem' }}>
      <h1>Release Assessment</h1>
      <p>Release risk scoring and decision workflow — coming soon.</p>
    </main>
  );
}

function SecurityReviewPage(): JSX.Element {
  return (
    <main style={{ padding: '2rem' }}>
      <h1>Security Review</h1>
      <p>Security finding escalations and reviewer actions — coming soon.</p>
    </main>
  );
}

function AdminPanelPage(): JSX.Element {
  return (
    <main style={{ padding: '2rem' }}>
      <h1>Admin Panel</h1>
      <p>Policy configuration and RBAC management — coming soon.</p>
    </main>
  );
}

function OperatorHealthPage(): JSX.Element {
  return (
    <main style={{ padding: '2rem' }}>
      <h1>Platform Health</h1>
      <p>Operator monitoring dashboard — coming soon.</p>
    </main>
  );
}

function NotFoundPage(): JSX.Element {
  return (
    <main style={{ padding: '2rem' }}>
      <h1>404 — Page Not Found</h1>
      <p>The page you requested does not exist.</p>
    </main>
  );
}

// --------------------------------------------------------------------------
// Route configuration
// --------------------------------------------------------------------------

const routes: RouteObject[] = [
  {
    path: '/login',
    element: <LoginPage />,
  },
  {
    path: '/',
    element: <DashboardPage />,
  },
  {
    path: '/services/:id',
    element: <ServiceHealthPage />,
  },
  {
    path: '/releases',
    element: <ReleaseAssessmentPage />,
  },
  {
    path: '/security',
    element: <SecurityReviewPage />,
  },
  {
    path: '/admin',
    element: <AdminPanelPage />,
  },
  {
    path: '/operations',
    element: <OperatorHealthPage />,
  },
  {
    path: '*',
    element: <NotFoundPage />,
  },
];

export const router = createBrowserRouter(routes);

// Named exports for individual page components so tests can import them directly.
export {
  AdminPanelPage,
  DashboardPage,
  NotFoundPage,
  OperatorHealthPage,
  ReleaseAssessmentPage,
  SecurityReviewPage,
  ServiceHealthPage,
};
export { LoginPage } from '@/pages/LoginPage';
