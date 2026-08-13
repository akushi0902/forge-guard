import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@/test-utils';
import userEvent from '@testing-library/user-event';
import { ManagerDashboardEmptyState } from '@/components/empty-states/ManagerDashboardEmptyState';

describe('ManagerDashboardEmptyState', () => {
  it('renders the correct title (AC-5)', () => {
    render(<ManagerDashboardEmptyState onOnboardService={vi.fn()} />);
    expect(screen.getByText('No Services Onboarded')).toBeInTheDocument();
  });

  it('renders the CTA button with correct label', () => {
    render(<ManagerDashboardEmptyState onOnboardService={vi.fn()} />);
    expect(screen.getByRole('button', { name: /onboard a service/i })).toBeInTheDocument();
  });

  it('calls onOnboardService when CTA is clicked', async () => {
    const handler = vi.fn();
    render(<ManagerDashboardEmptyState onOnboardService={handler} />);
    await userEvent.click(screen.getByRole('button', { name: /onboard a service/i }));
    expect(handler).toHaveBeenCalledOnce();
  });

  it('renders onboarding steps for the manager workflow', () => {
    render(<ManagerDashboardEmptyState onOnboardService={vi.fn()} />);
    expect(screen.getByText('Register your first service')).toBeInTheDocument();
    expect(screen.getByText('Assign teams and policies')).toBeInTheDocument();
    expect(screen.getByText('Run evaluations to populate metrics')).toBeInTheDocument();
  });

  it('renders an illustration with aria-hidden', () => {
    render(<ManagerDashboardEmptyState onOnboardService={vi.fn()} />);
    expect(document.querySelector('svg[aria-hidden="true"]')).toBeInTheDocument();
  });
});
