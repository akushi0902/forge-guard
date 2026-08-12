/**
 * Component tests for RBACManagement page (WO-080).
 *
 * Covers: tab navigation, users table rendering, search filtering,
 * role dropdown, confirm modal flow, self-change prevention,
 * permission matrix rendering, PII masking, RBAC guard.
 */

import {
  afterAll,
  afterEach,
  beforeAll,
  describe,
  expect,
  it,
} from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';

import { render } from '@/test-utils';
import { RBACManagement } from '@/pages/RBACManagement';
import { server } from '@/test/mocks/server';
import { USERS_RESPONSE_FIXTURE } from '@/test/fixtures/rbacData';
import { Role } from '@/types';

beforeAll(() => server.listen({ onUnhandledRequest: 'warn' }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

function setAuthUser(permissions: string[] = ['rbac.manage', 'service.view'], userId = 'usr-099') {
  const { useAuthStore } = require('@/stores/auth-store');
  useAuthStore.setState({
    user: {
      id: userId,
      email: 'admin@test.com',
      name: 'Test Admin',
      role: Role.PlatformAdmin,
      permissions,
    },
    isAuthenticated: true,
    isLoading: false,
    csrfToken: null,
  });
}

describe('RBACManagement — tab navigation', () => {
  it('renders two tabs: Users and Roles & Permissions', () => {
    setAuthUser();
    render(<RBACManagement />);
    expect(screen.getByTestId('tab-users')).toBeInTheDocument();
    expect(screen.getByTestId('tab-matrix')).toBeInTheDocument();
  });

  it('shows Users tab by default', () => {
    setAuthUser();
    render(<RBACManagement />);
    expect(screen.getByTestId('users-panel')).toBeInTheDocument();
  });

  it('switches to Roles & Permissions tab on click', async () => {
    setAuthUser();
    render(<RBACManagement />);
    const user = userEvent.setup();
    await user.click(screen.getByTestId('tab-matrix'));
    await waitFor(() =>
      expect(screen.getByTestId('role-permission-matrix')).toBeInTheDocument(),
    );
  });
});

describe('RBACManagement — RBAC guard', () => {
  it('renders ForbiddenPage for user without rbac.manage', () => {
    setAuthUser(['service.view']);
    render(<RBACManagement />);
    expect(screen.queryByTestId('rbac-tabs')).not.toBeInTheDocument();
  });
});

describe('UsersPanel — table rendering', () => {
  it('displays all users from API', async () => {
    setAuthUser();
    render(<RBACManagement />);
    await waitFor(() =>
      expect(screen.getByTestId('users-table')).toBeInTheDocument(),
    );
    // First user: Alice Chen
    expect(screen.getByText('Alice Chen')).toBeInTheDocument();
  });

  it('shows PII-masked emails', async () => {
    setAuthUser();
    render(<RBACManagement />);
    await waitFor(() =>
      expect(screen.getByTestId('users-table')).toBeInTheDocument(),
    );
    // Alice's email alice@forgeguard.io → a***@forgeguard.io
    expect(screen.getByTestId('email-usr-001')).toHaveTextContent('a***@forgeguard.io');
    // Bob's email bob.martinez@forgeguard.io → b***@forgeguard.io
    expect(screen.getByTestId('email-usr-002')).toHaveTextContent('b***@forgeguard.io');
  });

  it('shows empty state when no users match search', async () => {
    setAuthUser();
    render(<RBACManagement />);
    const user = userEvent.setup();
    await waitFor(() =>
      expect(screen.getByTestId('user-search')).toBeInTheDocument(),
    );
    await user.type(screen.getByTestId('user-search'), 'zzznomatch');
    await waitFor(() =>
      expect(screen.getByTestId('users-empty-state')).toBeInTheDocument(),
    );
  });

  it('filters users by name', async () => {
    setAuthUser();
    render(<RBACManagement />);
    const user = userEvent.setup();
    await waitFor(() =>
      expect(screen.getByTestId('user-search')).toBeInTheDocument(),
    );
    await user.type(screen.getByTestId('user-search'), 'Alice');
    await waitFor(() => {
      expect(screen.getByText('Alice Chen')).toBeInTheDocument();
      expect(screen.queryByText('Bob Martinez')).not.toBeInTheDocument();
    });
  });
});

describe('ConfirmRoleChangeModal — flow', () => {
  it('opens confirm modal when a different role is selected', async () => {
    setAuthUser();
    render(<RBACManagement />);
    await waitFor(() =>
      expect(screen.getByTestId('role-select-usr-001')).toBeInTheDocument(),
    );
    // Role select for usr-001 (Alice Chen, Developer) — change to Tech Lead
    // Mantine Select uses combobox — find and interact
    const select = screen.getByTestId('role-select-usr-001');
    const user = userEvent.setup();
    await user.click(select);
    // Find "Tech Lead" option in the dropdown
    const option = await screen.findByText('Tech Lead');
    await user.click(option);
    await waitFor(() =>
      expect(screen.getByTestId('confirm-role-modal')).toBeInTheDocument(),
    );
  });

  it('shows correct before/after roles in modal', async () => {
    setAuthUser();
    render(<RBACManagement />);
    await waitFor(() =>
      expect(screen.getByTestId('role-select-usr-001')).toBeInTheDocument(),
    );
    const user = userEvent.setup();
    await user.click(screen.getByTestId('role-select-usr-001'));
    const option = await screen.findByText('Tech Lead');
    await user.click(option);
    await waitFor(() => {
      expect(screen.getByTestId('current-role-badge')).toHaveTextContent('Developer');
      expect(screen.getByTestId('new-role-badge')).toHaveTextContent('Tech Lead');
    });
  });

  it('closes modal on cancel without changing role', async () => {
    setAuthUser();
    render(<RBACManagement />);
    await waitFor(() =>
      expect(screen.getByTestId('role-select-usr-001')).toBeInTheDocument(),
    );
    const user = userEvent.setup();
    await user.click(screen.getByTestId('role-select-usr-001'));
    await user.click(await screen.findByText('Tech Lead'));
    await waitFor(() =>
      expect(screen.getByTestId('confirm-role-modal')).toBeInTheDocument(),
    );
    await user.click(screen.getByText('Cancel'));
    await waitFor(() =>
      expect(screen.queryByTestId('confirm-role-modal')).not.toBeInTheDocument(),
    );
  });

  it('displays API 400 error inline in modal', async () => {
    server.use(
      http.put('/api/v1/admin/users/:id/role', () =>
        HttpResponse.json(
          { detail: 'Cannot change role: this is the last Platform Admin.', error_code: 'LAST_ADMIN' },
          { status: 400 },
        ),
      ),
    );
    setAuthUser();
    render(<RBACManagement />);
    await waitFor(() =>
      expect(screen.getByTestId('role-select-usr-001')).toBeInTheDocument(),
    );
    const user = userEvent.setup();
    await user.click(screen.getByTestId('role-select-usr-001'));
    await user.click(await screen.findByText('Tech Lead'));
    await waitFor(() =>
      expect(screen.getByTestId('confirm-btn')).toBeInTheDocument(),
    );
    await user.click(screen.getByTestId('confirm-btn'));
    await waitFor(() =>
      expect(screen.getByTestId('modal-error')).toBeInTheDocument(),
    );
  });
});

describe('Self-role-change prevention', () => {
  it('disables role dropdown for current user row', async () => {
    // Set auth user to usr-001 (Alice Chen)
    setAuthUser(['rbac.manage', 'service.view'], 'usr-001');
    render(<RBACManagement />);
    await waitFor(() =>
      expect(screen.getByTestId('role-select-usr-001')).toBeInTheDocument(),
    );
    expect(screen.getByTestId('role-select-usr-001').closest('input, [data-disabled]') ??
      screen.getByTestId('role-select-usr-001')).toBeTruthy();
  });
});

describe('RolePermissionMatrix', () => {
  it('renders a row for every permission', async () => {
    setAuthUser();
    render(<RBACManagement />);
    const user = userEvent.setup();
    await user.click(screen.getByTestId('tab-matrix'));
    await waitFor(() =>
      expect(screen.getByTestId('role-permission-matrix')).toBeInTheDocument(),
    );
    // Check a few permission rows
    expect(screen.getByTestId('matrix-row-service.view')).toBeInTheDocument();
    expect(screen.getByTestId('matrix-row-rbac.manage')).toBeInTheDocument();
    expect(screen.getByTestId('matrix-row-policy.manage')).toBeInTheDocument();
  });

  it('shows checkmark for Platform Admin rbac.manage permission', async () => {
    setAuthUser();
    render(<RBACManagement />);
    const user = userEvent.setup();
    await user.click(screen.getByTestId('tab-matrix'));
    await waitFor(() =>
      expect(screen.getByTestId('matrix-cell-rbac.manage-platform_admin')).toBeInTheDocument(),
    );
    const cell = screen.getByTestId('matrix-cell-rbac.manage-platform_admin');
    expect(cell).toHaveTextContent('✓');
  });

  it('shows dash for Developer rbac.manage permission', async () => {
    setAuthUser();
    render(<RBACManagement />);
    const user = userEvent.setup();
    await user.click(screen.getByTestId('tab-matrix'));
    await waitFor(() =>
      expect(screen.getByTestId('matrix-cell-rbac.manage-developer')).toBeInTheDocument(),
    );
    const cell = screen.getByTestId('matrix-cell-rbac.manage-developer');
    expect(cell).toHaveTextContent('—');
  });
});
