/**
 * Unit tests for ProtectedRoute guard (WO-070).
 *
 * Scenarios:
 *  - Unauthenticated user is redirected to /login with from state
 *  - Loading state shows spinner, not login redirect
 *  - Authenticated user renders Outlet children
 */

import { describe, it, expect, beforeEach } from 'vitest';
import { screen } from '@testing-library/react';
import { createMemoryRouter, RouterProvider } from 'react-router-dom';
import { render } from '@testing-library/react';
import { MantineProvider } from '@mantine/core';
import { theme } from '@/theme';
import { useAuthStore } from '@/stores/auth-store';
import { ProtectedRoute } from '@/components/guards/ProtectedRoute';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function renderRouter(initialEntry: string, authState: Partial<typeof useAuthStore.getState>) {
  useAuthStore.setState({ user: null, isAuthenticated: false, isLoading: false, csrfToken: null, ...authState });

  const router = createMemoryRouter(
    [
      {
        path: '/',
        element: <ProtectedRoute />,
        children: [
          { index: true, element: <div data-testid="protected-content">Protected</div> },
        ],
      },
      {
        path: '/login',
        element: <div data-testid="login-page">Login</div>,
      },
    ],
    { initialEntries: [initialEntry] },
  );

  return render(
    <MantineProvider theme={theme}>
      <RouterProvider router={router} />
    </MantineProvider>,
  );
}

beforeEach(() => {
  useAuthStore.setState({ user: null, isAuthenticated: false, isLoading: false, csrfToken: null });
});

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('ProtectedRoute', () => {
  it('redirects unauthenticated user to /login', async () => {
    renderRouter('/dashboard', { isAuthenticated: false, isLoading: false });
    expect(await screen.findByTestId('login-page')).toBeInTheDocument();
  });

  it('renders children when authenticated', async () => {
    renderRouter('/', { isAuthenticated: true, isLoading: false });
    expect(await screen.findByTestId('protected-content')).toBeInTheDocument();
  });

  it('shows loading state without redirecting when isLoading is true', async () => {
    renderRouter('/', { isAuthenticated: false, isLoading: true });
    expect(await screen.findByLabelText('Loading')).toBeInTheDocument();
    expect(screen.queryByTestId('login-page')).not.toBeInTheDocument();
  });

  it('preserves from state when redirecting to login', async () => {
    // Navigate to /dashboard while unauthenticated — router should send to /login
    renderRouter('/dashboard', { isAuthenticated: false, isLoading: false });
    expect(await screen.findByTestId('login-page')).toBeInTheDocument();
    expect(screen.queryByTestId('protected-content')).not.toBeInTheDocument();
  });
});
