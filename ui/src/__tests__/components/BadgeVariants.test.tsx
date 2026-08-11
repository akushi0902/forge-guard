import { describe, expect, it } from 'vitest';
import { screen } from '@testing-library/react';
import { render } from '@/test-utils';
import { SeverityBadge, StatusBadge } from '@/components/shared/BadgeVariants';
import type { FindingSeverity } from '@/types';

describe('SeverityBadge', () => {
  const severities: FindingSeverity[] = ['critical', 'high', 'medium', 'low', 'info'];

  it.each(severities)('renders severity "%s" with correct label', (severity) => {
    render(<SeverityBadge severity={severity} />);
    expect(
      screen.getByText(severity.charAt(0).toUpperCase() + severity.slice(1)),
    ).toBeInTheDocument();
  });

  it('renders critical badge', () => {
    render(<SeverityBadge severity="critical" />);
    expect(screen.getByText('Critical')).toBeInTheDocument();
  });

  it('renders high badge', () => {
    render(<SeverityBadge severity="high" />);
    expect(screen.getByText('High')).toBeInTheDocument();
  });

  it('renders medium badge', () => {
    render(<SeverityBadge severity="medium" />);
    expect(screen.getByText('Medium')).toBeInTheDocument();
  });

  it('renders low badge', () => {
    render(<SeverityBadge severity="low" />);
    expect(screen.getByText('Low')).toBeInTheDocument();
  });

  it('renders info badge', () => {
    render(<SeverityBadge severity="info" />);
    expect(screen.getByText('Info')).toBeInTheDocument();
  });
});

describe('StatusBadge', () => {
  it.each(['success', 'warning', 'error', 'info', 'neutral'] as const)(
    'renders status "%s" without throwing',
    (status) => {
      expect(() =>
        render(<StatusBadge status={status}>{status}</StatusBadge>),
      ).not.toThrow();
    },
  );

  it('renders with children', () => {
    render(<StatusBadge status="success">Active</StatusBadge>);
    expect(screen.getByText('Active')).toBeInTheDocument();
  });
});
