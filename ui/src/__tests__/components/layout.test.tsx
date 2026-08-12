import { describe, expect, it, vi, beforeEach } from 'vitest';
import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { render } from '@/test-utils';
import { Sidebar, type NavItem } from '@/components/layout/Sidebar';
import { TopBar } from '@/components/layout/TopBar';
import { MainContent } from '@/components/layout/MainContent';
import { useLayoutStore } from '@/stores/layout';
import { mockServices } from '@/test/fixtures';

// Reset Zustand store between tests.
beforeEach(() => {
  useLayoutStore.setState({ isSidebarCollapsed: false });
});

// ---------------------------------------------------------------------------
// Sidebar
// ---------------------------------------------------------------------------

const ICON = <span data-testid="nav-icon" />;

const NAV_ITEMS: NavItem[] = [
  { label: 'Dashboard', path: '/', icon: ICON },
  { label: 'Services', path: '/services', icon: ICON },
  {
    label: 'Admin Panel',
    path: '/admin',
    icon: ICON,
    requiredPermission: 'admin:access',
  },
];

describe('Sidebar', () => {
  it('renders navigation landmark', () => {
    render(<Sidebar navItems={NAV_ITEMS} />);
    expect(screen.getByRole('navigation', { name: 'Main navigation' })).toBeInTheDocument();
  });

  it('renders all nav items without requiredPermission', () => {
    render(<Sidebar navItems={NAV_ITEMS} />);
    expect(screen.getByLabelText('Dashboard')).toBeInTheDocument();
    expect(screen.getByLabelText('Services')).toBeInTheDocument();
  });

  it('hides nav items when user lacks the required permission', () => {
    render(<Sidebar navItems={NAV_ITEMS} userPermissions={['service:read']} />);
    expect(screen.queryByLabelText('Admin Panel')).not.toBeInTheDocument();
  });

  it('shows nav items when user has the required permission', () => {
    render(<Sidebar navItems={NAV_ITEMS} userPermissions={['service:read', 'admin:access']} />);
    expect(screen.getByLabelText('Admin Panel')).toBeInTheDocument();
  });

  it('hides permission-gated items when no userPermissions given', () => {
    render(<Sidebar navItems={NAV_ITEMS} />);
    // Without userPermissions, items with requiredPermission are hidden.
    expect(screen.getByLabelText('Dashboard')).toBeInTheDocument();
    expect(screen.getByLabelText('Services')).toBeInTheDocument();
    expect(screen.queryByLabelText('Admin Panel')).not.toBeInTheDocument();
  });

  it('renders collapse toggle button', () => {
    render(<Sidebar navItems={NAV_ITEMS} />);
    expect(
      screen.getByRole('button', { name: 'Collapse sidebar' }),
    ).toBeInTheDocument();
  });

  it('collapses sidebar when toggle is clicked', async () => {
    render(<Sidebar navItems={NAV_ITEMS} />);
    await userEvent.click(screen.getByRole('button', { name: 'Collapse sidebar' }));
    expect(
      screen.getByRole('button', { name: 'Expand sidebar' }),
    ).toBeInTheDocument();
  });

  it('expands sidebar when toggle clicked twice', async () => {
    render(<Sidebar navItems={NAV_ITEMS} />);
    const toggle = screen.getByRole('button', { name: 'Collapse sidebar' });
    await userEvent.click(toggle);
    await userEvent.click(screen.getByRole('button', { name: 'Expand sidebar' }));
    expect(
      screen.getByRole('button', { name: 'Collapse sidebar' }),
    ).toBeInTheDocument();
  });

  it('renders "FG" logo when no logoSrc is provided and collapsed', async () => {
    render(<Sidebar navItems={[]} />);
    await userEvent.click(screen.getByRole('button', { name: 'Collapse sidebar' }));
    expect(screen.getByLabelText('ForgeGuard')).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// TopBar
// ---------------------------------------------------------------------------

describe('TopBar', () => {
  it('renders header landmark', () => {
    render(<TopBar />);
    expect(screen.getByRole('banner')).toBeInTheDocument();
  });

  it('renders fallback "ForgeGuard" text when no breadcrumbs', () => {
    render(<TopBar />);
    expect(screen.getByText('ForgeGuard')).toBeInTheDocument();
  });

  it('renders breadcrumb segments when provided', () => {
    render(
      <TopBar breadcrumbs={[{ label: 'Home', href: '/' }, { label: 'Services' }]} />,
    );
    expect(screen.getByText('Home')).toBeInTheDocument();
    expect(screen.getByText('Services')).toBeInTheDocument();
  });

  it('renders ServiceSelector', () => {
    render(<TopBar />);
    expect(screen.getByLabelText('Select active service')).toBeInTheDocument();
  });

  it('shows "No services registered" placeholder when services is empty', () => {
    render(<TopBar services={[]} />);
    expect(screen.getByPlaceholderText('No services registered')).toBeInTheDocument();
  });

  it('shows "Select service" placeholder when services exist', () => {
    render(<TopBar services={mockServices} />);
    expect(screen.getByPlaceholderText('Select service')).toBeInTheDocument();
  });

  it('renders dark mode toggle button', () => {
    render(<TopBar />);
    expect(
      screen.getByRole('button', { name: /switch to (dark|light) mode/i }),
    ).toBeInTheDocument();
  });

  it('renders user avatar when userName is provided', () => {
    render(<TopBar userName="Alice Chen" />);
    // Dropdown trigger has an aria-label
    expect(screen.getByLabelText('User menu for Alice Chen')).toBeInTheDocument();
  });

  it('does not render user avatar when userName is omitted', () => {
    render(<TopBar />);
    expect(screen.queryByLabelText(/user menu/i)).not.toBeInTheDocument();
  });

  it('calls onServiceSelect when a service is selected', async () => {
    const onServiceSelect = vi.fn();
    render(
      <TopBar
        services={mockServices}
        selectedServiceId={null}
        onServiceSelect={onServiceSelect}
      />,
    );
    // Open the select dropdown
    const select = screen.getByLabelText('Select active service');
    await userEvent.click(select);
    // Click the first service option
    const option = await screen.findByText('payment-api');
    await userEvent.click(option);
    expect(onServiceSelect).toHaveBeenCalledWith('svc-001');
  });
});

// ---------------------------------------------------------------------------
// MainContent
// ---------------------------------------------------------------------------

describe('MainContent', () => {
  it('renders as main landmark', () => {
    render(<MainContent>Hello</MainContent>);
    expect(screen.getByRole('main')).toBeInTheDocument();
  });

  it('renders children', () => {
    render(<MainContent>Page body</MainContent>);
    expect(screen.getByText('Page body')).toBeInTheDocument();
  });

  it('uses default aria-label', () => {
    render(<MainContent>Content</MainContent>);
    expect(screen.getByRole('main', { name: 'Page content' })).toBeInTheDocument();
  });

  it('uses custom aria-label', () => {
    render(<MainContent ariaLabel="Dashboard">Content</MainContent>);
    expect(screen.getByRole('main', { name: 'Dashboard' })).toBeInTheDocument();
  });
});
