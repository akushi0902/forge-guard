/**
 * TopBar — application header bar.
 *
 * Slots:
 *   Breadcrumb        — current page context navigation
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
import { Breadcrumb, type BreadcrumbSegment } from '@/components/shared/Breadcrumb';
import { Avatar } from '@/components/shared/Avatar';
import { Dropdown, type DropdownItem } from '@/components/shared/Dropdown';
import { type Service } from '@/types';

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
 *   breadcrumbs={[{ label: 'Home', href: '/' }, { label: 'Services' }]}
 *   services={services}
 *   selectedServiceId={activeId}
 *   onServiceSelect={setActiveId}
 *   userName={user.displayName}
 *   userMenuItems={[{ key: 'logout', label: 'Log out', onClick: logout }]}
 * />
 */
export function TopBar({
  breadcrumbs = [],
  services = [],
  selectedServiceId = null,
  onServiceSelect,
  userName,
  userAvatarSrc,
  userMenuItems = [],
}: TopBarProps): JSX.Element {
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
      {breadcrumbs.length > 0 ? (
        <Breadcrumb segments={breadcrumbs} />
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
