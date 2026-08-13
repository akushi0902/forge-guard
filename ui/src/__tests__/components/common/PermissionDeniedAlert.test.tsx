/**
 * Unit tests for PermissionDeniedAlert component (WO-086).
 *
 * Covers: rendering with all 10 permission types, ARIA attributes
 * (role='alert', aria-live='assertive'), close button behaviour,
 * multi-role display, and unknown permission fallback.
 */

import { describe, expect, it, vi } from 'vitest';
import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { render } from '@/test-utils';
import { PermissionDeniedAlert } from '@/components/common/PermissionDeniedAlert';
import type { PermissionDeniedResponse } from '@/types/api-errors';

function makeError(
  permission: string,
  overrides: Partial<PermissionDeniedResponse> = {},
): PermissionDeniedResponse {
  return {
    error: 'forbidden',
    permission,
    required_role: 'Platform Admin',
    message: `Requires ${permission}`,
    action: 'Contact your Platform Admin for access.',
    ...overrides,
  };
}

describe('PermissionDeniedAlert — rendering', () => {
  it('renders the "Permission Denied" title', () => {
    render(<PermissionDeniedAlert error={makeError('release.approve')} />);
    expect(screen.getByText('Permission Denied')).toBeInTheDocument();
  });

  it('displays the human-readable permission label', () => {
    render(<PermissionDeniedAlert error={makeError('release.approve')} />);
    expect(screen.getByText(/Approve Release/)).toBeInTheDocument();
  });

  it('displays the role list for a known multi-role permission', () => {
    render(<PermissionDeniedAlert error={makeError('release.approve')} />);
    expect(screen.getByText(/Tech Lead/)).toBeInTheDocument();
    expect(screen.getByText(/Platform Admin/)).toBeInTheDocument();
  });

  it('displays the action guidance text', () => {
    render(
      <PermissionDeniedAlert
        error={makeError('policy.manage', { action: 'Ask your manager.' })}
      />,
    );
    expect(screen.getByText('Ask your manager.')).toBeInTheDocument();
  });

  it('renders the data-testid attribute', () => {
    render(<PermissionDeniedAlert error={makeError('policy.manage')} />);
    expect(screen.getByTestId('permission-denied-alert')).toBeInTheDocument();
  });

  it('does not render a close button when onClose is not provided', () => {
    render(<PermissionDeniedAlert error={makeError('policy.manage')} />);
    expect(screen.queryByRole('button')).not.toBeInTheDocument();
  });

  it('renders a close button when onClose is provided', () => {
    render(<PermissionDeniedAlert error={makeError('policy.manage')} onClose={vi.fn()} />);
    expect(screen.getByRole('button')).toBeInTheDocument();
  });

  it('calls onClose when the close button is clicked', async () => {
    const onClose = vi.fn();
    render(<PermissionDeniedAlert error={makeError('policy.manage')} onClose={onClose} />);
    await userEvent.click(screen.getByRole('button'));
    expect(onClose).toHaveBeenCalledOnce();
  });
});

describe('PermissionDeniedAlert — ARIA attributes', () => {
  it('has role="alert" on the alert element', () => {
    render(<PermissionDeniedAlert error={makeError('release.approve')} />);
    const alert = screen.getByTestId('permission-denied-alert');
    expect(alert).toHaveAttribute('role', 'alert');
  });

  it('has aria-live="assertive" on the alert element', () => {
    render(<PermissionDeniedAlert error={makeError('release.approve')} />);
    const alert = screen.getByTestId('permission-denied-alert');
    expect(alert).toHaveAttribute('aria-live', 'assertive');
  });
});

describe('PermissionDeniedAlert — all 10 permission types', () => {
  const permissions = [
    ['service.view',       'View Services'],
    ['assessment.request', 'Request Assessment'],
    ['release.approve',    'Approve Release'],
    ['release.block',      'Block Release'],
    ['exception.request',  'Request Exception'],
    ['exception.approve',  'Approve Exception'],
    ['policy.manage',      'Manage Policies'],
    ['rbac.manage',        'Manage Access Control'],
    ['health.monitor',     'Monitor Platform Health'],
    ['trends.view',        'View Trends'],
  ] as const;

  for (const [permission, label] of permissions) {
    it(`renders label "${label}" for permission "${permission}"`, () => {
      render(<PermissionDeniedAlert error={makeError(permission)} />);
      expect(screen.getByText(new RegExp(label))).toBeInTheDocument();
    });
  }
});

describe('PermissionDeniedAlert — multi-role display', () => {
  it('displays all roles when required_role is an array', () => {
    render(
      <PermissionDeniedAlert
        error={makeError('exception.approve', {
          required_role: ['Engineering Manager', 'Platform Admin'],
        })}
      />,
    );
    expect(screen.getByText(/Engineering Manager/)).toBeInTheDocument();
    expect(screen.getByText(/Platform Admin/)).toBeInTheDocument();
  });
});

describe('PermissionDeniedAlert — unknown permission fallback', () => {
  it('renders the raw permission slug when not in PERMISSION_MAP', () => {
    render(<PermissionDeniedAlert error={makeError('some.unknown.permission')} />);
    expect(screen.getByText(/some.unknown.permission/)).toBeInTheDocument();
  });
});
