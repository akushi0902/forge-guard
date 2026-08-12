/**
 * Unit tests for RoleGuard component (WO-070).
 *
 * Scenarios:
 *  - Renders children when user has the required permission
 *  - Renders ForbiddenPage when user lacks the required permission
 *  - ForbiddenPage message includes permission label and role name
 *  - User with empty permissions array sees ForbiddenPage
 */

import { describe, it, expect, beforeEach } from 'vitest';
import { screen } from '@testing-library/react';
import { render } from '@/test-utils';
import { useAuthStore } from '@/stores/auth-store';
import { RoleGuard } from '@/components/guards/RoleGuard';
import { Role } from '@/types';
import type { User } from '@/stores/auth-store';

const developerUser: User = {
  id: 'u1',
  email: 'dev@test.com',
  name: 'Dev User',
  role: Role.Developer,
  permissions: ['service:read', 'finding:read', 'score:read', 'assessment:read'],
};

const limitedUser: User = {
  id: 'u2',
  email: 'limited@test.com',
  name: 'Limited User',
  role: Role.Operator,
  permissions: ['operations:read'],
};

beforeEach(() => {
  useAuthStore.setState({ user: null, isAuthenticated: false, isLoading: false, csrfToken: null });
});

describe('RoleGuard', () => {
  it('renders children when user has the required permission', () => {
    useAuthStore.setState({ user: developerUser, isAuthenticated: true });

    render(
      <RoleGuard requiredPermission="service:read">
        <div data-testid="guarded-content">Secret content</div>
      </RoleGuard>,
    );

    expect(screen.getByTestId('guarded-content')).toBeInTheDocument();
    expect(screen.queryByTestId('forbidden-message')).not.toBeInTheDocument();
  });

  it('renders ForbiddenPage when user lacks the required permission', () => {
    useAuthStore.setState({ user: limitedUser, isAuthenticated: true });

    render(
      <RoleGuard requiredPermission="admin:access">
        <div data-testid="admin-content">Admin content</div>
      </RoleGuard>,
    );

    expect(screen.queryByTestId('admin-content')).not.toBeInTheDocument();
    expect(screen.getByTestId('forbidden-message')).toBeInTheDocument();
  });

  it('ForbiddenPage message mentions the permission label', () => {
    useAuthStore.setState({ user: limitedUser, isAuthenticated: true });

    render(
      <RoleGuard requiredPermission="admin:access">
        <div>Content</div>
      </RoleGuard>,
    );

    expect(screen.getByTestId('forbidden-message')).toHaveTextContent('Access Admin Panel');
  });

  it('ForbiddenPage message mentions the required role', () => {
    useAuthStore.setState({ user: limitedUser, isAuthenticated: true });

    render(
      <RoleGuard requiredPermission="admin:access">
        <div>Content</div>
      </RoleGuard>,
    );

    expect(screen.getByTestId('forbidden-message')).toHaveTextContent('Platform Admin');
  });

  it('renders ForbiddenPage for user with empty permissions array', () => {
    useAuthStore.setState({
      user: { ...developerUser, permissions: [] },
      isAuthenticated: true,
    });

    render(
      <RoleGuard requiredPermission="service:read">
        <div data-testid="content">Content</div>
      </RoleGuard>,
    );

    expect(screen.queryByTestId('content')).not.toBeInTheDocument();
    expect(screen.getByTestId('forbidden-message')).toBeInTheDocument();
  });

  it('renders ForbiddenPage when user is null (unauthenticated)', () => {
    useAuthStore.setState({ user: null, isAuthenticated: false });

    render(
      <RoleGuard requiredPermission="service:read">
        <div data-testid="content">Content</div>
      </RoleGuard>,
    );

    expect(screen.queryByTestId('content')).not.toBeInTheDocument();
    expect(screen.getByTestId('forbidden-message')).toBeInTheDocument();
  });
});
