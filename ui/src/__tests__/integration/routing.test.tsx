/**
 * Integration tests for route navigation (WO-070).
 *
 * Uses createMemoryRouter to test:
 *  1. Unauthenticated user accessing /dashboard → redirected to /login
 *  2. Developer accessing /admin/policies → 403 ForbiddenPage
 *  3. Platform Admin accessing /admin/policies → 200 content
 *  4. Tech Lead accessing /dashboard → renders successfully
 *  5. Unknown route → 404 NotFoundPage
 */

import { describe, it, expect, beforeEach } from 'vitest';
import { screen } from '@testing-library/react';
import { render } from '@testing-library/react';
import { createMemoryRouter, RouterProvider } from 'react-router-dom';
import { MantineProvider } from '@mantine/core';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { theme } from '@/theme';
import { useAuthStore } from '@/stores/auth-store';
import { ProtectedRoute } from '@/components/guards/ProtectedRoute';
import { RoleGuard } from '@/components/guards/RoleGuard';
import { ForbiddenPage } from '@/pages/ForbiddenPage';
import { NotFoundPage } from '@/pages/NotFoundPage';
import { Role } from '@/types';
import type { User } from '@/stores/auth-store';

// ---------------------------------------------------------------------------
// Test user fixtures
// ---------------------------------------------------------------------------

const developerUser: User = {
  id: 'u1', email: 'dev@test.com', name: 'Dev',
  role: Role.Developer,
  permissions: ['service:read', 'finding:read', 'score:read', 'assessment:read'],
};

const techLeadUser: User = {
  id: 'u2', email: 'tl@test.com', name: 'TL',
  role: Role.TechLead,
  permissions: ['service:read', 'service:write', 'finding:read', 'finding:write',
    'score:read', 'assessment:read', 'assessment:write'],
};

const platformAdminUser: User = {
  id: 'u3', email: 'admin@test.com', name: 'Admin',
  role: Role.PlatformAdmin,
  permissions: ['service:read', 'finding:read', 'score:read', 'assessment:read',
    'policy:read', 'policy:write', 'user:read', 'user:write', 'admin:access'],
};

// ---------------------------------------------------------------------------
// Router factory
// ---------------------------------------------------------------------------

function makeRouter(initialEntry: string) {
  return createMemoryRouter(
    [
      { path: '/login', element: <div data-testid="login-page">Login</div> },
      {
        path: '/',
        element: <ProtectedRoute />,
        children: [
          {
            path: 'dashboard',
            element: (
              <RoleGuard requiredPermission="service:read">
                <div data-testid="dashboard-content">Dashboard</div>
              </RoleGuard>
            ),
          },
          {
            path: 'admin/policies',
            element: (
              <RoleGuard requiredPermission="admin:access">
                <div data-testid="policies-content">Policies</div>
              </RoleGuard>
            ),
          },
        ],
      },
      { path: '*', element: <NotFoundPage /> },
    ],
    { initialEntries: [initialEntry] },
  );
}

function renderRouter(initialEntry: string) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <MantineProvider theme={theme}>
      <QueryClientProvider client={qc}>
        <RouterProvider router={makeRouter(initialEntry)} />
      </QueryClientProvider>
    </MantineProvider>,
  );
}

beforeEach(() => {
  useAuthStore.setState({ user: null, isAuthenticated: false, isLoading: false, csrfToken: null });
});

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('routing integration', () => {
  it('unauthenticated user accessing /dashboard is redirected to /login', async () => {
    useAuthStore.setState({ isAuthenticated: false, isLoading: false });
    renderRouter('/dashboard');
    expect(await screen.findByTestId('login-page')).toBeInTheDocument();
  });

  it('developer accessing /admin/policies sees ForbiddenPage', async () => {
    useAuthStore.setState({ user: developerUser, isAuthenticated: true, isLoading: false });
    renderRouter('/admin/policies');
    expect(await screen.findByTestId('forbidden-message')).toBeInTheDocument();
    expect(screen.queryByTestId('policies-content')).not.toBeInTheDocument();
  });

  it('platform admin accessing /admin/policies sees content', async () => {
    useAuthStore.setState({ user: platformAdminUser, isAuthenticated: true, isLoading: false });
    renderRouter('/admin/policies');
    expect(await screen.findByTestId('policies-content')).toBeInTheDocument();
  });

  it('tech lead accessing /dashboard renders successfully', async () => {
    useAuthStore.setState({ user: techLeadUser, isAuthenticated: true, isLoading: false });
    renderRouter('/dashboard');
    expect(await screen.findByTestId('dashboard-content')).toBeInTheDocument();
  });

  it('unknown route renders NotFoundPage', async () => {
    useAuthStore.setState({ isAuthenticated: true, isLoading: false });
    renderRouter('/this-route-does-not-exist');
    expect(await screen.findByLabelText('Page not found')).toBeInTheDocument();
  });
});
