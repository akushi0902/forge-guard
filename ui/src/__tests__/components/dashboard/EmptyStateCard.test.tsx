import { afterAll, afterEach, beforeAll, describe, expect, it } from 'vitest';
import { render, screen } from '@/test-utils';
import { server } from '@/test/mocks/server';
import { EmptyStateCard } from '@/components/dashboard/EmptyStateCard';

beforeAll(() => server.listen({ onUnhandledRequest: 'warn' }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

describe('EmptyStateCard', () => {
  it('renders the "No evaluations yet" heading', () => {
    render(<EmptyStateCard serviceId="svc-001" />);
    expect(screen.getByText('No evaluations yet')).toBeInTheDocument();
  });

  it('renders the 3-step onboarding instructions', () => {
    render(<EmptyStateCard serviceId="svc-001" />);
    expect(screen.getByText('Register your service')).toBeInTheDocument();
    expect(screen.getByText('Configure policies')).toBeInTheDocument();
    expect(screen.getByText('Trigger your first evaluation')).toBeInTheDocument();
  });

  it('renders the Run First Assessment CTA button', () => {
    render(<EmptyStateCard serviceId="svc-001" />);
    expect(
      screen.getByRole('button', { name: /run first assessment/i }),
    ).toBeInTheDocument();
  });

  it('CTA button is enabled when serviceId is provided', () => {
    render(<EmptyStateCard serviceId="svc-001" />);
    const btn = screen.getByTestId('run-assessment-btn');
    expect(btn).not.toBeDisabled();
  });

  it('CTA button is disabled when serviceId is empty', () => {
    render(<EmptyStateCard serviceId="" />);
    const btn = screen.getByTestId('run-assessment-btn');
    expect(btn).toBeDisabled();
  });

  it('does not show an error alert by default', () => {
    render(<EmptyStateCard serviceId="svc-001" />);
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });

  it('renders an illustration emoji', () => {
    render(<EmptyStateCard serviceId="svc-001" />);
    expect(screen.getByText('📊')).toBeInTheDocument();
  });
});
