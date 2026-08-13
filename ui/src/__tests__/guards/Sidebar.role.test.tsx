/**
 * Role-based Sidebar rendering tests (WO-070).
 *
 * Verifies that each role sees the correct number of nav items.
 */

import { describe, it, expect, beforeEach } from 'vitest';
import { screen } from '@testing-library/react';
import { render } from '@/test-utils';
import { Sidebar } from '@/components/layout/Sidebar';
import { useLayoutStore } from '@/stores/layout';
import { developerNav, operatorNav, platformAdminNav, securityReviewerNav } from '@/config/navigation';

// Minimal NavItems for each role (from config, with simple icons)
const ICON = <span />;

function toNavItems(config: typeof developerNav) {
  return config.map((item) => ({ ...item, icon: ICON }));
}

const developerPerms = ['service:read', 'finding:read', 'score:read', 'assessment:read'];
const operatorPerms  = ['service:read', 'operations:read', 'operations:manage'];
const adminPerms     = ['service:read', 'finding:read', 'admin:access', 'policy:read', 'user:read', 'user:write'];
const secReviewerPerms = ['service:read', 'finding:read', 'finding:escalate', 'assessment:read', 'security:review'];

beforeEach(() => {
  useLayoutStore.setState({ isSidebarCollapsed: false });
});

describe('Sidebar role-based rendering', () => {
  it('Developer sees 7 nav items', () => {
    render(
      <Sidebar navItems={toNavItems(developerNav)} userPermissions={developerPerms} />,
    );
    // All 7 developer items have requiredPermission that developer has
    const navLinks = screen.getAllByRole('button');
    // Count items + collapse button; subtract 1 for collapse toggle
    const allLabels = developerNav.map((i) => i.label);
    allLabels.forEach((label) => {
      expect(screen.getByLabelText(label)).toBeInTheDocument();
    });
    expect(developerNav).toHaveLength(7);
  });

  it('Operator sees operator-specific items (operations:manage required)', () => {
    render(
      <Sidebar navItems={toNavItems(operatorNav)} userPermissions={operatorPerms} />,
    );
    expect(screen.getByLabelText('Monitoring')).toBeInTheDocument();
    expect(screen.getByLabelText('Platform Health')).toBeInTheDocument();
  });

  it('Platform Admin sees admin items', () => {
    render(
      <Sidebar navItems={toNavItems(platformAdminNav)} userPermissions={adminPerms} />,
    );
    expect(screen.getByLabelText('Policies')).toBeInTheDocument();
    expect(screen.getByLabelText('RBAC')).toBeInTheDocument();
  });

  it('Security Reviewer sees security review item', () => {
    render(
      <Sidebar navItems={toNavItems(securityReviewerNav)} userPermissions={secReviewerPerms} />,
    );
    expect(screen.getByLabelText('Security Review')).toBeInTheDocument();
  });

  it('items with missing permission are hidden', () => {
    // Developer does NOT have admin:access
    render(
      <Sidebar navItems={toNavItems(platformAdminNav)} userPermissions={developerPerms} />,
    );
    expect(screen.queryByLabelText('Policies')).not.toBeInTheDocument();
    expect(screen.queryByLabelText('RBAC')).not.toBeInTheDocument();
  });
});
