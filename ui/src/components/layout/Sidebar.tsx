/**
 * Sidebar — application navigation sidebar.
 *
 * Structure:
 *   SidebarHeader — logo + product name
 *   SidebarNav    — permission-filtered NavLink list
 *   SidebarFooter — collapse toggle
 *
 * Collapse state is persisted via the `useLayoutStore` Zustand store.
 * Active route is highlighted with Mantine NavLink's built-in active style.
 */

import {
  Badge,
  Box,
  NavLink,
  Stack,
  Text,
  Tooltip,
  UnstyledButton,
} from '@mantine/core';
import { type JSX, type ReactNode } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { useLayoutStore } from '@/stores/layout';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface NavItem {
  label: string;
  path: string;
  icon: ReactNode;
  /** If set, the item is only shown to users whose permissions include this slug. */
  requiredPermission?: string;
  /** Optional badge count displayed on the nav item. */
  badgeCount?: number;
}

export interface SidebarProps {
  navItems: NavItem[];
  /** Current user permissions for RBAC filtering. Undefined = show all items. */
  userPermissions?: string[];
  logoSrc?: string;
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

interface SidebarHeaderProps {
  collapsed: boolean;
  logoSrc?: string;
}

function SidebarHeader({ collapsed, logoSrc }: SidebarHeaderProps): JSX.Element {
  return (
    <Box
      px={collapsed ? 'xs' : 'md'}
      py="md"
      style={{ borderBottom: '1px solid var(--mantine-color-neutral-2)' }}
    >
      {collapsed ? (
        <Box style={{ width: 32, height: 32 }}>
          {logoSrc ? (
            <img src={logoSrc} alt="ForgeGuard" style={{ width: 32, height: 32 }} />
          ) : (
            <Text fw={700} size="lg" c="brand" aria-label="ForgeGuard">
              FG
            </Text>
          )}
        </Box>
      ) : (
        <Text fw={700} size="md" c="brand">
          ForgeGuard
        </Text>
      )}
    </Box>
  );
}

interface SidebarNavProps {
  items: NavItem[];
  collapsed: boolean;
}

function SidebarNav({ items, collapsed }: SidebarNavProps): JSX.Element {
  const navigate = useNavigate();
  const { pathname } = useLocation();

  return (
    <Stack gap={4} px="xs" py="sm" style={{ flex: 1, overflowY: 'auto' }}>
      {items.map((item) => {
        const isActive = pathname === item.path || pathname.startsWith(item.path + '/');
        const rightSection =
          item.badgeCount != null && item.badgeCount > 0 ? (
            <Badge size="xs" circle variant="filled" color="red" aria-label={`${item.badgeCount} items`}>
              {item.badgeCount}
            </Badge>
          ) : undefined;

        const nav = (
          <NavLink
            key={item.path}
            label={collapsed ? undefined : item.label}
            leftSection={item.icon}
            rightSection={collapsed ? undefined : rightSection}
            active={isActive}
            onClick={() => navigate(item.path)}
            aria-label={item.label}
            aria-current={isActive ? 'page' : undefined}
            style={isActive ? { borderLeft: '3px solid var(--mantine-color-brand-5)' } : undefined}
          />
        );

        return collapsed ? (
          <Tooltip key={item.path} label={item.label} position="right" withArrow>
            {nav}
          </Tooltip>
        ) : (
          nav
        );
      })}
    </Stack>
  );
}

interface SidebarFooterProps {
  collapsed: boolean;
  onToggle: () => void;
}

function SidebarFooter({ collapsed, onToggle }: SidebarFooterProps): JSX.Element {
  return (
    <Box
      px="xs"
      py="sm"
      style={{ borderTop: '1px solid var(--mantine-color-neutral-2)' }}
    >
      <UnstyledButton
        onClick={onToggle}
        aria-label={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 8,
          padding: '8px',
          borderRadius: 6,
          width: '100%',
        }}
      >
        <span aria-hidden="true">{collapsed ? '»' : '«'}</span>
        {!collapsed && <Text size="sm">Collapse</Text>}
      </UnstyledButton>
    </Box>
  );
}

// ---------------------------------------------------------------------------
// Sidebar
// ---------------------------------------------------------------------------

const SIDEBAR_WIDTH_EXPANDED = 220;
const SIDEBAR_WIDTH_COLLAPSED = 60;

/**
 * @example
 * <Sidebar
 *   navItems={resolvedNavItems}
 *   userPermissions={user.permissions}
 * />
 */
export function Sidebar({ navItems, userPermissions, logoSrc }: SidebarProps): JSX.Element {
  const { isSidebarCollapsed, toggleSidebar } = useLayoutStore();

  const visibleItems = navItems.filter(
    (item) => !item.requiredPermission || (userPermissions?.includes(item.requiredPermission) ?? false),
  );

  return (
    <Box
      component="nav"
      aria-label="Main navigation"
      style={{
        width: isSidebarCollapsed ? SIDEBAR_WIDTH_COLLAPSED : SIDEBAR_WIDTH_EXPANDED,
        minHeight: '100vh',
        display: 'flex',
        flexDirection: 'column',
        borderRight: '1px solid var(--mantine-color-neutral-2)',
        transition: 'width 0.2s ease',
        overflow: 'hidden',
      }}
    >
      <SidebarHeader collapsed={isSidebarCollapsed} logoSrc={logoSrc} />
      <SidebarNav items={visibleItems} collapsed={isSidebarCollapsed} />
      <SidebarFooter collapsed={isSidebarCollapsed} onToggle={toggleSidebar} />
    </Box>
  );
}

export { SidebarHeader, SidebarNav, SidebarFooter };
