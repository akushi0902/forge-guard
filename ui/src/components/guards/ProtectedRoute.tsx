/**
 * ProtectedRoute — authentication gate for all authenticated views.
 *
 * Reads isAuthenticated and isLoading from the auth store:
 *  - Loading:         renders a centered loading spinner.
 *  - Unauthenticated: redirects to /login, preserving the current URL in
 *                     location.state.from for post-login redirect.
 *  - Authenticated:   renders <Outlet /> (nested route content).
 *
 * NOTE: This is a client-side convenience guard only. Server-side RBAC is
 * the authoritative enforcement layer.
 */

import { Center, Loader, Text } from '@mantine/core';
import { type JSX } from 'react';
import { Navigate, Outlet, useLocation } from 'react-router-dom';
import { useAuthStore } from '@/stores/auth-store';

export function ProtectedRoute(): JSX.Element {
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated);
  const isLoading = useAuthStore((s) => s.isLoading);
  const location = useLocation();

  if (isLoading) {
    return (
      <Center style={{ minHeight: '100vh' }} aria-label="Loading">
        <Loader size="md" />
        <Text ml="sm" c="dimmed" visually-hidden>
          Loading…
        </Text>
      </Center>
    );
  }

  if (!isAuthenticated) {
    return <Navigate to="/login" state={{ from: location }} replace />;
  }

  return <Outlet />;
}
