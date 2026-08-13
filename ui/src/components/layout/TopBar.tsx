/**
 * TopBar — application header bar.
 *
 * Slots:
 *   Breadcrumb        — auto-generated from current route or explicit segments
 *   ServiceSelector   — dropdown to switch active service context
 *   UserAvatar        — avatar with user menu (profile, logout)
 *   Dark mode toggle  — switches between light and dark colour scheme
 */

import {
  ActionIcon,
  Group,
  Select,
  Text,
  useMantineColorScheme,
} from '@mantine/core';
import { type JSX } from 'react';
import { useLocation } from 'react-router-dom';
import { Breadcrumb, type BreadcrumbSegment } from '@/components/shared/Breadcrumb';
import { Avatar } from '@/components/shared/Avatar';
import { Dropdown, type DropdownItem } from '@/components/shared/Dropdown';
import { type Service } from '@/types';

// ---------------------------------------------------------------------------
// Auto-breadcrumb generator
// ---------------------------------------------------------------------------

/** Converts a URL path segment to a human-readable label. */
function segmentToLabel(segment: string): string {
  return segment
    .replace(/-/g, ' ')
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

/**
 * Generates BreadcrumbSegment[] from the current pathname.
 * e.g. /admin/policies → [{ label: 'Admin', href: '/admin' }, { label: 'Policies' }]
 */
export function buildBreadcrumbsFromPath(pathname: string): BreadcrumbSegment[] {
  const parts = pathname.split('/').filter(Boolean);
  if (parts.length === 0) return [{ label: 'Dashboard' }];

  return parts.map((part, i) => {
    const href = '/' + parts.slice(0, i + 1).join('/');
    const isLast = i === parts.length - 1;
    return isLast
      ? { label: segmentToLabel(part) }
      : { label: segmentToLabel(part), href };
  });
}

// ---------------------------------------------------------------------------
// ServiceSelector
// ---------------------------------------------------------------------------

interface ServiceSelectorProps {
  services: Service[];
  selectedId: string | null;
  onSelect: (id: string | null) => void;
}

function ServiceSelector({ services, selectedId, onSelect }: ServiceSelectorProps): JSX.Element {
  const data = services.map((s) => ({ value: s.id, label: s.name }));
  return (
    <Select
      placeholder={data.length === 0 ? 'No services registered' : 'Select service'}
      data={data}
      value={selectedId}
      onChange={onSelect}
      disabled={data.length === 0}
      searchable
      clearable
      aria-label="Select active service"
      style={{ minWidth: 200 }}
    />
  );
}

// ---------------------------------------------------------------------------
// DarkModeToggle
// ---------------------------------------------------------------------------

function DarkModeToggle(): JSX.Element {
  const { colorScheme, toggleColorScheme } = useMantineColorScheme();
  const isDark = colorScheme === 'dark';
  return (
    <ActionIcon
      variant="subtle"
      color="neutral"
      size="lg"
      onClick={toggleColorScheme}
      aria-label={isDark ? 'Switch to light mode' : 'Switch to dark mode'}
      title={isDark ? 'Switch to light mode' : 'Switch to dark mode'}
    >
      {isDark ? '☀' : '🌙'}
    </ActionIcon>
  );
}

// ---------------------------------------------------------------------------
// TopBar
// ---------------------------------------------------------------------------

export interface TopBarProps {
  /** Explicit breadcrumb segments. If omitted, auto-generated from current route. */
  breadcrumbs?: BreadcrumbSegment[];
  services?: Service[];
  selectedServiceId?: string | null;
  onServiceSelect?: (id: string | null) => void;
  userName?: string;
  userAvatarSrc?: string | null;
  userMenuItems?: DropdownItem[];
}

/**
 * @example
 * <TopBar
 *   services={services}
 *   selectedServiceId={activeId}
 *   onServiceSelect={setActiveId}
 *   userName={user.name}
 *   userMenuItems={[{ key: 'logout', label: 'Log out', onClick: logout }]}
 * />
 */
export function TopBar({
  breadcrumbs,
  services = [],
  selectedServiceId = null,
  onServiceSelect,
  userName,
  userAvatarSrc,
  userMenuItems = [],
}: TopBarProps): JSX.Element {
  const { pathname } = useLocation();
  const resolvedBreadcrumbs = breadcrumbs ?? buildBreadcrumbsFromPath(pathname);

  return (
    <Group
      component="header"
      justify="space-between"
      px="md"
      py="sm"
      style={{
        borderBottom: '1px solid var(--mantine-color-neutral-2)',
        position: 'sticky',
        top: 0,
        background: 'var(--mantine-color-body)',
        zIndex: 100,
      }}
      aria-label="Top navigation bar"
    >
      {/* Left: breadcrumb */}
      {resolvedBreadcrumbs.length > 0 ? (
        <Breadcrumb segments={resolvedBreadcrumbs} />
      ) : (
        <Text size="sm" c="dimmed">
          ForgeGuard
        </Text>
      )}

      {/* Right: service selector, dark mode toggle, user avatar */}
      <Group gap="sm">
        <ServiceSelector
          services={services}
          selectedId={selectedServiceId}
          onSelect={onServiceSelect ?? (() => {})}
        />
        <DarkModeToggle />
        {userName && (
          <Dropdown
            trigger={<Avatar name={userName} src={userAvatarSrc} size="sm" />}
            items={userMenuItems}
            triggerAriaLabel={`User menu for ${userName}`}
          />
        )}
      </Group>
    </Group>
  );
}
